"""
Orchestrator Workflow

LangGraph workflow implementing the orchestrator state machine.
Based on DESIGN.md state machine diagram.
"""

from typing import Any, Optional
from datetime import datetime

import structlog
from langgraph.graph import StateGraph, START, END

from agent_template.workflow import BaseWorkflow
from agent_template.tools.a2a_client import A2AClient, configure_a2a_client

from .schemas.state import OrchestratorState, create_initial_state
from .nodes import (
    start_node,
    detect_node,
    assess_node,
    compute_node,
    provision_node,
    steer_node,
    monitor_node,
    restore_node,
    dampen_node,
    escalate_node,
    close_node,
    check_flapping,
    check_services_affected,
    check_path_found,
    check_provision_success,
    check_steer_success,
    check_sla_recovered,
    check_restore_complete,
    check_dampen_complete,
)

logger = structlog.get_logger(__name__)


class OrchestratorWorkflow(BaseWorkflow):
    """
    Orchestrator Workflow

    State machine based supervisor that coordinates the protection workflow.
    From DESIGN.md:
    - START -> detect -> assess -> compute -> provision -> steer -> monitor -> restore -> close -> END
    - With branches: dampen (for flapping), escalate (for failures)
    """

    def __init__(
        self,
        agent_name: str = "orchestrator",
        agent_version: str = "1.0.0",
        a2a_client: Optional[A2AClient] = None,
        agent_registry: dict[str, str] = None,
        max_iterations: int = 10,
        **kwargs,
    ):
        """
        Initialize Orchestrator Workflow.

        Args:
            agent_name: Agent name
            agent_version: Agent version
            a2a_client: A2A client for inter-agent calls
            agent_registry: Dict of agent URLs
            max_iterations: Maximum workflow iterations
        """
        # Configure A2A client with agent registry
        if agent_registry:
            a2a_client = configure_a2a_client(agent_registry=agent_registry)

        super().__init__(
            agent_name=agent_name,
            agent_version=agent_version,
            a2a_client=a2a_client,
            max_iterations=max_iterations,
            **kwargs,
        )

    def get_state_class(self) -> type:
        """Return OrchestratorState TypedDict"""
        return OrchestratorState

    def build_graph(self, graph: StateGraph) -> None:
        """
        Build the orchestrator state machine graph.

        Based on DESIGN.md state machine diagram.
        """
        # Add all nodes
        graph.add_node("start", start_node)
        graph.add_node("detect", detect_node)
        graph.add_node("assess", assess_node)
        graph.add_node("compute", compute_node)
        graph.add_node("provision", provision_node)
        graph.add_node("steer", steer_node)
        graph.add_node("monitor", monitor_node)
        graph.add_node("restore", restore_node)
        graph.add_node("dampen", dampen_node)
        graph.add_node("escalate", escalate_node)
        graph.add_node("close", close_node)

        # Entry point
        graph.add_edge(START, "start")

        # start -> detect
        graph.add_edge("start", "detect")

        # detect -> assess | dampen
        graph.add_conditional_edges(
            "detect",
            check_flapping,
            {
                "assess": "assess",
                "dampen": "dampen",
            },
        )

        # assess -> compute | close
        graph.add_conditional_edges(
            "assess",
            check_services_affected,
            {
                "compute": "compute",
                "close": "close",
            },
        )

        # compute -> provision | escalate
        graph.add_conditional_edges(
            "compute",
            check_path_found,
            {
                "provision": "provision",
                "escalate": "escalate",
            },
        )

        # provision -> steer | provision (retry) | escalate
        graph.add_conditional_edges(
            "provision",
            check_provision_success,
            {
                "steer": "steer",
                "provision": "provision",
                "escalate": "escalate",
            },
        )

        # steer -> monitor | provision (retry)
        graph.add_conditional_edges(
            "steer",
            check_steer_success,
            {
                "monitor": "monitor",
                "provision": "provision",
            },
        )

        # monitor -> restore | monitor (continue)
        graph.add_conditional_edges(
            "monitor",
            check_sla_recovered,
            {
                "restore": "restore",
                "monitor": "monitor",
            },
        )

        # restore -> close | restore (gradual cutover)
        graph.add_conditional_edges(
            "restore",
            check_restore_complete,
            {
                "close": "close",
                "restore": "restore",
            },
        )

        # dampen -> detect
        graph.add_conditional_edges(
            "dampen",
            check_dampen_complete,
            {
                "detect": "detect",
            },
        )

        # escalate -> close
        graph.add_edge("escalate", "close")

        # close -> END
        graph.add_edge("close", END)

    def get_initial_state(
        self,
        task_id: str,
        task_type: str,
        incident_id: Optional[str] = None,
        payload: dict[str, Any] = None,
        correlation_id: Optional[str] = None,
    ) -> OrchestratorState:
        """
        Create initial state for orchestrator workflow.

        Args:
            task_id: Task identifier
            task_type: Task type (handle_alert)
            incident_id: Incident identifier
            payload: Alert payload with degraded_links, severity, alert_type
            correlation_id: Correlation ID for tracing

        Returns:
            Initial OrchestratorState
        """
        payload = payload or {}

        return create_initial_state(
            task_id=task_id,
            incident_id=incident_id or f"INC-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            alert_type=payload.get("alert_type", "pca_sla"),
            degraded_links=payload.get("degraded_links", []),
            severity=payload.get("severity", "major"),
            correlation_id=correlation_id,
        )
