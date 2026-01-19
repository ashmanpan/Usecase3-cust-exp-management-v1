"""
Event Correlator Workflow

LangGraph workflow implementing alert correlation, dedup, and flap detection.
From DESIGN.md: INGEST -> DEDUP -> CORRELATE -> FLAP_DETECT -> EMIT | SUPPRESS | DISCARD
"""

from typing import Any, Optional

import structlog
from langgraph.graph import StateGraph, START, END

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agent_template.workflow import BaseWorkflow
from agent_template.tools.mcp_client import MCPToolClient
from agent_template.tools.a2a_client import A2AClient

from .schemas.state import EventCorrelatorState
from .nodes import (
    ingest_node,
    dedup_node,
    correlate_node,
    flap_detect_node,
    emit_node,
    suppress_node,
    discard_node,
    check_duplicate,
    check_flap_status,
)

logger = structlog.get_logger(__name__)


class EventCorrelatorWorkflow(BaseWorkflow):
    """
    Event Correlator Workflow

    From DESIGN.md workflow:
    - INGEST: Parse and normalize alerts
    - DEDUP: Check for duplicates
    - CORRELATE: Group related alerts
    - FLAP_DETECT: Detect flapping links
    - EMIT: Emit incident to Orchestrator
    - SUPPRESS: Suppress flapping alerts
    - DISCARD: Discard duplicates
    """

    def __init__(
        self,
        agent_name: str = "event_correlator",
        agent_version: str = "1.0.0",
        mcp_client: Optional[MCPToolClient] = None,
        a2a_client: Optional[A2AClient] = None,
        max_iterations: int = 3,
        stage_tools: dict[str, list[str]] = None,
    ):
        super().__init__(
            agent_name=agent_name,
            agent_version=agent_version,
            mcp_client=mcp_client,
            a2a_client=a2a_client,
            max_iterations=max_iterations,
            stage_tools=stage_tools,
        )

    def get_state_class(self) -> type:
        """Return EventCorrelatorState TypedDict"""
        return EventCorrelatorState

    def get_initial_state(
        self,
        task_id: str,
        task_type: str,
        incident_id: Optional[str] = None,
        payload: dict[str, Any] = None,
        correlation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create initial state for event correlation."""
        base_state = super().get_initial_state(
            task_id=task_id,
            task_type=task_type,
            incident_id=incident_id,
            payload=payload,
            correlation_id=correlation_id,
        )

        # Extract alert data from payload
        payload = payload or {}

        return {
            **base_state,
            # Alert source info
            "alert_source": payload.get("source", "unknown"),
            "raw_alert": payload.get("alert", {}),
            # Will be populated by nodes
            "normalized_alert": None,
            "is_duplicate": False,
            "duplicate_of": None,
            "correlated_alerts": [],
            "is_flapping": False,
            "flap_count": 0,
            "dampen_seconds": 0,
            "degraded_links": [],
            "emitted": False,
            "suppressed": False,
            "discarded": False,
            "workflow_status": "running",
            "workflow_result": None,
        }

    def build_graph(self, graph: StateGraph) -> None:
        """
        Build Event Correlator workflow graph.

        From DESIGN.md:
        INGEST -> DEDUP -> CORRELATE -> FLAP_DETECT -> EMIT | SUPPRESS
        DEDUP -> DISCARD (if duplicate)
        FLAP_DETECT -> SUPPRESS (if flapping)
        """
        # Add nodes
        graph.add_node("ingest", ingest_node)
        graph.add_node("dedup", dedup_node)
        graph.add_node("correlate", correlate_node)
        graph.add_node("flap_detect", flap_detect_node)
        graph.add_node("emit", emit_node)
        graph.add_node("suppress", suppress_node)
        graph.add_node("discard", discard_node)

        # Entry point
        graph.add_edge(START, "ingest")

        # INGEST -> DEDUP
        graph.add_edge("ingest", "dedup")

        # DEDUP -> CORRELATE | DISCARD (conditional)
        graph.add_conditional_edges(
            "dedup",
            check_duplicate,
            {
                "correlate": "correlate",
                "discard": "discard",
            }
        )

        # CORRELATE -> FLAP_DETECT
        graph.add_edge("correlate", "flap_detect")

        # FLAP_DETECT -> EMIT | SUPPRESS (conditional)
        graph.add_conditional_edges(
            "flap_detect",
            check_flap_status,
            {
                "emit": "emit",
                "suppress": "suppress",
            }
        )

        # Terminal nodes
        graph.add_edge("emit", END)
        graph.add_edge("suppress", END)
        graph.add_edge("discard", END)

        logger.info("Event Correlator workflow graph built")
