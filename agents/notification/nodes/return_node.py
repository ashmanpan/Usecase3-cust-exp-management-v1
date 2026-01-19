"""Return Notification Node - Return final notification response"""
from typing import Any
import structlog

from ..schemas.notification import NotificationResponse

logger = structlog.get_logger(__name__)


async def return_notification_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Return final notification response.
    """
    incident_id = state.get("incident_id", "UNKNOWN")
    event_type = state.get("event_type", "unknown")
    error = state.get("error")

    # Build response - From DESIGN.md A2A Task Schema
    response = NotificationResponse(
        incident_id=incident_id,
        event_type=event_type,
        channels_attempted=state.get("channels_attempted", []),
        channels_succeeded=state.get("channels_succeeded", []),
        channels_failed=state.get("channels_failed", []),
        servicenow_ticket=state.get("servicenow_ticket"),
        webex_message_id=state.get("webex_message_id"),
        email_recipients=state.get("email_sent_to", []),
        error=error,
    )

    logger.info(
        "Notification workflow complete",
        incident_id=incident_id,
        channels_succeeded=len(response.channels_succeeded),
        channels_failed=len(response.channels_failed),
    )

    return {
        "result": response.model_dump(),
        "stage": "return_notification",
        "status": "completed" if not error else "failed",
    }
