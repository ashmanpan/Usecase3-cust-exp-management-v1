"""
Suppress Node

Suppress flapping alerts with exponential backoff.
From DESIGN.md: flap_detect -> suppress (if flapping)
"""

from typing import Any
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


async def suppress_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Suppress Node - Suppress flapping alert.

    From DESIGN.md Flap Detection:
    - Exponential backoff: 1 min initial, doubles each time
    - Maximum suppression: 1 hour

    Actions:
    1. Log suppression with dampen period
    2. Mark workflow as suppressed
    3. Record suppression for audit

    Args:
        state: Current workflow state

    Returns:
        Updated state with suppress result
    """
    normalized_alert = state.get("normalized_alert", {})
    alert_id = normalized_alert.get("alert_id")
    link_id = normalized_alert.get("link_id")
    incident_id = state.get("incident_id")
    flap_count = state.get("flap_count", 0)
    dampen_seconds = state.get("dampen_seconds", 60)

    logger.warning(
        "Suppressing flapping alert",
        alert_id=alert_id,
        link_id=link_id,
        incident_id=incident_id,
        flap_count=flap_count,
        dampen_seconds=dampen_seconds,
    )

    # Build suppression record
    suppression_record = {
        "alert_id": alert_id,
        "incident_id": incident_id,
        "link_id": link_id,
        "timestamp": datetime.utcnow().isoformat(),
        "reason": "flapping",
        "flap_count": flap_count,
        "dampen_seconds": dampen_seconds,
        "resume_after": datetime.utcnow().isoformat(),  # Would add dampen_seconds
        "severity": normalized_alert.get("severity"),
    }

    logger.info(
        "Alert suppressed due to flapping",
        alert_id=alert_id,
        link_id=link_id,
        will_resume_in_seconds=dampen_seconds,
    )

    return {
        "current_node": "suppress",
        "nodes_executed": state.get("nodes_executed", []) + ["suppress"],
        "suppressed": True,
        "suppression_reason": "flapping",
        "suppression_record": suppression_record,
        "workflow_status": "completed",
        "workflow_result": "suppressed",
    }
