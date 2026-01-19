"""
Detect Node

Check flap detection results, decide whether to proceed or dampen.
From DESIGN.md: detect -> assess | dampen
"""

from typing import Any
import structlog

from ..tools.state_manager import update_incident

logger = structlog.get_logger(__name__)


async def detect_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Detect Node - Check flap detection, deduplicate.

    Actions:
    1. Check if link is flapping (from Event Correlator response)
    2. If flapping, route to dampen node
    3. If stable, proceed to assess node

    Args:
        state: Current workflow state

    Returns:
        Updated state with detection decision
    """
    incident_id = state.get("incident_id")

    logger.info(
        "Running detect node",
        incident_id=incident_id,
    )

    # Get correlation results
    correlator_response = state.get("a2a_responses", {}).get("event_correlator", {})
    is_flapping = correlator_response.get("is_flapping", False)
    alert_count = correlator_response.get("alert_count", 1)

    # Update Redis state
    await update_incident(
        incident_id=incident_id,
        updates={
            "status": "detecting",
            "is_flapping": is_flapping,
            "alert_count": alert_count,
        },
    )

    updates = {
        "current_node": "detect",
        "nodes_executed": state.get("nodes_executed", []) + ["detect"],
        "is_flapping": is_flapping,
        "alert_count": alert_count,
    }

    if is_flapping:
        logger.warning(
            "Link flapping detected, will dampen",
            incident_id=incident_id,
            alert_count=alert_count,
        )
        updates["status"] = "dampening"
    else:
        logger.info(
            "Link stable, proceeding to assess",
            incident_id=incident_id,
        )
        updates["status"] = "assessing"

    return updates
