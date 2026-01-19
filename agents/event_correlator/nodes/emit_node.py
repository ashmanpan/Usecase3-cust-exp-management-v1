"""
Emit Node

Emit correlated incident to Orchestrator.
From DESIGN.md: flap_detect -> emit (if not flapping)
"""

from typing import Any
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


async def emit_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Emit Node - Emit incident to Orchestrator.

    Actions:
    1. Build incident payload from correlated alerts
    2. Determine severity (highest from correlated alerts)
    3. Mark ready for emission to Orchestrator
    4. Complete workflow

    Args:
        state: Current workflow state

    Returns:
        Updated state with emit result
    """
    normalized_alert = state.get("normalized_alert", {})
    alert_id = normalized_alert.get("alert_id")
    incident_id = state.get("incident_id")
    correlated_alerts = state.get("correlated_alerts", [])
    degraded_links = state.get("degraded_links", [])

    logger.info(
        "Emitting incident",
        alert_id=alert_id,
        incident_id=incident_id,
        correlated_alert_count=len(correlated_alerts),
        degraded_link_count=len(degraded_links),
    )

    # Build incident payload for Orchestrator
    incident_payload = {
        "incident_id": incident_id,
        "timestamp": datetime.utcnow().isoformat(),
        "source_alert": alert_id,
        "alert_type": _determine_alert_type(normalized_alert),
        "severity": normalized_alert.get("severity", "warning"),
        "degraded_links": degraded_links or [normalized_alert.get("link_id")],
        "correlated_alerts": correlated_alerts,
        "correlation_rule": state.get("correlation_rule"),
        "correlation_reason": state.get("correlation_reason"),
        "alert_count": state.get("alert_count", 1),
        "metrics": {
            "latency_ms": normalized_alert.get("latency_ms"),
            "jitter_ms": normalized_alert.get("jitter_ms"),
            "packet_loss_pct": normalized_alert.get("packet_loss_pct"),
        },
        "violated_thresholds": normalized_alert.get("violated_thresholds", []),
        "is_new_incident": state.get("is_new_incident", True),
    }

    logger.info(
        "Incident ready for Orchestrator",
        incident_id=incident_id,
        alert_type=incident_payload["alert_type"],
        severity=incident_payload["severity"],
    )

    return {
        "current_node": "emit",
        "nodes_executed": state.get("nodes_executed", []) + ["emit"],
        "emitted": True,
        "incident_payload": incident_payload,
        "workflow_status": "completed",
        "workflow_result": "emitted",
    }


def _determine_alert_type(alert: dict) -> str:
    """Determine alert type from normalized alert."""
    source = alert.get("source", "unknown")

    if source == "pca":
        return "pca_sla"
    elif source == "cnc":
        return "cnc_alarm"
    elif source == "proactive":
        return "proactive"
    else:
        return "unknown"
