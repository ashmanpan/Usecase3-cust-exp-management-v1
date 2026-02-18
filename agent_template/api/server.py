"""
A2A Task Server Implementation

Provides HTTP server for receiving A2A tasks from other agents.
Replaces Kafka consumer with direct A2A protocol.
"""

import asyncio
import hmac
import ipaddress
from typing import Any, Callable, Optional
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import os
import structlog
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from ..schemas.tasks import TaskInput, TaskOutput, TaskStatus, AgentCard

logger = structlog.get_logger(__name__)


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    agent_name: str
    version: str
    timestamp: str


class A2ATaskServer:
    """
    A2A Task Server for receiving and processing tasks.

    Features:
    - Synchronous task execution (POST /a2a/tasks)
    - Asynchronous task execution with callback (POST /a2a/tasks/async)
    - Task status tracking (GET /a2a/tasks/{task_id}/status)
    - Agent card for capability discovery (GET /.well-known/agent.json)
    - Health checks (GET /health, GET /ready)
    """

    def __init__(
        self,
        agent_name: str,
        agent_version: str,
        agent_description: str,
        workflow_executor: Callable,
        supported_task_types: list[str],
        capabilities: list[dict[str, Any]] = None,
        tags: list[str] = None,
    ):
        """
        Initialize A2A Task Server.

        Args:
            agent_name: Name of this agent
            agent_version: Version string
            agent_description: Human-readable description
            workflow_executor: Async function to execute workflows
            supported_task_types: List of task types this agent handles
            capabilities: Agent capabilities for discovery
            tags: Tags for this agent
        """
        self.agent_name = agent_name
        self.agent_version = agent_version
        self.agent_description = agent_description
        self.workflow_executor = workflow_executor
        self.supported_task_types = supported_task_types
        self.capabilities = capabilities or []
        self.tags = tags or []

        # Task tracking (bounded to prevent memory leaks)
        self._max_stored_tasks = 1000
        self._tasks: dict[str, TaskOutput] = {}
        self._pending_tasks: dict[str, TaskInput] = {}

        # Health state
        self._ready = False
        self._started_at = datetime.now(timezone.utc)

        # Auth configuration
        self._a2a_secret = os.getenv("A2A_SHARED_SECRET", "")

        # Create FastAPI app
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        """Create FastAPI application with routes"""

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """Lifecycle management"""
            logger.info(
                "A2A Task Server starting",
                agent=self.agent_name,
                version=self.agent_version,
            )
            self._ready = True
            yield
            logger.info("A2A Task Server shutting down")
            self._ready = False

        app = FastAPI(
            title=f"{self.agent_name} A2A Server",
            version=self.agent_version,
            description=self.agent_description,
            lifespan=lifespan,
        )

        # Register routes
        self._register_routes(app)
        return app

    async def _verify_a2a_token(self, request: Request) -> None:
        """Verify A2A shared secret if configured."""
        if not self._a2a_secret:
            return  # Auth not configured — skip (dev mode)
        token = request.headers.get("X-Agent-Token", "")
        if not hmac.compare_digest(token, self._a2a_secret):
            raise HTTPException(status_code=401, detail="Invalid or missing A2A token")

    def _register_routes(self, app: FastAPI) -> None:
        """Register all API routes"""
        server = self  # capture for closures

        # ============== Health Endpoints ==============

        @app.get("/health", response_model=HealthResponse)
        async def health_check():
            """Basic health check"""
            return HealthResponse(
                status="healthy",
                agent_name=self.agent_name,
                version=self.agent_version,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        @app.get("/ready")
        async def readiness_check():
            """Readiness check for orchestration"""
            if not self._ready:
                raise HTTPException(status_code=503, detail="Not ready")
            return {"status": "ready"}

        # ============== A2A Discovery ==============

        @app.get("/.well-known/agent.json", response_model=AgentCard)
        async def get_agent_card():
            """Return agent card for capability discovery"""
            return AgentCard(
                name=self.agent_name,
                version=self.agent_version,
                description=self.agent_description,
                url="",  # Will be filled by client based on request
                protocol="a2a",
                capabilities=self.capabilities,
                supported_task_types=self.supported_task_types,
                tags=self.tags,
            )

        # ============== A2A Task Endpoints ==============

        @app.post("/a2a/tasks", response_model=TaskOutput)
        async def execute_task(task: TaskInput, request: Request):
            """Execute a task synchronously. Blocks until complete."""
            await server._verify_a2a_token(request)
            logger.info(
                "Received A2A task",
                task_id=task.task_id,
                task_type=task.task_type,
                incident_id=task.incident_id,
            )

            # Validate task type
            if task.task_type not in self.supported_task_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported task type: {task.task_type}. "
                    f"Supported: {self.supported_task_types}",
                )

            # Execute workflow
            started_at = datetime.now(timezone.utc)
            try:
                result = await asyncio.wait_for(
                    self.workflow_executor(
                        task_id=task.task_id,
                        task_type=task.task_type,
                        incident_id=task.incident_id,
                        payload=task.payload,
                        correlation_id=task.correlation_id,
                    ),
                    timeout=task.timeout_seconds,
                )

                completed_at = datetime.now(timezone.utc)
                duration_ms = int((completed_at - started_at).total_seconds() * 1000)

                output = TaskOutput(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    status=TaskStatus(
                        state="completed",
                        progress=100,
                        message="Task completed successfully",
                    ),
                    result=result,
                    agent_name=self.agent_name,
                    agent_version=self.agent_version,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                )

                # Store for status queries (with eviction)
                self._evict_old_tasks()
                self._tasks[task.task_id] = output
                logger.info(
                    "Task completed",
                    task_id=task.task_id,
                    duration_ms=duration_ms,
                )
                return output

            except asyncio.TimeoutError:
                logger.error("Task timed out", task_id=task.task_id)
                output = TaskOutput(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    status=TaskStatus(
                        state="failed",
                        message=f"Task timed out after {task.timeout_seconds}s",
                    ),
                    error=f"Timeout after {task.timeout_seconds} seconds",
                    agent_name=self.agent_name,
                    agent_version=self.agent_version,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc),
                )
                self._tasks[task.task_id] = output
                raise HTTPException(status_code=504, detail="Task timed out")

            except Exception as e:
                logger.exception("Task failed", task_id=task.task_id, error=str(e))
                output = TaskOutput(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    status=TaskStatus(
                        state="failed",
                        message=str(e),
                    ),
                    error=str(e),
                    agent_name=self.agent_name,
                    agent_version=self.agent_version,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc),
                )
                self._tasks[task.task_id] = output
                raise HTTPException(status_code=500, detail="Internal task execution error")

        @app.post("/a2a/tasks/async")
        async def execute_task_async(
            task: TaskInput,
            background_tasks: BackgroundTasks,
            request: Request,
        ):
            """Execute a task asynchronously. Returns immediately with task_id."""
            await server._verify_a2a_token(request)
            logger.info(
                "Received async A2A task",
                task_id=task.task_id,
                task_type=task.task_type,
            )

            # Validate task type
            if task.task_type not in self.supported_task_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported task type: {task.task_type}",
                )

            # Store as pending
            self._pending_tasks[task.task_id] = task
            self._tasks[task.task_id] = TaskOutput(
                task_id=task.task_id,
                task_type=task.task_type,
                status=TaskStatus(state="pending"),
                agent_name=self.agent_name,
                agent_version=self.agent_version,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )

            # Schedule background execution
            background_tasks.add_task(self._execute_async_task, task)

            return {"task_id": task.task_id, "status": "accepted"}

        @app.get("/a2a/tasks/{task_id}/status", response_model=TaskStatus)
        async def get_task_status(task_id: str, request: Request):
            """Get status of a task"""
            await server._verify_a2a_token(request)
            if task_id not in self._tasks:
                raise HTTPException(status_code=404, detail="Task not found")
            return self._tasks[task_id].status

        @app.get("/a2a/tasks/{task_id}", response_model=TaskOutput)
        async def get_task_result(task_id: str, request: Request):
            """Get full task result"""
            await server._verify_a2a_token(request)
            if task_id not in self._tasks:
                raise HTTPException(status_code=404, detail="Task not found")
            return self._tasks[task_id]

    async def _execute_async_task(self, task: TaskInput) -> None:
        """Execute task in background and handle callback"""
        started_at = datetime.now(timezone.utc)

        # Update status to running
        self._tasks[task.task_id] = TaskOutput(
            task_id=task.task_id,
            task_type=task.task_type,
            status=TaskStatus(state="running", progress=0),
            agent_name=self.agent_name,
            agent_version=self.agent_version,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        )

        try:
            result = await self.workflow_executor(
                task_id=task.task_id,
                task_type=task.task_type,
                incident_id=task.incident_id,
                payload=task.payload,
                correlation_id=task.correlation_id,
            )

            completed_at = datetime.now(timezone.utc)
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)

            output = TaskOutput(
                task_id=task.task_id,
                task_type=task.task_type,
                status=TaskStatus(state="completed", progress=100),
                result=result,
                agent_name=self.agent_name,
                agent_version=self.agent_version,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
            )
            self._tasks[task.task_id] = output

            # Send callback if configured
            if task.callback_url:
                await self._send_callback(task.callback_url, output)

        except Exception as e:
            logger.exception("Async task failed", task_id=task.task_id)
            output = TaskOutput(
                task_id=task.task_id,
                task_type=task.task_type,
                status=TaskStatus(state="failed", message=str(e)),
                error=str(e),
                agent_name=self.agent_name,
                agent_version=self.agent_version,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )
            self._tasks[task.task_id] = output

            if task.callback_url:
                await self._send_callback(task.callback_url, output)

        finally:
            # Clean up pending
            self._pending_tasks.pop(task.task_id, None)

    def _evict_old_tasks(self) -> None:
        """Evict oldest completed tasks when storage limit is reached."""
        if len(self._tasks) < self._max_stored_tasks:
            return
        completed = sorted(
            ((k, v) for k, v in self._tasks.items() if v.status.state in ("completed", "failed")),
            key=lambda x: x[1].completed_at or datetime.min,
        )
        to_remove = len(self._tasks) - self._max_stored_tasks + 100  # free 100 slots
        for task_id, _ in completed[:to_remove]:
            del self._tasks[task_id]

    def _validate_callback_url(self, url: str) -> bool:
        """Validate callback URL to prevent SSRF attacks."""
        try:
            parsed = urlparse(url)
            # Only allow HTTPS (or HTTP in dev mode)
            if parsed.scheme not in ("https", "http"):
                return False
            hostname = parsed.hostname
            if not hostname:
                return False
            # Block internal/metadata IPs
            try:
                addr = ipaddress.ip_address(hostname)
                if addr.is_private or addr.is_loopback or addr.is_link_local:
                    # Allow private IPs only for inter-agent communication
                    allowed_prefixes = os.getenv("CALLBACK_ALLOWED_PRIVATE_NETS", "10.,172.,192.168.")
                    if not any(hostname.startswith(p) for p in allowed_prefixes.split(",")):
                        return False
                # Always block link-local/metadata
                if addr.is_link_local or hostname.startswith("169.254."):
                    return False
            except ValueError:
                pass  # hostname is a DNS name, not an IP — allowed
            return True
        except Exception:
            return False

    async def _send_callback(self, url: str, output: TaskOutput) -> None:
        """Send task result to callback URL with SSRF protection."""
        if not self._validate_callback_url(url):
            logger.warning("Blocked callback to disallowed URL", url=url, task_id=output.task_id)
            return

        import httpx

        try:
            headers = {}
            if self._a2a_secret:
                headers["X-Agent-Token"] = self._a2a_secret
            async with httpx.AsyncClient() as client:
                await client.post(url, json=output.model_dump(mode="json"), headers=headers)
                logger.info("Sent callback", url=url, task_id=output.task_id)
        except Exception as e:
            logger.error("Failed to send callback", url=url, error=str(e))


def create_app(
    agent_name: str,
    agent_version: str,
    agent_description: str,
    workflow_executor: Callable,
    supported_task_types: list[str],
    **kwargs,
) -> FastAPI:
    """
    Create FastAPI app for A2A Task Server.

    Convenience function for creating the server.
    """
    server = A2ATaskServer(
        agent_name=agent_name,
        agent_version=agent_version,
        agent_description=agent_description,
        workflow_executor=workflow_executor,
        supported_task_types=supported_task_types,
        **kwargs,
    )
    return server.app
