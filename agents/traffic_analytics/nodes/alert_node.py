"""Emit Proactive Alert Node - From DESIGN.md emit_proactive_alert"""
from typing import Any
import structlog

from ..schemas.analytics import CongestionRisk
from ..tools.alert_emitter import get_alert_emitter

logger = structlog.get_logger(__name__)


async def emit_proactive_alert_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Send PROACTIVE_ALERT to Orchestrator.
    From DESIGN.md: emit_proactive_alert sends alert to Orchestrator.
    """
    task_id = state.get("task_id")
    risks_data = state.get("congestion_risks", [])
    at_risk_services = state.get("at_risk_services", [])
    highest_sla_tier = state.get("highest_sla_tier", "silver")

    logger.info(
        "Emitting proactive alert",
        task_id=task_id,
        at_risk_services=len(at_risk_services),
        highest_sla_tier=highest_sla_tier,
    )

    try:
        # Convert dict back to CongestionRisk objects
        risks = [CongestionRisk(**r) for r in risks_data]

        # Emit alert
        alert_emitter = get_alert_emitter()
        alert = await alert_emitter.emit_proactive_alert(
            risks=risks,
            at_risk_services=at_risk_services,
            highest_sla_tier=highest_sla_tier,
        )

        logger.info(
            "Proactive alert emitted",
            alert_id=alert.alert_id,
            recommended_action=alert.recommended_action,
        )

        return {
            "proactive_alert_emitted": True,
            "alert_id": alert.alert_id,
            "sent_to_orchestrator": True,
            "stage": "emit_proactive_alert",
            "status": "alerting",
        }

    except Exception as e:
        logger.error("Failed to emit proactive alert", error=str(e), task_id=task_id)
        return {
            "proactive_alert_emitted": False,
            "stage": "emit_proactive_alert",
            "error": f"Alert emission failed: {str(e)}",
        }
