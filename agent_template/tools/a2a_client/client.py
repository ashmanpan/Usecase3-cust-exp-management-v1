"""
A2A (Agent-to-Agent) Client Implementation

Provides async client for calling other agents using the A2A protocol.
Supports both direct HTTP/A2A and gRPC transports.
"""

import asyncio
from typing import Any, Optional
from datetime import datetime
from uuid import uuid4

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..schemas.tasks import TaskInput, TaskOutput, TaskStatus, AgentCard

logger = structlog.get_logger(__name__)


class A2AClientError(Exception):
    """Base exception for A2A client errors"""
    pass


class A2ATimeoutError(A2AClientError):
    """Timeout when calling another agent"""
    pass


class A2AConnectionError(A2AClientError):
    """Connection error when calling another agent"""
    pass


class A2AClient:
    """
    A2A Client for inter-agent communication.

    Supports:
    - Sending tasks to other agents
    - Retrieving agent cards (capability discovery)
    - Health checks
    - Retry with exponential backoff
    - Circuit breaker pattern (via tenacity)
    """

    def __init__(
        self,
        agent_registry: dict[str, str] = None,
        default_timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize A2A client.

        Args:
            agent_registry: Dict mapping agent names to their base URLs
            default_timeout: Default timeout in seconds for requests
            max_retries: Maximum number of retries for failed requests
        """
        self.agent_registry = agent_registry or {}
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None
        self._agent_cards: dict[str, AgentCard] = {}

    async def __aenter__(self) -> "A2AClient":
        """Async context manager entry"""
        self._client = httpx.AsyncClient(timeout=self.default_timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit"""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.default_timeout)
        return self._client

    def register_agent(self, agent_name: str, base_url: str) -> None:
        """Register an agent's base URL"""
        self.agent_registry[agent_name] = base_url.rstrip("/")
        logger.info("Registered agent", agent_name=agent_name, base_url=base_url)

    def get_agent_url(self, agent_name: str) -> str:
        """Get base URL for an agent"""
        if agent_name not in self.agent_registry:
            raise A2AClientError(f"Agent '{agent_name}' not registered")
        return self.agent_registry[agent_name]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    )
    async def get_agent_card(self, agent_name: str) -> AgentCard:
        """
        Retrieve agent card (capability discovery).

        Args:
            agent_name: Name of the agent

        Returns:
            AgentCard describing the agent's capabilities
        """
        # Check cache first
        if agent_name in self._agent_cards:
            return self._agent_cards[agent_name]

        base_url = self.get_agent_url(agent_name)
        client = self._get_client()

        try:
            response = await client.get(f"{base_url}/.well-known/agent.json")
            response.raise_for_status()
            card = AgentCard(**response.json())
            self._agent_cards[agent_name] = card
            logger.info("Retrieved agent card", agent_name=agent_name)
            return card
        except httpx.TimeoutException:
            raise A2ATimeoutError(f"Timeout getting agent card from {agent_name}")
        except httpx.ConnectError as e:
            raise A2AConnectionError(f"Cannot connect to agent {agent_name}: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    )
    async def send_task(
        self,
        agent_name: str,
        task_type: str,
        payload: dict[str, Any],
        incident_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        priority: int = 5,
        timeout: Optional[float] = None,
    ) -> TaskOutput:
        """
        Send a task to another agent and wait for response.

        Args:
            agent_name: Target agent name
            task_type: Type of task (must be in agent's supported_task_types)
            payload: Task payload data
            incident_id: Related incident ID
            correlation_id: Correlation ID for tracing
            priority: Task priority (1=highest, 10=lowest)
            timeout: Request timeout (uses default if not specified)

        Returns:
            TaskOutput from the target agent
        """
        base_url = self.get_agent_url(agent_name)
        client = self._get_client()

        # Build task input
        task_input = TaskInput(
            task_id=str(uuid4()),
            task_type=task_type,
            incident_id=incident_id,
            correlation_id=correlation_id or str(uuid4()),
            payload=payload,
            priority=priority,
            timeout_seconds=int(timeout or self.default_timeout),
        )

        logger.info(
            "Sending A2A task",
            target_agent=agent_name,
            task_id=task_input.task_id,
            task_type=task_type,
            incident_id=incident_id,
        )

        try:
            response = await client.post(
                f"{base_url}/a2a/tasks",
                json=task_input.model_dump(mode="json"),
                timeout=timeout or self.default_timeout,
            )
            response.raise_for_status()

            output = TaskOutput(**response.json())
            logger.info(
                "Received A2A response",
                target_agent=agent_name,
                task_id=task_input.task_id,
                status=output.status.state,
            )
            return output

        except httpx.TimeoutException:
            raise A2ATimeoutError(
                f"Timeout sending task to {agent_name} (task_id={task_input.task_id})"
            )
        except httpx.ConnectError as e:
            raise A2AConnectionError(f"Cannot connect to agent {agent_name}: {e}")
        except httpx.HTTPStatusError as e:
            raise A2AClientError(
                f"HTTP error from {agent_name}: {e.response.status_code} - {e.response.text}"
            )

    async def send_task_async(
        self,
        agent_name: str,
        task_type: str,
        payload: dict[str, Any],
        callback_url: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Send a task asynchronously (fire-and-forget with optional callback).

        Args:
            agent_name: Target agent name
            task_type: Type of task
            payload: Task payload
            callback_url: URL to POST result when complete
            **kwargs: Additional TaskInput fields

        Returns:
            Task ID for tracking
        """
        base_url = self.get_agent_url(agent_name)
        client = self._get_client()

        task_input = TaskInput(
            task_id=str(uuid4()),
            task_type=task_type,
            payload=payload,
            callback_url=callback_url,
            **kwargs,
        )

        logger.info(
            "Sending async A2A task",
            target_agent=agent_name,
            task_id=task_input.task_id,
            task_type=task_type,
        )

        try:
            response = await client.post(
                f"{base_url}/a2a/tasks/async",
                json=task_input.model_dump(mode="json"),
            )
            response.raise_for_status()
            return task_input.task_id
        except Exception as e:
            logger.error("Failed to send async task", error=str(e))
            raise

    async def get_task_status(self, agent_name: str, task_id: str) -> TaskStatus:
        """
        Get status of a previously submitted task.

        Args:
            agent_name: Agent that received the task
            task_id: Task ID to check

        Returns:
            Current TaskStatus
        """
        base_url = self.get_agent_url(agent_name)
        client = self._get_client()

        response = await client.get(f"{base_url}/a2a/tasks/{task_id}/status")
        response.raise_for_status()
        return TaskStatus(**response.json())

    async def health_check(self, agent_name: str) -> bool:
        """
        Check if an agent is healthy.

        Args:
            agent_name: Agent to check

        Returns:
            True if healthy, False otherwise
        """
        base_url = self.get_agent_url(agent_name)
        client = self._get_client()

        try:
            response = await client.get(f"{base_url}/health", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    async def discover_agents(self, registry_url: str) -> dict[str, str]:
        """
        Discover agents from a service registry.

        Args:
            registry_url: URL of the agent registry service

        Returns:
            Dict mapping agent names to URLs
        """
        client = self._get_client()
        response = await client.get(f"{registry_url}/agents")
        response.raise_for_status()

        agents = response.json()
        for agent in agents:
            self.register_agent(agent["name"], agent["url"])

        return self.agent_registry


# Singleton instance
_a2a_client: Optional[A2AClient] = None


def get_a2a_client() -> A2AClient:
    """Get singleton A2A client instance"""
    global _a2a_client
    if _a2a_client is None:
        _a2a_client = A2AClient()
    return _a2a_client


def configure_a2a_client(
    agent_registry: dict[str, str] = None,
    default_timeout: float = 30.0,
    max_retries: int = 3,
) -> A2AClient:
    """Configure the singleton A2A client"""
    global _a2a_client
    _a2a_client = A2AClient(
        agent_registry=agent_registry,
        default_timeout=default_timeout,
        max_retries=max_retries,
    )
    return _a2a_client
