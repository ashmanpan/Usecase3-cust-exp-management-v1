"""Return Restored Node - From DESIGN.md return_restored"""
from typing import Any
from datetime import datetime
import structlog

from ..schemas.restoration import RestorationResponse
from ..tools.hold_timer import SLA_TIER_CONFIG

logger = structlog.get_logger(__name__)


async def return_restored_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Notify Orchestrator restoration complete.
    From DESIGN.md: return_restored notifies Orchestrator, returns response.
    """
    incident_id = state.get("incident_id")
    sla_tier = state.get("sla_tier", "silver")
    cutover_mode = state.get("cutover_mode", "immediate")
    tunnel_deleted = state.get("tunnel_deleted", False)
    bsid_released = state.get("bsid_released")
    protection_start_time = state.get("protection_start_time")
    error = state.get("error")

    # Calculate total protection duration
    total_duration = 0.0
    if protection_start_time:
        try:
            start_dt = datetime.fromisoformat(protection_start_time)
            total_duration = (datetime.now() - start_dt).total_seconds()
        except Exception:
            pass

    # Get hold timer seconds for this tier
    hold_timer_seconds = SLA_TIER_CONFIG.get(sla_tier, SLA_TIER_CONFIG["silver"])["hold_timer_seconds"]

    # Determine if restoration was successful
    restored = (
        state.get("cutover_complete", False)
        and tunnel_deleted
        and not error
    )

    # Build response - From DESIGN.md A2A Task Schema
    response = RestorationResponse(
        incident_id=incident_id,
        restored=restored,
        hold_timer_seconds=hold_timer_seconds,
        cutover_mode=cutover_mode,
        tunnel_deleted=tunnel_deleted,
        bsid_released=bsid_released,
        total_protection_duration_seconds=total_duration,
        error=error,
    )

    logger.info(
        "Restoration workflow complete",
        incident_id=incident_id,
        restored=restored,
        total_protection_duration=total_duration,
        cutover_mode=cutover_mode,
    )

    return {
        "result": response.model_dump(),
        "stage": "return_restored",
        "status": "completed" if restored else "failed",
        "total_protection_duration_seconds": total_duration,
    }
