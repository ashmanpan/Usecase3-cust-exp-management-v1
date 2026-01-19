"""
Monitor Node

Call Restoration Monitor Agent to check SLA recovery.
From DESIGN.md: monitor -> restore | monitor (continue)
"""

from typing import Any
import structlog

from ..tools.agent_caller import call_agent
from ..tools.state_manager import update_incident

logger = structlog.get_logger(__name__)


async def monitor_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Monitor Node - Call Restoration Monitor Agent.

    Actions:
    1. Call Restoration Monitor Agent
    2. Check if original path SLA has recovered
    3. If recovered, route to restore
    4. If not recovered, stay in monitor

    Args:
        state: Current workflow state

    Returns:
        Updated state with recovery status
    """
    incident_id = state.get("incident_id")
    tunnel_id = state.get("tunnel_id")
    alternate_path = state.get("alternate_path", {})
    primary_service = state.get("primary_service", {})
    cutover_mode = state.get("cutover_mode", "gradual")

    logger.info(
        "Running monitor node",
        incident_id=incident_id,
        tunnel_id=tunnel_id,
    )

    # Call Restoration Monitor Agent
    monitor_result = await call_agent(
        agent_name="restoration_monitor",
        task_type="monitor_restoration",
        payload={
            "incident_id": incident_id,
            "protection_tunnel_id": tunnel_id,
            "original_path": {
                "degraded_links": state.get("degraded_links", []),
                "source_pe": primary_service.get("source_pe"),
                "destination_pe": primary_service.get("destination_pe"),
            },
            "sla_tier": primary_service.get("sla_tier", "gold"),
            "cutover_mode": cutover_mode,
        },
        incident_id=incident_id,
        timeout=30.0,
    )

    # Track A2A call
    a2a_tasks = state.get("a2a_tasks_sent", [])
    a2a_tasks.append({
        "agent": "restoration_monitor",
        "task_type": "monitor_restoration",
        "success": monitor_result.get("success"),
    })

    updates = {
        "current_node": "monitor",
        "nodes_executed": state.get("nodes_executed", []) + ["monitor"],
        "a2a_tasks_sent": a2a_tasks,
    }

    if monitor_result.get("success"):
        result = monitor_result.get("result", {})
        restored = result.get("restored", False)

        updates["a2a_responses"] = {
            **state.get("a2a_responses", {}),
            "restoration_monitor": result,
        }

        if restored:
            updates["sla_recovered"] = True
            updates["status"] = "restoring"
            updates["hold_timer_start"] = result.get("hold_timer_start")
            updates["cutover_mode"] = result.get("cutover_mode", cutover_mode)

            # Update Redis
            await update_incident(
                incident_id=incident_id,
                updates={
                    "status": "restoring",
                    "sla_recovered": True,
                    "hold_timer_start": result.get("hold_timer_start"),
                },
            )

            logger.info(
                "SLA recovered, proceeding to restore",
                incident_id=incident_id,
                hold_timer_seconds=result.get("hold_timer_seconds"),
            )
        else:
            # Continue monitoring
            updates["sla_recovered"] = False
            updates["status"] = "monitoring"
            updates["monitoring_status"] = result.get("status", "degraded")

            logger.info(
                "SLA not yet recovered, continuing to monitor",
                incident_id=incident_id,
                status=result.get("status"),
            )
    else:
        logger.error(
            "Restoration Monitor Agent call failed",
            incident_id=incident_id,
            error=monitor_result.get("error"),
        )
        updates["error_message"] = monitor_result.get("error")
        # Continue monitoring despite error
        updates["status"] = "monitoring"

    return updates
