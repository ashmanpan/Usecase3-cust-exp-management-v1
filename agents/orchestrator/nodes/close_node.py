"""
Close Node

Cleanup, notify, and audit incident closure.
From DESIGN.md: close -> END
"""

from typing import Any
from datetime import datetime
import structlog

from ..tools.agent_caller import call_agent
from ..tools.state_manager import update_incident
from ..tools.io_notifier import notify_ticket_closed

logger = structlog.get_logger(__name__)


async def close_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Close Node - Cleanup, notify, and audit.

    Actions:
    1. Calculate incident duration
    2. Send closure notification
    3. Log final audit event
    4. Update Redis with final state

    Args:
        state: Current workflow state

    Returns:
        Final state with closure info
    """
    incident_id = state.get("incident_id")
    started_at = state.get("started_at")
    close_reason = state.get("close_reason", "resolved")

    logger.info(
        "Running close node",
        incident_id=incident_id,
        close_reason=close_reason,
    )

    # Calculate duration
    duration_seconds = None
    if started_at:
        try:
            start_time = datetime.fromisoformat(started_at)
            duration_seconds = int((datetime.utcnow() - start_time).total_seconds())
        except Exception:
            pass

    # Determine final status
    if state.get("status") == "escalated":
        final_status = "escalated"
    elif state.get("restoration_complete"):
        final_status = "resolved"
    elif close_reason == "no_services_affected":
        final_status = "no_impact"
    else:
        final_status = "closed"

    # Build summary
    summary = {
        "incident_id": incident_id,
        "final_status": final_status,
        "close_reason": close_reason,
        "duration_seconds": duration_seconds,
        "degraded_links": state.get("degraded_links", []),
        "affected_services_count": len(state.get("affected_services", [])),
        "tunnel_id": state.get("tunnel_id"),
        "nodes_executed": state.get("nodes_executed", []),
        "a2a_calls_made": len(state.get("a2a_tasks_sent", [])),
    }

    # Track A2A calls
    a2a_tasks = state.get("a2a_tasks_sent", [])

    # Send closure notification
    notify_result = await call_agent(
        agent_name="notification",
        task_type="send_notification",
        payload={
            "incident_id": incident_id,
            "event_type": "incident_closed",
            "severity": "info",
            "data": summary,
        },
        incident_id=incident_id,
        timeout=10.0,
    )

    a2a_tasks.append({
        "agent": "notification",
        "task_type": "send_notification",
        "success": notify_result.get("success"),
    })

    # Log final audit event
    audit_result = await call_agent(
        agent_name="audit",
        task_type="log_event",
        payload={
            "incident_id": incident_id,
            "event_type": "incident_closed",
            "data": summary,
            "previous_state": state.get("status"),
            "new_state": "closed",
        },
        incident_id=incident_id,
        timeout=10.0,
    )

    a2a_tasks.append({
        "agent": "audit",
        "task_type": "log_event",
        "success": audit_result.get("success"),
    })

    # Update Redis with final state
    await update_incident(
        incident_id=incident_id,
        updates={
            "status": "closed",
            "final_status": final_status,
            "close_reason": close_reason,
            "closed_at": datetime.utcnow().isoformat(),
            "duration_seconds": duration_seconds,
        },
    )

    logger.info(
        "Incident closed",
        incident_id=incident_id,
        final_status=final_status,
        duration_seconds=duration_seconds,
    )

    # Notify IO Agent that ticket is closed
    await notify_ticket_closed(
        incident_id=incident_id,
        resolution=final_status,
        duration_seconds=duration_seconds or 0,
        summary=f"Incident {final_status}: {close_reason}",
        details=summary,
        correlation_id=state.get("correlation_id"),
    )

    return {
        "current_node": "close",
        "nodes_executed": state.get("nodes_executed", []) + ["close"],
        "status": "closed",
        "final_status": final_status,
        "close_reason": close_reason,
        "duration_seconds": duration_seconds,
        "a2a_tasks_sent": a2a_tasks,
        "result": summary,
    }
