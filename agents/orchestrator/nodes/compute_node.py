"""
Compute Node

Call Path Computation Agent to find alternate path.
From DESIGN.md: compute -> provision | escalate
"""

from typing import Any
import structlog

from ..tools.agent_caller import call_agent
from ..tools.state_manager import update_incident

logger = structlog.get_logger(__name__)


async def compute_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Compute Node - Call Path Computation Agent.

    Actions:
    1. Determine highest priority service (by SLA tier)
    2. Call Path Computation Agent with constraints
    3. If path found, route to provision
    4. If no path, route to escalate

    Args:
        state: Current workflow state

    Returns:
        Updated state with computed path
    """
    incident_id = state.get("incident_id")
    degraded_links = state.get("degraded_links", [])
    affected_services = state.get("affected_services", [])

    logger.info(
        "Running compute node",
        incident_id=incident_id,
        service_count=len(affected_services),
    )

    # Find highest priority service to compute path for
    # Priority order: platinum > gold > silver > bronze
    tier_priority = {"platinum": 1, "gold": 2, "silver": 3, "bronze": 4}
    sorted_services = sorted(
        affected_services,
        key=lambda s: tier_priority.get(s.get("sla_tier", "bronze"), 4),
    )

    if not sorted_services:
        logger.warning(
            "No services to compute path for",
            incident_id=incident_id,
        )
        return {
            "current_node": "compute",
            "nodes_executed": state.get("nodes_executed", []) + ["compute"],
            "status": "escalated",
            "error_message": "No services to compute path for",
        }

    # Use first (highest priority) service for path computation
    primary_service = sorted_services[0]

    # Call Path Computation Agent
    compute_result = await call_agent(
        agent_name="path_computation",
        task_type="compute_path",
        payload={
            "incident_id": incident_id,
            "source_pe": primary_service.get("source_pe"),
            "destination_pe": primary_service.get("destination_pe"),
            "degraded_links": degraded_links,
            "service_sla_tier": primary_service.get("sla_tier"),
            "current_te_type": primary_service.get("current_path_type"),
        },
        incident_id=incident_id,
        timeout=60.0,
    )

    # Track A2A call
    a2a_tasks = state.get("a2a_tasks_sent", [])
    a2a_tasks.append({
        "agent": "path_computation",
        "task_type": "compute_path",
        "success": compute_result.get("success"),
    })

    updates = {
        "current_node": "compute",
        "nodes_executed": state.get("nodes_executed", []) + ["compute"],
        "a2a_tasks_sent": a2a_tasks,
        "primary_service": primary_service,
    }

    if compute_result.get("success"):
        result = compute_result.get("result", {})
        path_found = result.get("path_found", False)

        updates["a2a_responses"] = {
            **state.get("a2a_responses", {}),
            "path_computation": result,
        }

        if path_found:
            alternate_path = result.get("path")
            updates["alternate_path"] = alternate_path
            updates["status"] = "provisioning"

            # Update Redis
            await update_incident(
                incident_id=incident_id,
                updates={
                    "status": "provisioning",
                    "alternate_path": alternate_path,
                },
            )

            logger.info(
                "Alternate path found, proceeding to provision",
                incident_id=incident_id,
                path_type=alternate_path.get("path_type") if alternate_path else None,
            )
        else:
            logger.warning(
                "No alternate path found, escalating",
                incident_id=incident_id,
            )
            updates["status"] = "escalated"
            updates["escalate_reason"] = "no_alternate_path"

            await update_incident(
                incident_id=incident_id,
                updates={
                    "status": "escalated",
                    "escalate_reason": "no_alternate_path",
                },
            )
    else:
        logger.error(
            "Path Computation Agent call failed",
            incident_id=incident_id,
            error=compute_result.get("error"),
        )
        updates["error_message"] = compute_result.get("error")
        updates["status"] = "escalated"

    return updates
