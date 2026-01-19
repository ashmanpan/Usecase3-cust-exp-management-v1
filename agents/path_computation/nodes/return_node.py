"""
Return Path Node

Return computed path to Orchestrator.
From DESIGN.md: validate_path -> return_path -> END
"""

from typing import Any
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


async def return_path_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Return Path Node - Build response for Orchestrator.

    From DESIGN.md:
    - Return computed path to Orchestrator
    - Include path details, SIDs, and recommended TE type

    Args:
        state: Current workflow state

    Returns:
        Updated state with result for Orchestrator
    """
    incident_id = state.get("incident_id")
    computed_path = state.get("computed_path")
    path_found = state.get("path_found", False)
    path_valid = state.get("path_valid", False)
    relaxation_level = state.get("relaxation_level", 0)
    validation_violations = state.get("validation_violations", [])

    logger.info(
        "Building path response",
        incident_id=incident_id,
        path_found=path_found,
        path_valid=path_valid,
    )

    if path_found and path_valid:
        # Success case
        result = {
            "incident_id": incident_id,
            "path_found": True,
            "path": computed_path,
            "constraints_relaxed": relaxation_level > 0,
            "relaxation_level": relaxation_level,
            "timestamp": datetime.utcnow().isoformat(),
        }
        status = "success"

        logger.info(
            "Path computation successful",
            incident_id=incident_id,
            path_id=computed_path.get("path_id") if computed_path else None,
            hops=computed_path.get("total_hops") if computed_path else None,
        )

    elif path_found and not path_valid:
        # Path found but doesn't meet SLA
        result = {
            "incident_id": incident_id,
            "path_found": True,
            "path": computed_path,  # Return anyway for escalation decision
            "path_valid": False,
            "validation_violations": validation_violations,
            "constraints_relaxed": relaxation_level > 0,
            "relaxation_level": relaxation_level,
            "timestamp": datetime.utcnow().isoformat(),
        }
        status = "success"  # Workflow succeeded, path quality is info for Orchestrator

        logger.warning(
            "Path found but not valid",
            incident_id=incident_id,
            violations=validation_violations,
        )

    else:
        # No path found
        result = {
            "incident_id": incident_id,
            "path_found": False,
            "path": None,
            "relaxation_level": relaxation_level,
            "query_errors": state.get("query_errors", []),
            "timestamp": datetime.utcnow().isoformat(),
        }
        status = "no_path"

        logger.warning(
            "No path found after relaxation",
            incident_id=incident_id,
            relaxation_level=relaxation_level,
        )

    return {
        "current_node": "return_path",
        "nodes_executed": state.get("nodes_executed", []) + ["return_path"],
        "result": result,
        "status": status,
        "completed_at": datetime.utcnow().isoformat(),
    }
