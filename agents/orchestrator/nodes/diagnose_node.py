"""
Diagnose Node - Pinpoint the specific degraded P-to-P link
from an overlay PE-to-PE PCA session degradation event.

Uses CNC Topology API to walk IGP path hops and identifies
which specific P-to-P link segment has elevated loss.

Background (GAP 5):
  When PCA reports PE-A -> PE-B overlay session packet loss, the agent
  only knows PE-A and PE-B have loss — it does NOT know which specific
  P-to-P link is degraded. This node walks the IGP path hop-by-hop via
  the CNC Topology API to collect all candidate P-to-P link IDs, which
  are then passed to the service_impact agent for correlation.

  Actual per-hop DPM counter checking will be added in a future
  DPM integration milestone.
"""

from typing import Any
import structlog

from agents.path_computation.tools.cnc_topology_client import get_cnc_topology_client

logger = structlog.get_logger(__name__)


async def diagnose_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Diagnose Node - Walk IGP path to identify candidate degraded P-to-P links.

    Actions:
    1. If degraded_links is already populated (P-to-P session, link known):
       skip diagnosis and return state unchanged with diagnosis_skipped=True.
    2. If pe_source and pe_destination are set and degraded_links is empty:
       - Call CNC Topology API to get hop-by-hop IGP path.
       - Collect all link_id values from the path hops.
       - Store as candidate_links in state for service_impact correlation.

    Args:
        state: Current workflow state

    Returns:
        Updated state dict with candidate_links, diagnosis_result,
        and nodes_executed updated.
    """
    incident_id = state.get("incident_id")
    pe_source = state.get("pe_source")
    pe_destination = state.get("pe_destination")
    degraded_links: list = state.get("degraded_links", [])
    alert_source = state.get("alert_source")

    logger.info(
        "Running diagnose node",
        incident_id=incident_id,
        pe_source=pe_source,
        pe_destination=pe_destination,
        degraded_links_count=len(degraded_links),
        alert_source=alert_source,
    )

    updates: dict[str, Any] = {
        "current_node": "diagnose",
        "nodes_executed": state.get("nodes_executed", []) + ["diagnose"],
    }

    # --- Case 1: Link already known (P-to-P session, not overlay) ---
    if degraded_links:
        logger.info(
            "Link already identified, skipping diagnosis",
            incident_id=incident_id,
            degraded_links=degraded_links,
        )
        updates["diagnosis_skipped"] = True
        return updates

    # --- Case 2: Overlay PE-to-PE session — walk IGP path ---
    if not pe_source or not pe_destination:
        logger.warning(
            "Cannot diagnose: pe_source or pe_destination missing in state",
            incident_id=incident_id,
            pe_source=pe_source,
            pe_destination=pe_destination,
        )
        updates["degraded_links"] = []
        updates["candidate_links"] = []
        updates["diagnosis_result"] = "missing_pe_endpoints"
        return updates

    topology_client = get_cnc_topology_client()
    path = await topology_client.get_igp_path(pe_source, pe_destination)

    if not path:
        logger.warning(
            "CNC Topology API returned no path",
            incident_id=incident_id,
            pe_source=pe_source,
            pe_destination=pe_destination,
        )
        updates["degraded_links"] = []
        updates["candidate_links"] = []
        updates["diagnosis_result"] = "no_path_found"
        return updates

    # Collect link_ids from all hops (some hops may not carry a link_id)
    candidate_links = [h.get("link_id") for h in path if h.get("link_id")]

    logger.info(
        "IGP path found",
        pe_source=pe_source,
        pe_destination=pe_destination,
        hop_count=len(path),
        links=candidate_links,
    )

    # candidate_links are passed to service_impact for correlation.
    # Per-hop DPM counter checks will be added in a future DPM integration.
    updates["candidate_links"] = candidate_links
    updates["diagnosis_result"] = "candidate_links_identified"

    return updates
