"""
Path Computation Workflow

LangGraph workflow for computing alternate paths via Knowledge Graph.
From DESIGN.md: BUILD_CONSTRAINTS -> QUERY_KG -> VALIDATE_PATH -> RETURN_PATH
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

from .schemas.state import PathComputationState
from .nodes import (
    build_constraints_node,
    query_kg_node,
    validate_path_node,
    relax_constraints_node,
    return_path_node,
    check_path_found,
    check_path_valid,
    check_can_relax,
)

logger = structlog.get_logger(__name__)


class PathComputationWorkflow(BaseWorkflow):
    """
    Path Computation Workflow

    From DESIGN.md workflow:
    - BUILD_CONSTRAINTS: Build avoidance constraints
    - QUERY_KG: Call KG Dijkstra API
    - VALIDATE_PATH: Check SLA requirements
    - RELAX_CONSTRAINTS: Progressive relaxation
    - RETURN_PATH: Return computed path
    """

    def __init__(
        self,
        agent_name: str = "path_computation",
        agent_version: str = "1.0.0",
        mcp_client: Optional[MCPToolClient] = None,
        a2a_client: Optional[A2AClient] = None,
        max_iterations: int = 5,
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
        """Return PathComputationState TypedDict"""
        return PathComputationState

    def get_initial_state(
        self,
        task_id: str,
        task_type: str,
        incident_id: Optional[str] = None,
        payload: dict[str, Any] = None,
        correlation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create initial state for path computation."""
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
            "source_pe": payload.get("source_pe"),
            "destination_pe": payload.get("destination_pe"),
            "degraded_links": payload.get("degraded_links", []),
            "avoid_nodes": payload.get("avoid_nodes", []),
            "avoid_srlgs": payload.get("avoid_srlgs", []),
            "service_sla_tier": payload.get("service_sla_tier", "silver"),
            "current_te_type": payload.get("current_te_type", "sr-mpls"),
            "existing_policies": payload.get("existing_policies", []),
            "required_sla": payload.get("required_sla", {}),
            # Will be populated by nodes
            "constraints": {},
            "original_constraints": {},
            "relaxation_level": 0,
            "path_found": False,
            "computed_path": None,
            "query_attempts": 0,
            "query_errors": [],
            "path_valid": False,
            "validation_violations": [],
        }

    def build_graph(self, graph: StateGraph) -> None:
        """
        Build Path Computation workflow graph.

        From DESIGN.md:
        BUILD_CONSTRAINTS -> QUERY_KG -> VALIDATE_PATH -> RETURN_PATH
        Or: QUERY_KG -> RELAX_CONSTRAINTS -> QUERY_KG (retry loop)
        """
        # Add nodes
        graph.add_node("build_constraints", build_constraints_node)
        graph.add_node("query_kg", query_kg_node)
        graph.add_node("validate_path", validate_path_node)
        graph.add_node("relax_constraints", relax_constraints_node)
        graph.add_node("return_path", return_path_node)

        # Entry point
        graph.add_edge(START, "build_constraints")

        # BUILD_CONSTRAINTS -> QUERY_KG
        graph.add_edge("build_constraints", "query_kg")

        # QUERY_KG -> VALIDATE_PATH | RELAX_CONSTRAINTS
        graph.add_conditional_edges(
            "query_kg",
            check_path_found,
            {
                "validate": "validate_path",
                "relax": "relax_constraints",
            }
        )

        # VALIDATE_PATH -> RETURN_PATH | RELAX_CONSTRAINTS
        graph.add_conditional_edges(
            "validate_path",
            check_path_valid,
            {
                "return": "return_path",
                "relax": "relax_constraints",
            }
        )

        # RELAX_CONSTRAINTS -> QUERY_KG | RETURN_PATH
        graph.add_conditional_edges(
            "relax_constraints",
            check_can_relax,
            {
                "query": "query_kg",
                "return": "return_path",
            }
        )

        # Terminal
        graph.add_edge("return_path", END)

        logger.info("Path Computation workflow graph built")
