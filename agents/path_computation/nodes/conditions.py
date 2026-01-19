"""
Conditional Edge Functions

Routing logic for Path Computation workflow.
From DESIGN.md workflow transitions.
"""

from typing import Any, Literal


def check_path_found(state: dict[str, Any]) -> Literal["validate", "relax"]:
    """
    Check if path was found.

    From DESIGN.md: query_kg -> validate | relax

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    path_found = state.get("path_found", False)

    if path_found:
        return "validate"
    return "relax"


def check_path_valid(state: dict[str, Any]) -> Literal["return", "relax"]:
    """
    Check if path is valid.

    From DESIGN.md: validate_path -> return | relax

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    path_valid = state.get("path_valid", False)

    if path_valid:
        return "return"
    return "relax"


def check_can_relax(state: dict[str, Any]) -> Literal["query", "return"]:
    """
    Check if further relaxation is possible.

    From DESIGN.md: relax_constraints -> query | return

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    relaxation_level = state.get("relaxation_level", 0)
    max_relaxation = 4  # From DESIGN.md

    if relaxation_level <= max_relaxation:
        return "query"
    return "return"
