"""
Base LangGraph Workflow Template

This module provides the base workflow structure that all agents extend.
Customize by:
1. Extending WorkflowState for agent-specific fields
2. Defining agent-specific nodes
3. Configuring the graph edges
"""

from typing import Any, Optional, Callable, TypeVar
from datetime import datetime
from abc import ABC, abstractmethod

import structlog
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from .schemas.state import WorkflowState
from .tools.mcp_client import MCPToolClient
from .tools.a2a_client import A2AClient

logger = structlog.get_logger(__name__)

# Type variable for state
S = TypeVar("S", bound=WorkflowState)


class BaseWorkflow(ABC):
    """
    Abstract base class for LangGraph workflows.

    Subclass this to create agent-specific workflows.
    Override the abstract methods to customize behavior.
    """

    def __init__(
        self,
        agent_name: str,
        agent_version: str,
        mcp_client: Optional[MCPToolClient] = None,
        a2a_client: Optional[A2AClient] = None,
        max_iterations: int = 3,
        stage_tools: dict[str, list[str]] = None,
    ):
        """
        Initialize workflow.

        Args:
            agent_name: Name of this agent
            agent_version: Version string
            mcp_client: MCP client for tool execution
            a2a_client: A2A client for inter-agent calls
            max_iterations: Maximum workflow iterations
            stage_tools: Dict mapping stage names to allowed tool lists
        """
        self.agent_name = agent_name
        self.agent_version = agent_version
        self.mcp_client = mcp_client or MCPToolClient()
        self.a2a_client = a2a_client or A2AClient()
        self.max_iterations = max_iterations
        self.stage_tools = stage_tools or {}

        self._graph: Optional[StateGraph] = None
        self._compiled = None

    @abstractmethod
    def get_state_class(self) -> type:
        """Return the TypedDict class for this workflow's state"""
        pass

    @abstractmethod
    def build_graph(self, graph: StateGraph) -> None:
        """
        Build the workflow graph.

        Add nodes and edges to the graph.
        Called by compile() before compilation.
        """
        pass

    def get_initial_state(
        self,
        task_id: str,
        task_type: str,
        incident_id: Optional[str] = None,
        payload: dict[str, Any] = None,
        correlation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Create initial state for workflow execution.

        Override to add agent-specific initial state.
        """
        return {
            "task_id": task_id,
            "incident_id": incident_id,
            "correlation_id": correlation_id,
            "input_payload": payload or {},
            "iteration_count": 0,
            "max_iterations": self.max_iterations,
            "current_node": "start",
            "started_at": datetime.utcnow().isoformat(),
            "nodes_executed": [],
            "tool_outputs": [],
            "mcp_tools_used": [],
            "a2a_tasks_sent": [],
            "a2a_responses": {},
            "status": "running",
        }

    def compile(self) -> Any:
        """
        Compile the workflow graph.

        Returns the compiled LangGraph application.
        """
        if self._compiled:
            return self._compiled

        state_class = self.get_state_class()
        self._graph = StateGraph(state_class)

        # Let subclass build the graph
        self.build_graph(self._graph)

        # Compile
        self._compiled = self._graph.compile()
        logger.info("Compiled workflow", agent=self.agent_name)
        return self._compiled

    async def execute(
        self,
        task_id: str,
        task_type: str,
        incident_id: Optional[str] = None,
        payload: dict[str, Any] = None,
        correlation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Execute the workflow.

        Args:
            task_id: Unique task identifier
            task_type: Type of task being processed
            incident_id: Related incident ID
            payload: Task payload data
            correlation_id: Correlation ID for tracing

        Returns:
            Workflow result dict
        """
        app = self.compile()

        initial_state = self.get_initial_state(
            task_id=task_id,
            task_type=task_type,
            incident_id=incident_id,
            payload=payload,
            correlation_id=correlation_id,
        )

        logger.info(
            "Executing workflow",
            agent=self.agent_name,
            task_id=task_id,
            task_type=task_type,
        )

        try:
            final_state = await app.ainvoke(initial_state)

            # Extract result
            result = final_state.get("result", {})
            error = final_state.get("error")

            if error:
                logger.error(
                    "Workflow failed",
                    task_id=task_id,
                    error=error,
                )
            else:
                logger.info(
                    "Workflow completed",
                    task_id=task_id,
                    nodes_executed=final_state.get("nodes_executed", []),
                )

            return result

        except Exception as e:
            logger.exception("Workflow exception", task_id=task_id)
            raise


# ============== Common Node Implementations ==============


def create_tool_node(tools: list) -> ToolNode:
    """Create a LangGraph ToolNode with given tools"""
    return ToolNode(tools)


def make_iteration_check(max_iterations: int) -> Callable[[dict], str]:
    """
    Create an iteration check function for conditional edges.

    Returns function that checks if max iterations reached.
    """

    def check_iteration(state: dict) -> str:
        current = state.get("iteration_count", 0)
        if current >= max_iterations:
            return "max_reached"
        return "continue"

    return check_iteration


def make_checklist_check() -> Callable[[dict], str]:
    """
    Create a checklist check function for conditional edges.

    Returns function that checks if checklist is complete.
    """

    def check_checklist(state: dict) -> str:
        remaining = state.get("remaining_checklist", [])
        if not remaining:
            return "complete"
        return "continue"

    return check_checklist


def make_error_check() -> Callable[[dict], str]:
    """
    Create an error check function for conditional edges.

    Returns function that checks if error occurred.
    """

    def check_error(state: dict) -> str:
        if state.get("error"):
            return "error"
        return "success"

    return check_error


# ============== Example Node Implementations ==============


async def increment_iteration(state: dict) -> dict:
    """Increment iteration counter"""
    return {
        "iteration_count": state.get("iteration_count", 0) + 1,
    }


async def track_node_execution(state: dict, node_name: str) -> dict:
    """Track node execution in state"""
    nodes = state.get("nodes_executed", [])
    return {
        "nodes_executed": nodes + [node_name],
        "current_node": node_name,
    }


async def set_status(state: dict, status: str, message: str = None) -> dict:
    """Set workflow status"""
    result = {"status": status}
    if message:
        result["error"] = message if status == "failed" else None
    return result
