"""Format Message Node - From DESIGN.md format_message"""
from typing import Any
import structlog

from ..tools.message_formatter import get_message_formatter

logger = structlog.get_logger(__name__)


async def format_message_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Generate message from template.
    From DESIGN.md: format_message generates formatted message from template.
    """
    incident_id = state.get("incident_id", "UNKNOWN")
    event_type = state.get("event_type", "incident_detected")
    severity = state.get("severity", "medium")
    data = state.get("notification_data", {})

    logger.info(
        "Formatting notification message",
        incident_id=incident_id,
        event_type=event_type,
        severity=severity,
    )

    try:
        formatter = get_message_formatter()
        message = formatter.format_message(
            event_type=event_type,
            incident_id=incident_id,
            severity=severity,
            data=data,
        )

        logger.info(
            "Message formatted",
            subject=message.subject[:50] + "..." if len(message.subject) > 50 else message.subject,
        )

        return {
            "message_subject": message.subject,
            "message_body": message.body,
            "message_formatted": True,
            "stage": "format_message",
            "status": "formatting",
        }

    except Exception as e:
        logger.error("Failed to format message", error=str(e))
        return {
            "message_formatted": False,
            "stage": "format_message",
            "error": f"Message formatting failed: {str(e)}",
        }
