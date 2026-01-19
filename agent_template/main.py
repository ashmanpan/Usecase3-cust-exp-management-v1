"""
Agent Template Main Entry Point

This is the main entry point for running an agent.
Customize this file or import the components for your specific agent.
"""

import asyncio
import os
from typing import Any, Optional

import structlog
import uvicorn
from dotenv import load_dotenv

from .config_loader import load_config, get_config
from .api.server import A2ATaskServer, create_app
from .workflow import BaseWorkflow
from .tools.mcp_client import MCPToolClient
from .tools.a2a_client import A2AClient, configure_a2a_client
from .chains.llm_factory import get_llm, LLMConfig

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


class AgentRunner:
    """
    Agent Runner

    Initializes and runs an agent with A2A server.
    """

    def __init__(
        self,
        workflow_class: type,
        config_path: Optional[str] = None,
    ):
        """
        Initialize agent runner.

        Args:
            workflow_class: Workflow class to instantiate
            config_path: Path to config.yaml
        """
        self.config = load_config(config_path)
        self.workflow_class = workflow_class

        # Initialize components
        self._mcp_client: Optional[MCPToolClient] = None
        self._a2a_client: Optional[A2AClient] = None
        self._workflow: Optional[BaseWorkflow] = None
        self._server: Optional[A2ATaskServer] = None

    async def initialize(self) -> None:
        """Initialize all components"""
        logger.info(
            "Initializing agent",
            name=self.config.agent.name,
            version=self.config.agent.version,
        )

        # Initialize MCP client
        self._mcp_client = MCPToolClient(
            server_url=self.config.mcp.server_url,
            timeout=self.config.mcp.timeout_seconds,
            blocked_tools=self.config.mcp.blocked_tools,
        )

        # Initialize A2A client for calling other agents
        agent_registry = {}
        if hasattr(self.config.services, "pca") and self.config.services.pca:
            agent_registry["path_computation_agent"] = self.config.services.pca.get("a2a_url", "")

        self._a2a_client = configure_a2a_client(
            agent_registry=agent_registry,
            default_timeout=30.0,
        )

        # Initialize workflow
        self._workflow = self.workflow_class(
            agent_name=self.config.agent.name,
            agent_version=self.config.agent.version,
            mcp_client=self._mcp_client,
            a2a_client=self._a2a_client,
            max_iterations=self.config.workflow.max_iterations,
            stage_tools=self.config.workflow.stages,
        )

        # Compile workflow
        self._workflow.compile()

        logger.info("Agent initialized successfully")

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
            task_type: Type of task
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
            "Starting A2A server",
            host=self.config.a2a.host,
            port=self.config.a2a.port,
        )

        uvicorn.run(
            server.app,
            host=self.config.a2a.host,
            port=self.config.a2a.port,
            log_level=self.config.observability.log_level.lower(),
        )


def run_agent(workflow_class: type, config_path: Optional[str] = None) -> None:
    """
    Convenience function to run an agent.

    Args:
        workflow_class: Workflow class to use
        config_path: Path to configuration file
    """
    runner = AgentRunner(workflow_class, config_path)
    runner.run()


# Example usage when running this file directly
if __name__ == "__main__":
    # This is just for testing - real agents will import and customize
    from .workflow import BaseWorkflow
    from .schemas.state import WorkflowState
    from langgraph.graph import StateGraph, START, END

    class ExampleWorkflow(BaseWorkflow):
        """Example workflow for testing"""

        def get_state_class(self) -> type:
            return WorkflowState

        def build_graph(self, graph: StateGraph) -> None:
            """Build simple echo workflow"""

            async def echo_node(state: dict) -> dict:
                return {
                    "result": {
                        "echo": state.get("input_payload", {}),
                        "task_id": state.get("task_id"),
                    },
                    "status": "success",
                }

            graph.add_node("echo", echo_node)
            graph.add_edge(START, "echo")
            graph.add_edge("echo", END)

    run_agent(ExampleWorkflow)
