"""Check Recovery Node - From DESIGN.md check_recovery"""
from typing import Any
import structlog

logger = structlog.get_logger(__name__)


async def check_recovery_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Compare metrics against SLA thresholds.
    From DESIGN.md: check_recovery compares metrics against SLA thresholds.
    Output: Recovered/Degraded
    """
    incident_id = state.get("incident_id")
    sla_recovered = state.get("sla_recovered", False)
    current_metrics = state.get("current_metrics", {})

    logger.info(
        "Checking recovery status",
        incident_id=incident_id,
        sla_recovered=sla_recovered,
        metrics=current_metrics,
    )

    if sla_recovered:
        logger.info(
            "SLA recovered - proceeding to hold timer",
            incident_id=incident_id,
        )
        return {
            "stage": "check_recovery",
            "status": "hold_timer",
        }
    else:
        # SLA still degraded - continue monitoring
        logger.info(
            "SLA still degraded - continuing to monitor",
            incident_id=incident_id,
            latency_ms=current_metrics.get("latency_ms"),
        )
        return {
            "stage": "check_recovery",
            "status": "monitoring",
        }
