"""
Steer Node

Activate traffic steering to protection tunnel.
From DESIGN.md: steer -> monitor | provision (retry)
"""

from typing import Any
import structlog

from ..tools.agent_caller import call_agent
from ..tools.state_manager import update_incident

logger = structlog.get_logger(__name__)


async def steer_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Steer Node - Activate traffic steering.

    Actions:
    1. Verify tunnel is operationally up
    2. Activate traffic steering (BGP Color/ODN)
    3. Notify about protection activation
    4. Route to monitor node

    Args:
        state: Current workflow state

    Returns:
        Updated state with steering status
    """
    incident_id = state.get("incident_id")
    tunnel_id = state.get("tunnel_id")
    binding_sid = state.get("binding_sid")
    affected_services = state.get("affected_services", [])

    logger.info(
        "Running steer node",
        incident_id=incident_id,
        tunnel_id=tunnel_id,
        binding_sid=binding_sid,
    )

    # In a real implementation, this would:
    # 1. Verify tunnel operational status via CNC
    # 2. Activate traffic steering (BGP Color advertisement)
    # 3. Verify traffic is flowing through protection path

    # For now, we'll mark steering as successful if tunnel exists
    if not tunnel_id:
        logger.error(
            "No tunnel_id available for steering",
            incident_id=incident_id,
        )
        return {
            "current_node": "steer",
            "nodes_executed": state.get("nodes_executed", []) + ["steer"],
            "status": "provisioning",  # Go back to provision
            "error_message": "No tunnel available for steering",
        }

    # Call Notification Agent to inform about protection activation
    notify_result = await call_agent(
        agent_name="notification",
        task_type="send_notification",
        payload={
            "incident_id": incident_id,
            "event_type": "protection_activated",
            "severity": state.get("severity"),
            "data": {
                "tunnel_id": tunnel_id,
                "binding_sid": binding_sid,
                "affected_services_count": len(affected_services),
                "degraded_links": state.get("degraded_links", []),
            },
        },
        incident_id=incident_id,
        timeout=10.0,
    )

    # Call Audit Agent to log the event
    audit_result = await call_agent(
        agent_name="audit",
        task_type="log_event",
        payload={
            "incident_id": incident_id,
            "event_type": "traffic_steered",
            "data": {
                "tunnel_id": tunnel_id,
                "binding_sid": binding_sid,
                "affected_services": [s.get("service_id") for s in affected_services],
            },
            "previous_state": "provisioning",
            "new_state": "monitoring",
        },
        incident_id=incident_id,
        timeout=10.0,
    )

    # Track A2A calls
    a2a_tasks = state.get("a2a_tasks_sent", [])
    a2a_tasks.extend([
        {
            "agent": "notification",
            "task_type": "send_notification",
            "success": notify_result.get("success"),
        },
        {
            "agent": "audit",
            "task_type": "log_event",
            "success": audit_result.get("success"),
        },
    ])

    # Update Redis
    await update_incident(
        incident_id=incident_id,
        updates={
            "status": "monitoring",
            "steering_active": True,
        },
    )

    logger.info(
        "Traffic steering activated, proceeding to monitor",
        incident_id=incident_id,
        tunnel_id=tunnel_id,
    )

    return {
        "current_node": "steer",
        "nodes_executed": state.get("nodes_executed", []) + ["steer"],
        "status": "monitoring",
        "steering_active": True,
        "a2a_tasks_sent": a2a_tasks,
    }
