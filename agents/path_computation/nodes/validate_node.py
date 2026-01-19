"""
Validate Path Node

Validate computed path against SLA requirements.
From DESIGN.md: query_kg -> validate_path -> return_path | relax_constraints
"""

from typing import Any
import structlog

from ..tools.path_validator import get_path_validator
from ..schemas.paths import ComputedPath

logger = structlog.get_logger(__name__)


async def validate_path_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Validate Path Node - Check path meets SLA requirements.

    From DESIGN.md:
    - Check path meets SLA requirements (delay, BW)
    - Valid path goes to return, invalid to relax

    Args:
        state: Current workflow state

    Returns:
        Updated state with validation result
    """
    incident_id = state.get("incident_id")
    computed_path_dict = state.get("computed_path")
    required_sla = state.get("required_sla", {})
    constraints = state.get("constraints", {})

    logger.info(
        "Validating computed path",
        incident_id=incident_id,
    )

    if not computed_path_dict:
        logger.warning(
            "No path to validate",
            incident_id=incident_id,
        )
        return {
            "current_node": "validate_path",
            "nodes_executed": state.get("nodes_executed", []) + ["validate_path"],
            "path_valid": False,
            "validation_violations": ["No path computed"],
        }

    try:
        # Convert dict to ComputedPath
        computed_path = ComputedPath(**computed_path_dict)

        validator = get_path_validator()

        # Validate path
        result = validator.validate_path(
            path=computed_path,
            required_sla=required_sla,
            max_hops=constraints.get("max_hops"),
        )

        logger.info(
            "Path validation complete",
            incident_id=incident_id,
            path_id=computed_path.path_id,
            is_valid=result.is_valid,
            violations=result.violations,
        )

        return {
            "current_node": "validate_path",
            "nodes_executed": state.get("nodes_executed", []) + ["validate_path"],
            "path_valid": result.is_valid,
            "validation_violations": result.violations,
        }

    except Exception as e:
        logger.error(
            "Path validation failed",
            incident_id=incident_id,
            error=str(e),
        )
        return {
            "current_node": "validate_path",
            "nodes_executed": state.get("nodes_executed", []) + ["validate_path"],
            "path_valid": False,
            "validation_violations": [f"Validation error: {str(e)}"],
        }
