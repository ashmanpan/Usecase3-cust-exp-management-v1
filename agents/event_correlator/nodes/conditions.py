"""
Conditional Edge Functions

Routing logic for Event Correlator workflow.
From DESIGN.md workflow transitions.
"""

from typing import Any, Literal


def check_duplicate(state: dict[str, Any]) -> Literal["correlate", "discard"]:
    """
    Check if alert is duplicate.

    From DESIGN.md: dedup -> correlate | discard

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    is_duplicate = state.get("is_duplicate", False)

    if is_duplicate:
        return "discard"
    return "correlate"


def check_flap_status(state: dict[str, Any]) -> Literal["emit", "suppress"]:
    """
    Check if link is flapping.

    From DESIGN.md: flap_detect -> emit | suppress

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    is_flapping = state.get("is_flapping", False)

    if is_flapping:
        return "suppress"
    return "emit"
