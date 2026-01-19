"""
Relax Constraints Node

Relax constraints to find a path when strict constraints fail.
From DESIGN.md: validate_path -> relax_constraints -> query_kg (retry loop)
"""

from typing import Any
import structlog

from ..tools.constraint_builder import get_constraint_builder
from ..schemas.paths import PathConstraints

logger = structlog.get_logger(__name__)


async def relax_constraints_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Relax Constraints Node - Relax constraints for retry.

    From DESIGN.md:
    - Remove less critical constraints
    - Relaxation order: SRLGs, max_hops, metric, avoid_nodes
    - Never relax: avoid_links (degraded links)

    Args:
        state: Current workflow state

    Returns:
        Updated state with relaxed constraints
    """
    incident_id = state.get("incident_id")
    constraints_dict = state.get("constraints", {})
    current_level = state.get("relaxation_level", 0)
    new_level = current_level + 1

    logger.info(
        "Relaxing constraints",
        incident_id=incident_id,
        current_level=current_level,
        new_level=new_level,
    )

    builder = get_constraint_builder()

    # Check if we can relax further
    if not builder.can_relax_further(current_level):
        logger.warning(
            "Max relaxation level reached",
            incident_id=incident_id,
            level=current_level,
        )
        return {
            "current_node": "relax_constraints",
            "nodes_executed": state.get("nodes_executed", []) + ["relax_constraints"],
            "relaxation_level": new_level,
            # Keep constraints unchanged
        }

    # Convert dict to PathConstraints
    constraints = PathConstraints(**constraints_dict)

    # Relax constraints
    relaxed = builder.relax_constraints(constraints, new_level)

    logger.info(
        "Constraints relaxed",
        incident_id=incident_id,
        level=new_level,
        avoid_srlgs=len(relaxed.avoid_srlgs),
        max_hops=relaxed.max_hops,
        metric=relaxed.optimization_metric,
    )

    return {
        "current_node": "relax_constraints",
        "nodes_executed": state.get("nodes_executed", []) + ["relax_constraints"],
        "constraints": relaxed.model_dump(),
        "relaxation_level": new_level,
    }
