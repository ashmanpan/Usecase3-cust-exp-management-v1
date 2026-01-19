"""
Conditional Edge Functions

Functions for LangGraph conditional edges in the orchestrator state machine.
Based on DESIGN.md state transitions.
"""

from typing import Literal


def check_flapping(state: dict) -> Literal["dampen", "assess"]:
    """
    Check if link is flapping.

    detect -> dampen (if flapping)
    detect -> assess (if stable)
    """
    is_flapping = state.get("is_flapping", False)
    if is_flapping:
        return "dampen"
    return "assess"


def check_services_affected(state: dict) -> Literal["compute", "close"]:
    """
    Check if services are affected.

    assess -> close (if no services)
    assess -> compute (if services affected)
    """
    affected_services = state.get("affected_services", [])
    total_affected = state.get("total_affected", len(affected_services))

    if total_affected == 0:
        return "close"
    return "compute"


def check_path_found(state: dict) -> Literal["provision", "escalate"]:
    """
    Check if alternate path was found.

    compute -> escalate (if no path)
    compute -> provision (if path found)
    """
    alternate_path = state.get("alternate_path")
    if alternate_path:
        return "provision"
    return "escalate"


def check_provision_success(state: dict) -> Literal["steer", "provision", "escalate"]:
    """
    Check tunnel provisioning result.

    provision -> steer (if success)
    provision -> provision (if retry available)
    provision -> escalate (if max retries)
    """
    status = state.get("status")

    if status == "steering":
        return "steer"
    elif status == "escalated":
        return "escalate"
    else:
        # Retry provisioning
        return "provision"


def check_steer_success(state: dict) -> Literal["monitor", "provision"]:
    """
    Check traffic steering result.

    steer -> monitor (if success)
    steer -> provision (if failed, retry)
    """
    steering_active = state.get("steering_active", False)

    if steering_active:
        return "monitor"
    return "provision"


def check_sla_recovered(state: dict) -> Literal["restore", "monitor"]:
    """
    Check if SLA has recovered.

    monitor -> restore (if recovered)
    monitor -> monitor (if still degraded)
    """
    sla_recovered = state.get("sla_recovered", False)

    if sla_recovered:
        return "restore"
    return "monitor"


def check_restore_complete(state: dict) -> Literal["close", "restore"]:
    """
    Check if restoration is complete.

    restore -> close (if complete)
    restore -> restore (if gradual cutover in progress)
    """
    restoration_complete = state.get("restoration_complete", False)
    cutover_progress = state.get("cutover_progress", 0)

    if restoration_complete or cutover_progress >= 100:
        return "close"
    return "restore"


def check_should_escalate(state: dict) -> Literal["escalate", "close"]:
    """
    Check if incident should be escalated.

    Used after error conditions.
    """
    status = state.get("status")
    error_message = state.get("error_message")
    escalate_reason = state.get("escalate_reason")

    if status == "escalated" or escalate_reason:
        return "escalate"
    if error_message:
        return "escalate"
    return "close"


def check_dampen_complete(state: dict) -> Literal["detect"]:
    """
    After dampen, always return to detect.

    dampen -> detect
    """
    return "detect"


def route_by_status(state: dict) -> str:
    """
    Generic router based on current status.

    Routes to appropriate node based on status field.
    """
    status = state.get("status", "detecting")

    status_to_node = {
        "detecting": "detect",
        "assessing": "assess",
        "computing": "compute",
        "provisioning": "provision",
        "steering": "steer",
        "monitoring": "monitor",
        "restoring": "restore",
        "dampening": "dampen",
        "escalated": "escalate",
        "closed": "close",
    }

    return status_to_node.get(status, "close")
