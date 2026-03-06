"""Check Recovery Node - From DESIGN.md check_recovery"""
from typing import Any, List
import structlog

from ..tools.service_health_client import get_service_health_client

logger = structlog.get_logger(__name__)


async def check_recovery_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Compare metrics against SLA thresholds and check for actively impacted services.

    From DESIGN.md: check_recovery compares metrics against SLA thresholds.
    Output: Recovered/Degraded

    Recovery logic:
      - sla_recovered=True  AND  no impacted services  → status="hold_timer"
      - sla_recovered=True  BUT  services still impacted → status="monitoring"
      - sla_recovered=False                             → status="monitoring"

    Falls back to sla_recovered-only decision if get_impacted_services raises.
    """
    incident_id = state.get("incident_id")
    sla_recovered = state.get("sla_recovered", False)
    current_metrics = state.get("current_metrics", {})
    transport_ids: List[str] = state.get("transport_ids") or []

    logger.info(
        "Checking recovery status",
        incident_id=incident_id,
        sla_recovered=sla_recovered,
        metrics=current_metrics,
        transport_ids=transport_ids,
    )

    # ------------------------------------------------------------------
    # Query impacted services via Service Health API
    # ------------------------------------------------------------------
    impacted_services: List[dict] = []

    if transport_ids:
        sh = get_service_health_client()
        try:
            impacted_services = await sh.get_impacted_services(transport_ids)
            logger.info(
                "Impacted services check complete",
                incident_id=incident_id,
                impacted_service_count=len(impacted_services),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "get_impacted_services failed - falling back to sla_recovered only",
                incident_id=incident_id,
                error=str(exc),
            )
            # impacted_services stays [] so recovery decision falls through to
            # the sla_recovered-only path below.
    else:
        logger.info(
            "No transport_ids provided - skipping impacted services check",
            incident_id=incident_id,
        )

    impacted_service_count: int = len(impacted_services)
    impacted_service_ids: List[str] = [
        svc.get("serviceId", "") for svc in impacted_services if svc.get("serviceId")
    ]

    # ------------------------------------------------------------------
    # Recovery decision
    # ------------------------------------------------------------------
    if sla_recovered and impacted_service_count == 0:
        logger.info(
            "SLA recovered and no impacted services - proceeding to hold timer",
            incident_id=incident_id,
        )
        status = "hold_timer"
    elif sla_recovered and impacted_service_count > 0:
        logger.info(
            "SLA recovered but services still showing impact - continuing to monitor",
            incident_id=incident_id,
            impacted_service_count=impacted_service_count,
            impacted_service_ids=impacted_service_ids,
        )
        status = "monitoring"
    else:
        # sla_recovered=False
        logger.info(
            "SLA still degraded - continuing to monitor",
            incident_id=incident_id,
            latency_ms=current_metrics.get("latency_ms"),
            impacted_service_count=impacted_service_count,
        )
        status = "monitoring"

    return {
        "stage": "check_recovery",
        "status": status,
        "impacted_service_count": impacted_service_count,
        "impacted_service_ids": impacted_service_ids,
    }
