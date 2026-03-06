"""
Query KG Node

Query Knowledge Graph Dijkstra API for path computation.
From DESIGN.md: build_constraints -> query_kg -> validate_path
"""

from typing import Any
import structlog

from ..tools.kg_client import get_kg_client
from ..tools.cnc_topology_client import get_cnc_topology_client
from ..tools.srpm_client import get_srpm_client
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

        # Step 1: Get live topology path hint from CNC
        topology_path_hint = []
        try:
            topo_client = get_cnc_topology_client()
            topology_path_hint = await topo_client.get_igp_path(source_pe, destination_pe)
            logger.info(
                "Topology path hint retrieved",
                incident_id=incident_id,
                hops=len(topology_path_hint),
            )
        except Exception as e:
            logger.warning(
                "Topology enrichment failed, continuing with KG only",
                incident_id=incident_id,
                error=str(e),
            )

        # Step 2: Get SR-PM path metrics for current path (if available)
        # Build segment_list from topology_path_hint link IDs when available
        srpm_metrics = {}
        try:
            srpm = get_srpm_client()
            segment_list = [
                hop["link_id"]
                for hop in topology_path_hint
                if hop.get("link_id")
            ]
            if segment_list:
                per_hop = await srpm.get_path_metrics(segment_list)
                srpm_metrics = {
                    "available": True,
                    "per_hop": per_hop,
                    "source_pe": source_pe,
                    "destination_pe": destination_pe,
                }
            else:
                logger.info(
                    "No segment_list available for SR-PM — skipping path metrics",
                    incident_id=incident_id,
                )
        except Exception as e:
            logger.warning(
                "SR-PM metrics unavailable",
                incident_id=incident_id,
                error=str(e),
            )

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
                "topology_path_hint": topology_path_hint,
                "srpm_metrics": srpm_metrics,
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
