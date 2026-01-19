"""Log Results Node - From DESIGN.md log_results"""
from typing import Any
import structlog

logger = structlog.get_logger(__name__)


async def log_results_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Record notification outcomes.
    From DESIGN.md: log_results records notification outcomes.
    """
    incident_id = state.get("incident_id", "UNKNOWN")
    event_type = state.get("event_type", "unknown")
    channels_attempted = state.get("channels_attempted", [])
    channels_succeeded = state.get("channels_succeeded", [])
    channels_failed = state.get("channels_failed", [])
    servicenow_ticket = state.get("servicenow_ticket")

    # Log summary
    logger.info(
        "Notification results",
        incident_id=incident_id,
        event_type=event_type,
        channels_attempted=channels_attempted,
        channels_succeeded=channels_succeeded,
        channels_failed=channels_failed,
        servicenow_ticket=servicenow_ticket,
    )

    # Log individual channel results
    for result in state.get("channel_results", []):
        if result.get("success"):
            logger.info(
                "Channel notification sent",
                channel=result.get("channel"),
                message_id=result.get("message_id"),
                ticket_number=result.get("ticket_number"),
            )
        else:
            logger.warning(
                "Channel notification failed",
                channel=result.get("channel"),
                error=result.get("error"),
            )

    return {
        "stage": "log_results",
        "status": "logging",
    }
