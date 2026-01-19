"""
IO Agent Notifier - Sends status updates to IO Agent for human UI

Provides helper functions for orchestrator nodes to send updates.
"""

from typing import Any, Optional
import sys
import os
import structlog

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from agent_template.tools.io_agent_client import get_io_client

logger = structlog.get_logger(__name__)

# Phase mapping for UI display
PHASE_MAP = {
    "detecting": ("1", "Detecting SLA Degradation"),
    "dampening": ("1", "Flap Detection - Dampening"),
    "assessing": ("2", "Assessing Service Impact"),
    "computing": ("3", "Computing Alternate Path"),
    "provisioning": ("4", "Provisioning Protection Tunnel"),
    "steering": ("5", "Steering Traffic"),
    "monitoring": ("6", "Monitoring SLA Recovery"),
    "restoring": ("7", "Restoring Original Path"),
    "escalated": ("E", "Escalated to Operator"),
    "closed": ("C", "Incident Closed"),
}


async def notify_phase_change(
    incident_id: str,
    status: str,
    message: str = None,
    details: dict[str, Any] = None,
    correlation_id: Optional[str] = None,
) -> bool:
    """
    Notify IO Agent of phase change.

    Args:
        incident_id: Incident ID
        status: New status (detecting, assessing, computing, etc.)
        message: Optional custom message
        details: Additional details
        correlation_id: Correlation ID for tracing

    Returns:
        True if notification sent successfully
    """
    try:
        io_client = get_io_client()

        phase_info = PHASE_MAP.get(status, ("?", status))
        phase_num = phase_info[0]
        phase_name = phase_info[1]

        await io_client.send_status_update(
            incident_id=incident_id,
            status=status,
            phase=phase_num,
            message=message or phase_name,
            details=details or {},
            source_agent="orchestrator",
            correlation_id=correlation_id,
        )

        logger.debug(
            "IO Agent notified of phase change",
            incident_id=incident_id,
            status=status,
            phase=phase_num,
        )
        return True

    except Exception as e:
        logger.warning(
            "Failed to notify IO Agent of phase change",
            incident_id=incident_id,
            status=status,
            error=str(e),
        )
        return False


async def notify_error(
    incident_id: str,
    error_type: str,
    error_message: str,
    recoverable: bool = True,
    correlation_id: Optional[str] = None,
) -> bool:
    """
    Notify IO Agent of an error.

    Args:
        incident_id: Incident ID
        error_type: Type of error
        error_message: Human-readable error message
        recoverable: Whether the error is recoverable
        correlation_id: Correlation ID for tracing

    Returns:
        True if notification sent successfully
    """
    try:
        io_client = get_io_client()

        await io_client.send_error(
            incident_id=incident_id,
            error_type=error_type,
            error_message=error_message,
            source_agent="orchestrator",
            recoverable=recoverable,
            correlation_id=correlation_id,
        )

        logger.debug(
            "IO Agent notified of error",
            incident_id=incident_id,
            error_type=error_type,
        )
        return True

    except Exception as e:
        logger.warning(
            "Failed to notify IO Agent of error",
            incident_id=incident_id,
            error_type=error_type,
            error=str(e),
        )
        return False


async def notify_ticket_closed(
    incident_id: str,
    resolution: str,
    duration_seconds: int,
    summary: str,
    details: dict[str, Any] = None,
    correlation_id: Optional[str] = None,
) -> bool:
    """
    Notify IO Agent that ticket is closed.

    Args:
        incident_id: Incident ID
        resolution: Resolution type
        duration_seconds: Total duration
        summary: Resolution summary
        details: Additional details
        correlation_id: Correlation ID for tracing

    Returns:
        True if notification sent successfully
    """
    try:
        io_client = get_io_client()

        await io_client.notify_ticket_closed(
            incident_id=incident_id,
            resolution=resolution,
            duration_seconds=duration_seconds,
            summary=summary,
            details=details or {},
            source_agent="orchestrator",
            correlation_id=correlation_id,
        )

        logger.debug(
            "IO Agent notified of ticket closure",
            incident_id=incident_id,
            resolution=resolution,
        )
        return True

    except Exception as e:
        logger.warning(
            "Failed to notify IO Agent of ticket closure",
            incident_id=incident_id,
            error=str(e),
        )
        return False
