"""
Path Computation Agent Main Entry Point

Runs the Path Computation agent with A2A server on port 8003.
From DESIGN.md: Query KG Dijkstra for alternate paths with constraints.
"""

import asyncio
import os
import sys
from typing import Any, Optional

import structlog
import uvicorn
from dotenv import load_dotenv

# Add parent path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agent_template.config_loader import load_config
from agent_template.api.server import A2ATaskServer
from agent_template.tools.mcp_client import MCPToolClient
from agent_template.tools.a2a_client import A2AClient, configure_a2a_client

from .workflow import PathComputationWorkflow

# Load environment variables
load_dotenv()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
        if os.getenv("LOG_FORMAT", "json") == "json"
        else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class PathComputationRunner:
    """
    Path Computation Agent Runner

    Initializes and runs the Path Computation agent with A2A server.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize runner.

        Args:
            config_path: Path to config.yaml
        """
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "config.yaml")

        self.config = load_config(config_path)
        self._mcp_client: Optional[MCPToolClient] = None
        self._a2a_client: Optional[A2AClient] = None
        self._workflow: Optional[PathComputationWorkflow] = None
        self._server: Optional[A2ATaskServer] = None

    async def initialize(self) -> None:
        """Initialize all components"""
        logger.info(
            "Initializing Path Computation agent",
            name=self.config.agent.name,
            version=self.config.agent.version,
        )

        # Initialize MCP client
        self._mcp_client = MCPToolClient(
            server_url=self.config.mcp.server_url,
            timeout=self.config.mcp.timeout_seconds,
            blocked_tools=self.config.mcp.blocked_tools,
        )

        # Initialize A2A client
        agent_registry = {}
        if hasattr(self.config, "services") and self.config.services:
            services = self.config.services
            if hasattr(services, "orchestrator"):
                agent_registry["orchestrator"] = services.orchestrator.get("a2a_url", "")

        self._a2a_client = configure_a2a_client(
            agent_registry=agent_registry,
            default_timeout=60.0,
        )

        # Initialize workflow
        self._workflow = PathComputationWorkflow(
            agent_name=self.config.agent.name,
            agent_version=self.config.agent.version,
            mcp_client=self._mcp_client,
            a2a_client=self._a2a_client,
            max_iterations=self.config.workflow.max_iterations,
            stage_tools=self.config.workflow.stages,
        )

        # Compile workflow
        self._workflow.compile()

        logger.info("Path Computation agent initialized successfully")

    async def execute_workflow(
        self,
        task_id: str,
        task_type: str,
        incident_id: Optional[str] = None,
        payload: dict[str, Any] = None,
        correlation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Execute workflow (called by A2A server).

        Args:
            task_id: Task identifier
            task_type: Type of task (compute_path, etc.)
            incident_id: Related incident
            payload: Task payload
            correlation_id: Correlation ID

        Returns:
            Workflow result
        """
        if self._workflow is None:
            raise RuntimeError("Workflow not initialized")

        return await self._workflow.execute(
            task_id=task_id,
            task_type=task_type,
            incident_id=incident_id,
            payload=payload,
            correlation_id=correlation_id,
        )

    def create_server(self) -> A2ATaskServer:
        """Create A2A task server"""
        self._server = A2ATaskServer(
            agent_name=self.config.agent.name,
            agent_version=self.config.agent.version,
            agent_description=self.config.agent.description,
            workflow_executor=self.execute_workflow,
            supported_task_types=self.config.a2a.capabilities,
            tags=[self.config.agent.type],
        )
        return self._server

    def run(self) -> None:
        """Run the agent server"""
        # Initialize asynchronously
        asyncio.run(self.initialize())

        # Create server
        server = self.create_server()

        # Run with uvicorn
        logger.info(
            "Starting Path Computation A2A server",
            host=self.config.a2a.host,
            port=self.config.a2a.port,
        )

        uvicorn.run(
            server.app,
            host=self.config.a2a.host,
            port=self.config.a2a.port,
            log_level=self.config.observability.log_level.lower(),
        )


def main():
    """Main entry point"""
    runner = PathComputationRunner()
    runner.run()


if __name__ == "__main__":
    main()
