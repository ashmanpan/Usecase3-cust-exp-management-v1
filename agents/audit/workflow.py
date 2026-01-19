"""Audit Workflow - From DESIGN.md"""
from typing import Any, Optional
import structlog
from langgraph.graph import StateGraph, START, END
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from agent_template.workflow import BaseWorkflow
from agent_template.tools.mcp_client import MCPToolClient
from agent_template.tools.a2a_client import A2AClient
from .schemas.state import AuditState
from .nodes import (
    capture_event_node,
    format_log_node,
    store_db_node,
    index_async_node,
    return_audit_node,
)

logger = structlog.get_logger(__name__)


class AuditWorkflow(BaseWorkflow):
    """
    Audit Workflow - From DESIGN.md
    Flow: CAPTURE_EVENT -> FORMAT_LOG -> STORE_DB -> INDEX_ASYNC
    """

    def __init__(
        self,
        agent_name: str = "audit",
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
        return AuditState

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
            # Event data (populated by capture_event)
            "event_type": None,
            "agent_name": None,
            "node_name": None,
            "event_payload": {},
            "previous_state": None,
            "new_state": None,
            "decision_type": None,
            "decision_reasoning": None,
            "actor": "system",
            # Formatted log
            "event_id": None,
            "timestamp": None,
            "formatted_log": {},
            "log_formatted": False,
            # Storage state
            "db_stored": False,
            "db_store_error": None,
            # Index state
            "indexed": False,
            "index_error": None,
            "es_enabled": False,
            # Timeline query results
            "timeline_events": [],
            "timeline_count": 0,
            # Report results
            "report_start_date": payload.get("start_date"),
            "report_end_date": payload.get("end_date"),
            "report_data": {},
            # Workflow tracking
            "iteration": 0,
            "stage": "init",
            "status": "pending",
            "error": None,
            # Result
            "result": None,
        }

    def build_graph(self, graph: StateGraph) -> None:
        """Build the audit workflow graph - From DESIGN.md"""

        # Add all nodes
        graph.add_node("capture_event", capture_event_node)
        graph.add_node("format_log", format_log_node)
        graph.add_node("store_db", store_db_node)
        graph.add_node("index_async", index_async_node)
        graph.add_node("return_audit", return_audit_node)

        # Linear flow: CAPTURE -> FORMAT -> STORE -> INDEX -> RETURN
        graph.add_edge(START, "capture_event")
        graph.add_edge("capture_event", "format_log")
        graph.add_edge("format_log", "store_db")
        graph.add_edge("store_db", "index_async")
        graph.add_edge("index_async", "return_audit")
        graph.add_edge("return_audit", END)

        logger.info("Audit workflow graph built")
