"""Notification Workflow - From DESIGN.md"""
from typing import Any, Optional
import structlog
from langgraph.graph import StateGraph, START, END
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from agent_template.workflow import BaseWorkflow
from agent_template.tools.mcp_client import MCPToolClient
from agent_template.tools.a2a_client import A2AClient
from .schemas.state import NotificationState
from .nodes import (
    select_channels_node,
    format_message_node,
    send_parallel_node,
    log_results_node,
    return_notification_node,
)

logger = structlog.get_logger(__name__)


class NotificationWorkflow(BaseWorkflow):
    """
    Notification Workflow - From DESIGN.md
    Flow: SELECT_CHANNELS -> FORMAT_MESSAGE -> SEND_PARALLEL -> LOG_RESULTS
    """

    def __init__(
        self,
        agent_name: str = "notification",
        agent_version: str = "1.0.0",
        mcp_client: Optional[MCPToolClient] = None,
        a2a_client: Optional[A2AClient] = None,
        max_iterations: int = 5,
        stage_tools: dict[str, list[str]] = None,
    ):
        super().__init__(
            agent_name,
            agent_version,
            mcp_client,
            a2a_client,
            max_iterations,
            stage_tools,
        )

    def get_state_class(self) -> type:
        return NotificationState

    def get_initial_state(
        self,
        task_id: str,
        task_type: str,
        incident_id: Optional[str] = None,
        payload: dict[str, Any] = None,
        correlation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        base = super().get_initial_state(task_id, task_type, incident_id, payload, correlation_id)
        payload = payload or {}

        return {
            **base,
            # Notification request
            "event_type": payload.get("event_type", "incident_detected"),
            "severity": payload.get("severity", "medium"),
            "sla_tier": payload.get("sla_tier", "silver"),
            "notification_data": payload.get("data", {}),
            # Channel selection state
            "selected_channels": [],
            "webex_space": None,
            "servicenow_assignment": None,
            "email_recipients": [],
            # Message formatting state
            "message_subject": None,
            "message_body": None,
            "message_formatted": False,
            # Send state per channel
            "webex_sent": False,
            "webex_message_id": None,
            "servicenow_sent": False,
            "servicenow_ticket": None,
            "email_sent": False,
            "email_sent_to": [],
            # Results
            "channels_attempted": [],
            "channels_succeeded": [],
            "channels_failed": [],
            "channel_results": [],
            # Workflow tracking
            "iteration": 0,
            "stage": "init",
            "status": "pending",
            "error": None,
            # Result
            "result": None,
        }

    def build_graph(self, graph: StateGraph) -> None:
        """Build the notification workflow graph - From DESIGN.md"""

        # Add all nodes
        graph.add_node("select_channels", select_channels_node)
        graph.add_node("format_message", format_message_node)
        graph.add_node("send_parallel", send_parallel_node)
        graph.add_node("log_results", log_results_node)
        graph.add_node("return_notification", return_notification_node)

        # Linear flow
        graph.add_edge(START, "select_channels")
        graph.add_edge("select_channels", "format_message")
        graph.add_edge("format_message", "send_parallel")
        graph.add_edge("send_parallel", "log_results")
        graph.add_edge("log_results", "return_notification")
        graph.add_edge("return_notification", END)

        logger.info("Notification workflow graph built")
