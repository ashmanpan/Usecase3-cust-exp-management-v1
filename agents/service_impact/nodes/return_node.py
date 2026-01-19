"""
Return Affected Node

Return affected services to Orchestrator.
From DESIGN.md: enrich_sla -> return_affected -> END
"""

from typing import Any
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


async def return_affected_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Return Affected Node - Build response for Orchestrator.

    From DESIGN.md:
    - Return sorted list (by SLA tier) to Orchestrator
    - ServiceImpactResponse format

    Args:
        state: Current workflow state

    Returns:
        Updated state with result for Orchestrator
    """
    incident_id = state.get("incident_id")
    affected_services = state.get("affected_services", [])
    services_by_tier = state.get("services_by_tier", {})
    services_by_type = state.get("services_by_type", {})
    highest_priority_tier = state.get("highest_priority_tier")
    auto_protect_required = state.get("auto_protect_required", False)
    total_affected = state.get("total_affected", 0)

    logger.info(
        "Building response for Orchestrator",
        incident_id=incident_id,
        total_affected=total_affected,
    )

    # Build ServiceImpactResponse
    result = {
        "incident_id": incident_id,
        "total_affected": total_affected,
        "services_by_tier": services_by_tier,
        "services_by_type": services_by_type,
        "affected_services": affected_services,
        "highest_priority_tier": highest_priority_tier,
        "auto_protect_required": auto_protect_required,
        "timestamp": datetime.utcnow().isoformat(),
    }

    logger.info(
        "Service impact assessment complete",
        incident_id=incident_id,
        total_affected=total_affected,
        highest_priority_tier=highest_priority_tier,
        auto_protect_required=auto_protect_required,
    )

    return {
        "current_node": "return_affected",
        "nodes_executed": state.get("nodes_executed", []) + ["return_affected"],
        "result": result,
        "status": "success",
        "completed_at": datetime.utcnow().isoformat(),
    }
