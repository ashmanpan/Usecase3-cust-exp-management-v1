"""Timer Nodes - From DESIGN.md start_timer and wait_timer"""
from typing import Any
from datetime import datetime
import asyncio
import structlog

from ..tools.hold_timer import get_hold_timer_manager

logger = structlog.get_logger(__name__)


async def start_timer_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Set hold timer in Redis (per SLA tier).
    From DESIGN.md: start_timer sets hold timer, returns Timer ID
    """
    incident_id = state.get("incident_id")
    sla_tier = state.get("sla_tier", "silver")
    recovery_time = state.get("recovery_time")

    logger.info(
        "Starting hold timer",
        incident_id=incident_id,
        sla_tier=sla_tier,
    )

    try:
        timer_manager = get_hold_timer_manager()

        recovery_dt = datetime.fromisoformat(recovery_time) if recovery_time else datetime.now()
        timer_id = await timer_manager.start_timer(
            incident_id=incident_id,
            sla_tier=sla_tier,
            recovery_time=recovery_dt,
        )

        # Get timer info for state
        timer_info = await timer_manager.get_timer_info(timer_id)
        hold_seconds = timer_info.get("hold_seconds", 180) if timer_info else 180

        logger.info(
            "Hold timer started",
            incident_id=incident_id,
            timer_id=timer_id,
            hold_seconds=hold_seconds,
        )

        return {
            "timer_id": timer_id,
            "timer_started": True,
            "timer_expired": False,
            "timer_cancelled": False,
            "stage": "start_timer",
            "status": "hold_timer",
        }

    except Exception as e:
        logger.error("Failed to start hold timer", error=str(e), incident_id=incident_id)
        return {
            "timer_started": False,
            "stage": "start_timer",
            "error": f"Timer start failed: {str(e)}",
        }


async def wait_timer_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Wait for hold timer expiration.
    From DESIGN.md: wait_timer waits for hold timer expiration.
    """
    incident_id = state.get("incident_id")
    timer_id = state.get("timer_id")

    if not timer_id:
        logger.warning("No timer ID found", incident_id=incident_id)
        return {
            "timer_expired": True,
            "stage": "wait_timer",
            "status": "verifying",
        }

    logger.info(
        "Waiting for hold timer",
        incident_id=incident_id,
        timer_id=timer_id,
    )

    try:
        timer_manager = get_hold_timer_manager()

        # Poll timer status (with timeout to prevent infinite loop)
        max_wait_seconds = 600  # 10 minute max wait
        poll_interval = 5  # Check every 5 seconds
        waited = 0

        while waited < max_wait_seconds:
            timer_status = await timer_manager.check_timer(timer_id)

            if timer_status.get("status") == "cancelled":
                logger.info(
                    "Hold timer was cancelled",
                    incident_id=incident_id,
                    timer_id=timer_id,
                )
                return {
                    "timer_expired": False,
                    "timer_cancelled": True,
                    "stage": "wait_timer",
                    "status": "monitoring",  # Go back to monitoring
                }

            if timer_status.get("expired"):
                logger.info(
                    "Hold timer expired",
                    incident_id=incident_id,
                    timer_id=timer_id,
                )
                return {
                    "timer_expired": True,
                    "timer_cancelled": False,
                    "stage": "wait_timer",
                    "status": "verifying",
                }

            remaining = timer_status.get("remaining_seconds", 0)
            logger.debug(
                "Timer still waiting",
                remaining_seconds=remaining,
            )

            await asyncio.sleep(min(poll_interval, remaining + 1))
            waited += poll_interval

        # Timeout reached - treat as expired
        logger.warning("Timer wait timeout reached", incident_id=incident_id)
        return {
            "timer_expired": True,
            "stage": "wait_timer",
            "status": "verifying",
        }

    except Exception as e:
        logger.error("Error waiting for timer", error=str(e), incident_id=incident_id)
        return {
            "timer_expired": True,  # Proceed on error
            "stage": "wait_timer",
            "error": f"Timer wait failed: {str(e)}",
        }
