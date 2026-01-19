"""
Correlate Node

Group related alerts using correlation rules.
From DESIGN.md: dedup -> correlate -> flap_detect
"""

from typing import Any
import structlog

from ..tools.correlator import get_correlator

logger = structlog.get_logger(__name__)


async def correlate_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Correlate Node - Group related alerts.

    Actions:
    1. Apply correlation rules from DESIGN.md
    2. Check for same_link_multiple_metrics
    3. Check for adjacent_link_failures
    4. Check for path_correlation
    5. Create or update incident

    Args:
        state: Current workflow state

    Returns:
        Updated state with correlation result
    """
    normalized_alert = state.get("normalized_alert", {})
    alert_id = normalized_alert.get("alert_id")
    link_id = normalized_alert.get("link_id")

    logger.info(
        "Correlating alert",
        alert_id=alert_id,
        link_id=link_id,
    )

    correlator = get_correlator()

    # Apply correlation rules
    result = await correlator.correlate(normalized_alert)

    logger.info(
        "Correlation complete",
        alert_id=alert_id,
        incident_id=result.get("incident_id"),
        is_new_incident=result.get("is_new_incident"),
        correlation_rule=result.get("correlation_rule"),
        alert_count=result.get("alert_count"),
    )

    return {
        "current_node": "correlate",
        "nodes_executed": state.get("nodes_executed", []) + ["correlate"],
        "incident_id": result.get("incident_id"),
        "is_new_incident": result.get("is_new_incident", True),
        "correlated_alerts": result.get("correlated_alerts", [alert_id]),
        "correlation_rule": result.get("correlation_rule"),
        "correlation_reason": result.get("correlation_reason"),
        "degraded_links": result.get("degraded_links", []),
        "alert_count": result.get("alert_count", 1),
    }
