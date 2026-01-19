"""
Dedup Node

Check for duplicate alerts within time window.
From DESIGN.md: dedup -> correlate | discard
"""

from typing import Any
import structlog

from ..tools.dedup_checker import get_dedup_checker

logger = structlog.get_logger(__name__)


async def dedup_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Dedup Node - Check for duplicate alerts.

    Actions:
    1. Compute dedup hash for normalized alert
    2. Check Redis for existing alert with same hash
    3. If duplicate, route to discard
    4. If new, record and route to correlate

    Args:
        state: Current workflow state

    Returns:
        Updated state with dedup result
    """
    normalized_alert = state.get("normalized_alert", {})
    alert_id = normalized_alert.get("alert_id")

    logger.info(
        "Checking for duplicate",
        alert_id=alert_id,
    )

    checker = get_dedup_checker()

    # Check for duplicate
    is_duplicate, duplicate_of = await checker.check_duplicate(normalized_alert)

    if is_duplicate:
        logger.info(
            "Duplicate alert detected",
            alert_id=alert_id,
            duplicate_of=duplicate_of,
        )
        return {
            "current_node": "dedup",
            "nodes_executed": state.get("nodes_executed", []) + ["dedup"],
            "is_duplicate": True,
            "duplicate_of": duplicate_of,
        }

    # Record alert for future dedup
    await checker.record_alert(normalized_alert)

    logger.info(
        "Alert is not duplicate, proceeding to correlate",
        alert_id=alert_id,
    )

    return {
        "current_node": "dedup",
        "nodes_executed": state.get("nodes_executed", []) + ["dedup"],
        "is_duplicate": False,
        "duplicate_of": None,
    }
