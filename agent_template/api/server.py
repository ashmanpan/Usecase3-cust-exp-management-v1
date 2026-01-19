"""
A2A Task Server Implementation

Provides HTTP server for receiving A2A tasks from other agents.
Replaces Kafka consumer with direct A2A protocol.
"""

import asyncio
from typing import Any, Callable, Optional
from datetime import datetime
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
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

        # Task tracking
        self._tasks: dict[str, TaskOutput] = {}
        self._pending_tasks: dict[str, TaskInput] = {}

        # Health state
        self._ready = False
        self._started_at = datetime.utcnow()

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

    def _register_routes(self, app: FastAPI) -> None:
        """Register all API routes"""

        # ============== Health Endpoints ==============

        @app.get("/health", response_model=HealthResponse)
        async def health_check():
            """Basic health check"""
            return HealthResponse(
                status="healthy",
                agent_name=self.agent_name,
                version=self.agent_version,
                timestamp=datetime.utcnow().isoformat(),
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
                capabilities=[],
                supported_task_types=self.supported_task_types,
                tags=self.tags,
            )

        # ============== A2A Task Endpoints ==============

        @app.post("/a2a/tasks", response_model=TaskOutput)
        async def execute_task(task: TaskInput):
            """
            Execute a task synchronously.

            Blocks until the task completes and returns the result.
            """
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
            started_at = datetime.utcnow()
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

                completed_at = datetime.utcnow()
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

                # Store for status queries
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
                    completed_at=datetime.utcnow(),
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
                    completed_at=datetime.utcnow(),
                )
                self._tasks[task.task_id] = output
                raise HTTPException(status_code=500, detail=str(e))

        @app.post("/a2a/tasks/async")
        async def execute_task_async(
            task: TaskInput,
            background_tasks: BackgroundTasks,
        ):
            """
            Execute a task asynchronously.

            Returns immediately with task_id. Use callback_url or
            GET /a2a/tasks/{task_id}/status to get results.
            """
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
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )

            # Schedule background execution
            background_tasks.add_task(self._execute_async_task, task)

            return {"task_id": task.task_id, "status": "accepted"}

        @app.get("/a2a/tasks/{task_id}/status", response_model=TaskStatus)
        async def get_task_status(task_id: str):
            """Get status of a task"""
            if task_id not in self._tasks:
                raise HTTPException(status_code=404, detail="Task not found")
            return self._tasks[task_id].status

        @app.get("/a2a/tasks/{task_id}", response_model=TaskOutput)
        async def get_task_result(task_id: str):
            """Get full task result"""
            if task_id not in self._tasks:
                raise HTTPException(status_code=404, detail="Task not found")
            return self._tasks[task_id]

    async def _execute_async_task(self, task: TaskInput) -> None:
        """Execute task in background and handle callback"""
        started_at = datetime.utcnow()

        # Update status to running
        self._tasks[task.task_id] = TaskOutput(
            task_id=task.task_id,
            task_type=task.task_type,
            status=TaskStatus(state="running", progress=0),
            agent_name=self.agent_name,
            agent_version=self.agent_version,
            started_at=started_at,
            completed_at=datetime.utcnow(),
        )

        try:
            result = await self.workflow_executor(
                task_id=task.task_id,
                task_type=task.task_type,
                incident_id=task.incident_id,
                payload=task.payload,
                correlation_id=task.correlation_id,
            )

            completed_at = datetime.utcnow()
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
                completed_at=datetime.utcnow(),
            )
            self._tasks[task.task_id] = output

            if task.callback_url:
                await self._send_callback(task.callback_url, output)

        finally:
            # Clean up pending
            self._pending_tasks.pop(task.task_id, None)

    async def _send_callback(self, url: str, output: TaskOutput) -> None:
        """Send task result to callback URL"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                await client.post(url, json=output.model_dump(mode="json"))
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
