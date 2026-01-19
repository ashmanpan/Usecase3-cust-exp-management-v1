"""
Restore Node

Execute cutover and remove protection tunnel.
From DESIGN.md: restore -> close
"""

from typing import Any
import structlog

from ..tools.agent_caller import call_agent
from ..tools.state_manager import update_incident

logger = structlog.get_logger(__name__)


async def restore_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Restore Node - Execute cutover, remove protection tunnel.

    Actions:
    1. Execute cutover (immediate or gradual)
    2. Call Tunnel Provisioning to delete protection tunnel
    3. Notify about restoration
    4. Route to close

    Args:
        state: Current workflow state

    Returns:
        Updated state with restoration status
    """
    incident_id = state.get("incident_id")
    tunnel_id = state.get("tunnel_id")
    cutover_mode = state.get("cutover_mode", "gradual")
    affected_services = state.get("affected_services", [])

    logger.info(
        "Running restore node",
        incident_id=incident_id,
        tunnel_id=tunnel_id,
        cutover_mode=cutover_mode,
    )

    # Track A2A calls
    a2a_tasks = state.get("a2a_tasks_sent", [])

    # If gradual cutover, check progress from restoration monitor
    restoration_response = state.get("a2a_responses", {}).get("restoration_monitor", {})
    cutover_progress = restoration_response.get("cutover_progress", 100)

    if cutover_mode == "gradual" and cutover_progress < 100:
        # Gradual cutover still in progress
        logger.info(
            "Gradual cutover in progress",
            incident_id=incident_id,
            progress=cutover_progress,
        )
        return {
            "current_node": "restore",
            "nodes_executed": state.get("nodes_executed", []) + ["restore"],
            "status": "restoring",
            "cutover_progress": cutover_progress,
        }

    # Cutover complete, delete protection tunnel
    if tunnel_id:
        delete_result = await call_agent(
            agent_name="tunnel_provisioning",
            task_type="delete_tunnel",
            payload={
                "incident_id": incident_id,
                "tunnel_id": tunnel_id,
            },
            incident_id=incident_id,
            timeout=30.0,
        )

        a2a_tasks.append({
            "agent": "tunnel_provisioning",
            "task_type": "delete_tunnel",
            "success": delete_result.get("success"),
        })

        if not delete_result.get("success"):
            logger.warning(
                "Failed to delete protection tunnel",
                incident_id=incident_id,
                tunnel_id=tunnel_id,
                error=delete_result.get("error"),
            )

    # Notify about restoration
    notify_result = await call_agent(
        agent_name="notification",
        task_type="send_notification",
        payload={
            "incident_id": incident_id,
            "event_type": "restoration_complete",
            "severity": "info",
            "data": {
                "tunnel_id": tunnel_id,
                "cutover_mode": cutover_mode,
                "affected_services_count": len(affected_services),
            },
        },
        incident_id=incident_id,
        timeout=10.0,
    )

    a2a_tasks.append({
        "agent": "notification",
        "task_type": "send_notification",
        "success": notify_result.get("success"),
    })

    # Log restoration event
    audit_result = await call_agent(
        agent_name="audit",
        task_type="log_event",
        payload={
            "incident_id": incident_id,
            "event_type": "restoration_complete",
            "data": {
                "tunnel_id": tunnel_id,
                "tunnel_deleted": True,
                "cutover_mode": cutover_mode,
            },
            "previous_state": "restoring",
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

    # Update Redis
    await update_incident(
        incident_id=incident_id,
        updates={
            "status": "closed",
            "tunnel_deleted": True,
            "restoration_complete": True,
        },
    )

    logger.info(
        "Restoration complete, proceeding to close",
        incident_id=incident_id,
    )

    return {
        "current_node": "restore",
        "nodes_executed": state.get("nodes_executed", []) + ["restore"],
        "status": "closed",
        "tunnel_deleted": True,
        "restoration_complete": True,
        "cutover_progress": 100,
        "a2a_tasks_sent": a2a_tasks,
    }
