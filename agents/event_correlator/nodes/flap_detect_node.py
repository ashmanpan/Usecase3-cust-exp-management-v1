"""
Flap Detect Node

Detect flapping links using sliding window.
From DESIGN.md: correlate -> flap_detect -> emit | suppress
"""

from typing import Any
import structlog

from ..tools.flap_detector import get_flap_detector

logger = structlog.get_logger(__name__)


async def flap_detect_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Flap Detect Node - Check for flapping links.

    From DESIGN.md Flap Detection:
    - 5-minute sliding window
    - 3 state changes = flapping
    - Exponential backoff suppression (1 min initial, 1 hour max)

    Actions:
    1. Record state change for link
    2. Check if link is flapping
    3. Calculate dampen period if flapping
    4. Route to emit or suppress

    Args:
        state: Current workflow state

    Returns:
        Updated state with flap detection result
    """
    normalized_alert = state.get("normalized_alert", {})
    alert_id = normalized_alert.get("alert_id")
    link_id = normalized_alert.get("link_id")

    logger.info(
        "Checking for flapping",
        alert_id=alert_id,
        link_id=link_id,
    )

    if not link_id:
        logger.warning(
            "No link_id for flap detection, proceeding to emit",
            alert_id=alert_id,
        )
        return {
            "current_node": "flap_detect",
            "nodes_executed": state.get("nodes_executed", []) + ["flap_detect"],
            "is_flapping": False,
            "flap_count": 0,
            "dampen_seconds": 0,
        }

    detector = get_flap_detector()

    # Record state change
    await detector.record_state_change(link_id)

    # Check for flapping
    is_flapping, dampen_seconds = await detector.check_flapping(link_id)

    if is_flapping:
        flap_count = await detector.get_flap_count(link_id)
        logger.warning(
            "Link is flapping, will suppress",
            alert_id=alert_id,
            link_id=link_id,
            flap_count=flap_count,
            dampen_seconds=dampen_seconds,
        )
        return {
            "current_node": "flap_detect",
            "nodes_executed": state.get("nodes_executed", []) + ["flap_detect"],
            "is_flapping": True,
            "flap_count": flap_count,
            "dampen_seconds": dampen_seconds,
        }

    logger.info(
        "Link not flapping, proceeding to emit",
        alert_id=alert_id,
        link_id=link_id,
    )

    return {
        "current_node": "flap_detect",
        "nodes_executed": state.get("nodes_executed", []) + ["flap_detect"],
        "is_flapping": False,
        "flap_count": 0,
        "dampen_seconds": 0,
    }
