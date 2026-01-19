"""Conditional Edge Functions - From DESIGN.md workflow transitions"""
from typing import Any, Literal


def check_recovered(state: dict[str, Any]) -> Literal["start_timer", "wait_poll"]:
    """
    Check if SLA has recovered.
    From DESIGN.md flow: If recovered -> start hold timer, else continue monitoring
    """
    if state.get("sla_recovered", False):
        return "start_timer"
    return "wait_poll"


def check_timer_expired(state: dict[str, Any]) -> Literal["verify", "wait_timer", "poll"]:
    """
    Check if hold timer has expired or been cancelled.
    """
    if state.get("timer_cancelled", False):
        # Timer cancelled (SLA degraded during hold) - go back to polling
        return "poll"
    if state.get("timer_expired", False):
        return "verify"
    return "wait_timer"


def check_stable(state: dict[str, Any]) -> Literal["cutover", "reset_timer"]:
    """
    Check if SLA is stable after hold timer.
    From DESIGN.md: If stable -> proceed to cutover, else reset timer
    """
    if state.get("stability_verified", False):
        return "cutover"
    return "reset_timer"


def check_cutover_complete(state: dict[str, Any]) -> Literal["cleanup", "verify"]:
    """
    Check if cutover completed successfully.
    """
    if state.get("cutover_complete", False):
        return "cleanup"
    # Cutover failed - go back to verification
    return "verify"


def check_max_iterations(state: dict[str, Any]) -> Literal["continue", "timeout"]:
    """
    Check if maximum polling iterations reached.
    """
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_poll_attempts", 100)

    if iteration >= max_iterations:
        return "timeout"
    return "continue"


def route_after_poll(state: dict[str, Any]) -> Literal["check", "timeout"]:
    """
    Route after poll based on iteration count and max attempts.
    """
    iteration = state.get("poll_count", 0)
    max_attempts = state.get("max_poll_attempts", 100)

    if iteration >= max_attempts:
        return "timeout"
    return "check"
