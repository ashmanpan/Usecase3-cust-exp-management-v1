"""Analyze Risk Node - From DESIGN.md analyze_risk"""
from typing import Any
import structlog

from ..schemas.analytics import CongestionRisk
from ..tools.alert_emitter import get_alert_emitter

logger = structlog.get_logger(__name__)


async def analyze_risk_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Determine risk level and affected services.
    From DESIGN.md: analyze_risk determines risk level and affected services.
    """
    task_id = state.get("task_id")
    risks_data = state.get("congestion_risks", [])
    high_risk_count = state.get("high_risk_count", 0)
    medium_risk_count = state.get("medium_risk_count", 0)

    logger.info(
        "Analyzing risk",
        task_id=task_id,
        high_risk_count=high_risk_count,
        medium_risk_count=medium_risk_count,
    )

    try:
        # Convert dict back to CongestionRisk objects
        risks = [CongestionRisk(**r) for r in risks_data]

        # Determine overall risk level - From DESIGN.md
        if high_risk_count > 0:
            risk_level = "high"
        elif medium_risk_count > 0:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Get affected services and SLA tier
        alert_emitter = get_alert_emitter()
        at_risk_services, highest_sla_tier = await alert_emitter.get_affected_services(risks)

        # Get at-risk links
        at_risk_links = [r.link_id for r in risks if r.risk_level in ("high", "medium")]

        # Determine recommended action - From DESIGN.md
        if risk_level == "high":
            recommended_action = "pre_provision_tunnel"
            time_to_congestion = 15
        elif risk_level == "medium":
            recommended_action = "load_balance"
            time_to_congestion = 30
        else:
            recommended_action = "alert_only"
            time_to_congestion = None

        logger.info(
            "Risk analysis complete",
            risk_level=risk_level,
            at_risk_links=len(at_risk_links),
            at_risk_services=len(at_risk_services),
            recommended_action=recommended_action,
        )

        return {
            "risk_level": risk_level,
            "at_risk_links": at_risk_links,
            "at_risk_services": at_risk_services,
            "highest_sla_tier": highest_sla_tier,
            "time_to_congestion_minutes": time_to_congestion,
            "recommended_action": recommended_action,
            "stage": "analyze_risk",
            "status": "analyzing",
        }

    except Exception as e:
        logger.error("Failed to analyze risk", error=str(e), task_id=task_id)
        return {
            "risk_level": "low",
            "stage": "analyze_risk",
            "error": f"Risk analysis failed: {str(e)}",
        }
