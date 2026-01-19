"""Send Parallel Node - From DESIGN.md send_parallel"""
from typing import Any, List
import asyncio
import structlog

from ..schemas.notification import ChannelResult
from ..tools.webex_client import get_webex_client
from ..tools.servicenow_client import get_servicenow_client
from ..tools.email_client import get_email_client

logger = structlog.get_logger(__name__)

# Severity mapping for ServiceNow
SEVERITY_MAP = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
}


async def send_parallel_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Send to all channels concurrently.
    From DESIGN.md: send_parallel sends to all channels concurrently.
    """
    selected_channels = state.get("selected_channels", [])
    message_subject = state.get("message_subject", "Notification")
    message_body = state.get("message_body", "No message content")
    incident_id = state.get("incident_id", "UNKNOWN")
    severity = state.get("severity", "medium")
    webex_space = state.get("webex_space", "")
    servicenow_assignment = state.get("servicenow_assignment", "Network Operations")
    email_recipients = state.get("email_recipients", [])

    logger.info(
        "Sending notifications in parallel",
        channels=selected_channels,
        incident_id=incident_id,
    )

    # Create send tasks
    tasks = []
    if "webex" in selected_channels and webex_space:
        tasks.append(("webex", _send_webex(webex_space, message_body)))
    if "servicenow" in selected_channels:
        tasks.append(("servicenow", _send_servicenow(
            message_subject, message_body, severity, servicenow_assignment
        )))
    if "email" in selected_channels and email_recipients:
        tasks.append(("email", _send_email(email_recipients, message_subject, message_body)))

    # Execute all sends in parallel
    results: List[ChannelResult] = []
    channels_attempted = []
    channels_succeeded = []
    channels_failed = []

    webex_sent = False
    webex_message_id = None
    servicenow_sent = False
    servicenow_ticket = None
    email_sent = False
    email_sent_to = []

    for channel_name, coro in tasks:
        channels_attempted.append(channel_name)
        try:
            result = await coro
            results.append(result)

            if result.success:
                channels_succeeded.append(channel_name)
                if channel_name == "webex":
                    webex_sent = True
                    webex_message_id = result.message_id
                elif channel_name == "servicenow":
                    servicenow_sent = True
                    servicenow_ticket = result.ticket_number
                elif channel_name == "email":
                    email_sent = True
                    email_sent_to = result.recipients
            else:
                channels_failed.append(channel_name)

        except Exception as e:
            logger.error(f"Failed to send to {channel_name}", error=str(e))
            channels_failed.append(channel_name)
            results.append(ChannelResult(
                channel=channel_name,
                success=False,
                error=str(e),
            ))

    logger.info(
        "Parallel send complete",
        attempted=len(channels_attempted),
        succeeded=len(channels_succeeded),
        failed=len(channels_failed),
    )

    return {
        "channels_attempted": channels_attempted,
        "channels_succeeded": channels_succeeded,
        "channels_failed": channels_failed,
        "channel_results": [r.model_dump() for r in results],
        "webex_sent": webex_sent,
        "webex_message_id": webex_message_id,
        "servicenow_sent": servicenow_sent,
        "servicenow_ticket": servicenow_ticket,
        "email_sent": email_sent,
        "email_sent_to": email_sent_to,
        "stage": "send_parallel",
        "status": "sending",
    }


async def _send_webex(space_id: str, message: str) -> ChannelResult:
    """Send to Webex"""
    client = get_webex_client()
    result = await client.send_message(space_id=space_id, message=message, markdown=True)

    return ChannelResult(
        channel="webex",
        success=result.success,
        message_id=result.message_id,
        error=result.error,
    )


async def _send_servicenow(
    subject: str,
    description: str,
    severity: str,
    assignment_group: str,
) -> ChannelResult:
    """Send to ServiceNow"""
    client = get_servicenow_client()
    result = await client.create_incident(
        short_description=subject,
        description=description,
        severity=SEVERITY_MAP.get(severity, "medium"),
        assignment_group=assignment_group,
    )

    return ChannelResult(
        channel="servicenow",
        success=result.success,
        ticket_number=result.incident_number,
        error=result.error,
    )


async def _send_email(
    recipients: List[str],
    subject: str,
    body: str,
) -> ChannelResult:
    """Send email"""
    client = get_email_client()
    result = await client.send_email(to=recipients, subject=subject, body=body, html=False)

    return ChannelResult(
        channel="email",
        success=result.success,
        recipients=result.sent_to,
        error=result.error,
    )
