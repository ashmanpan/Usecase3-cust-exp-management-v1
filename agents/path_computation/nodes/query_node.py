"""
Query KG Node

Query Knowledge Graph Dijkstra API for path computation.
From DESIGN.md: build_constraints -> query_kg -> validate_path
"""

from typing import Any
import structlog

from ..tools.kg_client import get_kg_client
from ..schemas.paths import PathConstraints

logger = structlog.get_logger(__name__)


async def query_kg_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Query KG Node - Compute path via Knowledge Graph.

    From DESIGN.md:
    - Call KG Dijkstra API with constraints
    - Return computed path or null

    Args:
        state: Current workflow state

    Returns:
        Updated state with computed path
    """
    incident_id = state.get("incident_id")
    source_pe = state.get("source_pe")
    destination_pe = state.get("destination_pe")
    constraints_dict = state.get("constraints", {})
    query_attempts = state.get("query_attempts", 0) + 1

    logger.info(
        "Querying KG for path",
        incident_id=incident_id,
        source=source_pe,
        destination=destination_pe,
        attempt=query_attempts,
    )

    if not source_pe or not destination_pe:
        logger.error(
            "Missing source or destination",
            incident_id=incident_id,
        )
        return {
            "current_node": "query_kg",
            "nodes_executed": state.get("nodes_executed", []) + ["query_kg"],
            "path_found": False,
            "computed_path": None,
            "query_attempts": query_attempts,
            "query_errors": state.get("query_errors", []) + ["Missing source or destination PE"],
        }

    try:
        # Convert dict to PathConstraints
        constraints = PathConstraints(**constraints_dict)

        client = get_kg_client()

        # Compute path
        path = await client.compute_path(
            source=source_pe,
            destination=destination_pe,
            constraints=constraints,
        )

        if path:
            # Add relaxation info if constraints were relaxed
            relaxation_level = state.get("relaxation_level", 0)
            path.constraints_relaxed = relaxation_level > 0
            path.relaxation_level = relaxation_level

            logger.info(
                "Path computed successfully",
                incident_id=incident_id,
                path_id=path.path_id,
                hops=path.total_hops,
                delay_ms=path.total_delay_ms,
            )

            return {
                "current_node": "query_kg",
                "nodes_executed": state.get("nodes_executed", []) + ["query_kg"],
                "path_found": True,
                "computed_path": path.model_dump(),
                "query_attempts": query_attempts,
            }
        else:
            logger.warning(
                "No path found",
                incident_id=incident_id,
                source=source_pe,
                destination=destination_pe,
            )
            return {
                "current_node": "query_kg",
                "nodes_executed": state.get("nodes_executed", []) + ["query_kg"],
                "path_found": False,
                "computed_path": None,
                "query_attempts": query_attempts,
            }

    except Exception as e:
        logger.error(
            "KG query failed",
            incident_id=incident_id,
            error=str(e),
        )
        return {
            "current_node": "query_kg",
            "nodes_executed": state.get("nodes_executed", []) + ["query_kg"],
            "path_found": False,
            "computed_path": None,
            "query_attempts": query_attempts,
            "query_errors": state.get("query_errors", []) + [str(e)],
        }
