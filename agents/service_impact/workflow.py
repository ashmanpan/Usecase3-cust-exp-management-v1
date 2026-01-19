"""
Service Impact Workflow

LangGraph workflow for querying CNC Service Health and assessing impact.
From DESIGN.md: QUERY_SERVICES -> ANALYZE_IMPACT -> ENRICH_SLA -> RETURN_AFFECTED
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

from .schemas.state import ServiceImpactState
from .nodes import (
    query_services_node,
    analyze_impact_node,
    enrich_sla_node,
    return_affected_node,
)

logger = structlog.get_logger(__name__)


class ServiceImpactWorkflow(BaseWorkflow):
    """
    Service Impact Workflow

    From DESIGN.md workflow:
    - QUERY_SERVICES: Call CNC Service Health API
    - ANALYZE_IMPACT: Determine impact severity
    - ENRICH_SLA: Add SLA tier info and priority
    - RETURN_AFFECTED: Return sorted list to Orchestrator
    """

    def __init__(
        self,
        agent_name: str = "service_impact",
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
        """Return ServiceImpactState TypedDict"""
        return ServiceImpactState

    def get_initial_state(
        self,
        task_id: str,
        task_type: str,
        incident_id: Optional[str] = None,
        payload: dict[str, Any] = None,
        correlation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create initial state for service impact assessment."""
        base_state = super().get_initial_state(
            task_id=task_id,
            task_type=task_type,
            incident_id=incident_id,
            payload=payload,
            correlation_id=correlation_id,
        )

        # Extract input from payload
        payload = payload or {}

        return {
            **base_state,
            # Input from Orchestrator
            "degraded_links": payload.get("degraded_links", []),
            "severity": payload.get("severity", "warning"),
            # Will be populated by nodes
            "raw_services": [],
            "query_success": False,
            "query_error": None,
            "impact_assessment": {},
            "total_affected": 0,
            "services_by_tier": {},
            "services_by_type": {},
            "affected_services": [],
            "highest_priority_tier": None,
            "auto_protect_required": False,
        }

    def build_graph(self, graph: StateGraph) -> None:
        """
        Build Service Impact workflow graph.

        From DESIGN.md:
        QUERY_SERVICES -> ANALYZE_IMPACT -> ENRICH_SLA -> RETURN_AFFECTED
        """
        # Add nodes
        graph.add_node("query_services", query_services_node)
        graph.add_node("analyze_impact", analyze_impact_node)
        graph.add_node("enrich_sla", enrich_sla_node)
        graph.add_node("return_affected", return_affected_node)

        # Entry point
        graph.add_edge(START, "query_services")

        # Linear flow
        graph.add_edge("query_services", "analyze_impact")
        graph.add_edge("analyze_impact", "enrich_sla")
        graph.add_edge("enrich_sla", "return_affected")

        # Terminal
        graph.add_edge("return_affected", END)

        logger.info("Service Impact workflow graph built")
