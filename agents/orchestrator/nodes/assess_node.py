"""
Assess Node

Call Service Impact Agent to identify affected services.
From DESIGN.md: assess -> compute | close
"""

from typing import Any
import structlog

from ..tools.agent_caller import call_agent
from ..tools.state_manager import update_incident

logger = structlog.get_logger(__name__)


async def assess_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Assess Node - Call Service Impact Agent.

    Actions:
    1. Call Service Impact Agent with degraded links
    2. Get list of affected services with SLA tiers
    3. If no services affected, route to close
    4. If services affected, route to compute

    Args:
        state: Current workflow state

    Returns:
        Updated state with affected services
    """
    incident_id = state.get("incident_id")
    degraded_links = state.get("degraded_links", [])

    logger.info(
        "Running assess node",
        incident_id=incident_id,
        degraded_links=degraded_links,
    )

    # Call Service Impact Agent
    impact_result = await call_agent(
        agent_name="service_impact",
        task_type="assess_impact",
        payload={
            "incident_id": incident_id,
            "degraded_links": degraded_links,
        },
        incident_id=incident_id,
        timeout=30.0,
    )

    # Track A2A call
    a2a_tasks = state.get("a2a_tasks_sent", [])
    a2a_tasks.append({
        "agent": "service_impact",
        "task_type": "assess_impact",
        "success": impact_result.get("success"),
    })

    updates = {
        "current_node": "assess",
        "nodes_executed": state.get("nodes_executed", []) + ["assess"],
        "a2a_tasks_sent": a2a_tasks,
    }

    if impact_result.get("success"):
        result = impact_result.get("result", {})
        affected_services = result.get("affected_services", [])
        total_affected = result.get("total_affected", 0)
        services_by_tier = result.get("services_by_tier", {})

        updates["a2a_responses"] = {
            **state.get("a2a_responses", {}),
            "service_impact": result,
        }
        updates["affected_services"] = affected_services
        updates["total_affected"] = total_affected
        updates["services_by_tier"] = services_by_tier

        # Update Redis
        await update_incident(
            incident_id=incident_id,
            updates={
                "status": "assessing",
                "affected_services": affected_services,
                "total_affected": total_affected,
                "services_by_tier": services_by_tier,
            },
        )

        if total_affected > 0:
            logger.info(
                "Services affected, proceeding to compute",
                incident_id=incident_id,
                total_affected=total_affected,
                services_by_tier=services_by_tier,
            )
            updates["status"] = "computing"
        else:
            logger.info(
                "No services affected, closing incident",
                incident_id=incident_id,
            )
            updates["status"] = "closed"
            updates["close_reason"] = "no_services_affected"
    else:
        logger.error(
            "Service Impact Agent call failed",
            incident_id=incident_id,
            error=impact_result.get("error"),
        )
        updates["error_message"] = impact_result.get("error")
        updates["status"] = "escalated"

    return updates
