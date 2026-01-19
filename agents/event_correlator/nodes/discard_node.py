"""
Discard Node

Discard duplicate alerts.
From DESIGN.md: dedup -> discard (if duplicate)
"""

from typing import Any
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


async def discard_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Discard Node - Discard duplicate alert.

    Actions:
    1. Log discard reason
    2. Record duplicate detection for metrics
    3. Complete workflow without emission

    Args:
        state: Current workflow state

    Returns:
        Updated state with discard result
    """
    normalized_alert = state.get("normalized_alert", {})
    alert_id = normalized_alert.get("alert_id")
    duplicate_of = state.get("duplicate_of")

    logger.info(
        "Discarding duplicate alert",
        alert_id=alert_id,
        duplicate_of=duplicate_of,
    )

    # Build discard record
    discard_record = {
        "alert_id": alert_id,
        "timestamp": datetime.utcnow().isoformat(),
        "reason": "duplicate",
        "duplicate_of": duplicate_of,
        "link_id": normalized_alert.get("link_id"),
        "source": normalized_alert.get("source"),
    }

    logger.info(
        "Alert discarded as duplicate",
        alert_id=alert_id,
        duplicate_of=duplicate_of,
    )

    return {
        "current_node": "discard",
        "nodes_executed": state.get("nodes_executed", []) + ["discard"],
        "discarded": True,
        "discard_reason": "duplicate",
        "discard_record": discard_record,
        "workflow_status": "completed",
        "workflow_result": "discarded",
    }
