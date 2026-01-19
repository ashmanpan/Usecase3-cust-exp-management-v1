"""
IO Agent Client - Sends ticket updates to human UI

Provides interface for agents to send:
- New ticket notifications
- Status updates
- Ticket closed notifications
"""

import os
from typing import Any, Optional
from datetime import datetime
import structlog

from .a2a_client import A2AClient, get_a2a_client, A2AClientError

logger = structlog.get_logger(__name__)

# IO Agent configuration (can be overridden via environment)
IO_AGENT_URL = os.getenv("IO_AGENT_URL", "http://io-agent:8009")
IO_AGENT_NAME = "io_agent"

# Singleton instance
_io_client: Optional["IOAgentClient"] = None


class IOAgentClient:
    """
    Client for sending updates to the IO Agent (Human UI).

    Task Types:
    - new_ticket: New incident/ticket created
    - status_update: Incident status changed
    - ticket_closed: Incident resolved and closed
    """

    def __init__(
        self,
        io_agent_url: str = None,
        a2a_client: A2AClient = None,
        enabled: bool = None,
    ):
        self.io_agent_url = io_agent_url or IO_AGENT_URL
        self.a2a_client = a2a_client or get_a2a_client()
        self.enabled = enabled if enabled is not None else (
            os.getenv("IO_AGENT_ENABLED", "true").lower() == "true"
        )

        # Register IO Agent with A2A client
        if self.enabled:
            self.a2a_client.register_agent(IO_AGENT_NAME, self.io_agent_url)
            logger.info(
                "IO Agent client initialized",
                url=self.io_agent_url,
                enabled=self.enabled,
            )

    async def notify_new_ticket(
        self,
        incident_id: str,
        severity: str,
        summary: str,
        degraded_links: list[str] = None,
        affected_services: list[str] = None,
        source_agent: str = "event_correlator",
        correlation_id: Optional[str] = None,
    ) -> bool:
        """
        Notify IO Agent of a new ticket/incident.

        Args:
            incident_id: Unique incident ID (e.g., INC-2026-0001)
            severity: Incident severity (critical, high, medium, low)
            summary: Brief description of the incident
            degraded_links: List of affected links
            affected_services: List of affected services
            source_agent: Agent that created the incident
            correlation_id: Correlation ID for tracing

        Returns:
            True if notification sent successfully
        """
        if not self.enabled:
            logger.debug("IO Agent disabled, skipping new_ticket notification")
            return True

        payload = {
            "incident_id": incident_id,
            "severity": severity,
            "summary": summary,
            "degraded_links": degraded_links or [],
            "affected_services": affected_services or [],
            "source_agent": source_agent,
            "created_at": datetime.utcnow().isoformat(),
            "status": "new",
        }

        try:
            await self.a2a_client.send_task(
                agent_name=IO_AGENT_NAME,
                task_type="new_ticket",
                payload=payload,
                incident_id=incident_id,
                correlation_id=correlation_id,
            )
            logger.info(
                "Sent new_ticket to IO Agent",
                incident_id=incident_id,
                severity=severity,
            )
            return True

        except A2AClientError as e:
            logger.warning(
                "Failed to notify IO Agent of new ticket",
                incident_id=incident_id,
                error=str(e),
            )
            return False

    async def send_status_update(
        self,
        incident_id: str,
        status: str,
        phase: str,
        message: str,
        details: dict[str, Any] = None,
        source_agent: str = "orchestrator",
        correlation_id: Optional[str] = None,
    ) -> bool:
        """
        Send status update to IO Agent.

        Args:
            incident_id: Incident ID
            status: Current status (detecting, assessing, computing, provisioning, monitoring, restoring, closed)
            phase: Current workflow phase (1-7)
            message: Human-readable status message
            details: Additional details (e.g., tunnel_id, affected_services count)
            source_agent: Agent sending the update
            correlation_id: Correlation ID for tracing

        Returns:
            True if update sent successfully
        """
        if not self.enabled:
            logger.debug("IO Agent disabled, skipping status_update")
            return True

        payload = {
            "incident_id": incident_id,
            "status": status,
            "phase": phase,
            "message": message,
            "details": details or {},
            "source_agent": source_agent,
            "updated_at": datetime.utcnow().isoformat(),
        }

        try:
            await self.a2a_client.send_task(
                agent_name=IO_AGENT_NAME,
                task_type="status_update",
                payload=payload,
                incident_id=incident_id,
                correlation_id=correlation_id,
            )
            logger.info(
                "Sent status_update to IO Agent",
                incident_id=incident_id,
                status=status,
                phase=phase,
            )
            return True

        except A2AClientError as e:
            logger.warning(
                "Failed to send status update to IO Agent",
                incident_id=incident_id,
                error=str(e),
            )
            return False

    async def notify_ticket_closed(
        self,
        incident_id: str,
        resolution: str,
        duration_seconds: int,
        summary: str,
        details: dict[str, Any] = None,
        source_agent: str = "orchestrator",
        correlation_id: Optional[str] = None,
    ) -> bool:
        """
        Notify IO Agent that ticket is closed.

        Args:
            incident_id: Incident ID
            resolution: Resolution type (restored, escalated, manual)
            duration_seconds: Total incident duration
            summary: Resolution summary
            details: Additional details
            source_agent: Agent closing the ticket
            correlation_id: Correlation ID for tracing

        Returns:
            True if notification sent successfully
        """
        if not self.enabled:
            logger.debug("IO Agent disabled, skipping ticket_closed notification")
            return True

        payload = {
            "incident_id": incident_id,
            "resolution": resolution,
            "duration_seconds": duration_seconds,
            "summary": summary,
            "details": details or {},
            "source_agent": source_agent,
            "closed_at": datetime.utcnow().isoformat(),
            "status": "closed",
        }

        try:
            await self.a2a_client.send_task(
                agent_name=IO_AGENT_NAME,
                task_type="ticket_closed",
                payload=payload,
                incident_id=incident_id,
                correlation_id=correlation_id,
            )
            logger.info(
                "Sent ticket_closed to IO Agent",
                incident_id=incident_id,
                resolution=resolution,
            )
            return True

        except A2AClientError as e:
            logger.warning(
                "Failed to notify IO Agent of ticket closure",
                incident_id=incident_id,
                error=str(e),
            )
            return False

    async def send_error(
        self,
        incident_id: str,
        error_type: str,
        error_message: str,
        source_agent: str,
        recoverable: bool = True,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """
        Send error notification to IO Agent.

        Args:
            incident_id: Incident ID
            error_type: Type of error (provisioning_failed, path_not_found, etc.)
            error_message: Human-readable error message
            source_agent: Agent that encountered the error
            recoverable: Whether the error is recoverable
            correlation_id: Correlation ID for tracing

        Returns:
            True if notification sent successfully
        """
        if not self.enabled:
            return True

        payload = {
            "incident_id": incident_id,
            "error_type": error_type,
            "error_message": error_message,
            "source_agent": source_agent,
            "recoverable": recoverable,
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            await self.a2a_client.send_task(
                agent_name=IO_AGENT_NAME,
                task_type="error",
                payload=payload,
                incident_id=incident_id,
                correlation_id=correlation_id,
            )
            logger.info(
                "Sent error to IO Agent",
                incident_id=incident_id,
                error_type=error_type,
            )
            return True

        except A2AClientError as e:
            logger.warning(
                "Failed to send error to IO Agent",
                incident_id=incident_id,
                error=str(e),
            )
            return False


def get_io_client() -> IOAgentClient:
    """Get singleton IO Agent client instance"""
    global _io_client
    if _io_client is None:
        _io_client = IOAgentClient()
    return _io_client


def configure_io_client(
    io_agent_url: str = None,
    enabled: bool = True,
) -> IOAgentClient:
    """Configure the singleton IO Agent client"""
    global _io_client
    _io_client = IOAgentClient(
        io_agent_url=io_agent_url,
        enabled=enabled,
    )
    return _io_client
