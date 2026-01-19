"""
Build Constraints Node

Build avoidance constraints for path computation.
From DESIGN.md: build_constraints -> query_kg
"""

from typing import Any
import structlog

from ..tools.constraint_builder import get_constraint_builder

logger = structlog.get_logger(__name__)


async def build_constraints_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Build Constraints Node - Create path constraints.

    From DESIGN.md:
    - Build avoidance constraints (links, nodes, SRLGs)
    - Include disjointness from existing policies

    Args:
        state: Current workflow state

    Returns:
        Updated state with constraints
    """
    incident_id = state.get("incident_id")
    degraded_links = state.get("degraded_links", [])
    avoid_nodes = state.get("avoid_nodes", [])
    avoid_srlgs = state.get("avoid_srlgs", [])
    existing_policies = state.get("existing_policies", [])
    required_sla = state.get("required_sla", {})
    current_te_type = state.get("current_te_type", "sr-mpls")

    logger.info(
        "Building path constraints",
        incident_id=incident_id,
        degraded_links=len(degraded_links),
    )

    builder = get_constraint_builder()

    # Build initial constraints
    constraints = builder.build_constraints(
        degraded_links=degraded_links,
        avoid_nodes=avoid_nodes,
        avoid_srlgs=avoid_srlgs,
        existing_policies=existing_policies,
        required_sla=required_sla,
        te_type=current_te_type,
    )

    # Convert to dict for state
    constraints_dict = constraints.model_dump()

    logger.info(
        "Constraints built",
        incident_id=incident_id,
        avoid_links=len(constraints.avoid_links),
        metric=constraints.optimization_metric,
    )

    return {
        "current_node": "build_constraints",
        "nodes_executed": state.get("nodes_executed", []) + ["build_constraints"],
        "constraints": constraints_dict,
        "original_constraints": constraints_dict.copy(),
        "relaxation_level": 0,
    }
