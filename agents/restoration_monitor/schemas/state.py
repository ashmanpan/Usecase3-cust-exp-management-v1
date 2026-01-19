"""Restoration Monitor Agent State Schema - From DESIGN.md"""
from typing import TypedDict, Optional, List, Any, Literal
from datetime import datetime


class RestorationMonitorState(TypedDict, total=False):
    """
    LangGraph state for Restoration Monitor workflow.
    From DESIGN.md: POLL_SLA -> CHECK_RECOVERY -> START_TIMER -> WAIT_TIMER ->
                    VERIFY_STABILITY -> CUTOVER_TRAFFIC -> CLEANUP_TUNNEL -> RETURN_RESTORED
    """
    # Task identification
    task_id: str
    task_type: str
    incident_id: Optional[str]
    correlation_id: Optional[str]

    # Restoration context from request
    protection_tunnel_id: str
    original_path_source: str
    original_path_dest: str
    sla_tier: str
    cutover_mode: Literal["immediate", "gradual"]

    # SLA monitoring state
    current_metrics: Optional[dict[str, Any]]
    sla_recovered: bool
    recovery_time: Optional[str]  # ISO format datetime

    # Hold timer state
    timer_id: Optional[str]
    timer_started: bool
    timer_expired: bool
    timer_cancelled: bool

    # Stability verification
    stability_checks: int
    stability_verified: bool
    last_stability_check: Optional[str]  # ISO format datetime

    # Cutover state
    cutover_started: bool
    cutover_complete: bool
    current_cutover_stage: int
    cutover_stages_completed: List[dict[str, Any]]

    # Cleanup state
    tunnel_deleted: bool
    bsid_released: Optional[int]

    # Workflow tracking
    poll_count: int
    max_poll_attempts: int
    iteration: int
    stage: str
    status: Literal["pending", "monitoring", "hold_timer", "verifying", "cutover", "cleanup", "completed", "failed"]
    error: Optional[str]

    # Timing
    protection_start_time: Optional[str]
    total_protection_duration_seconds: Optional[float]

    # Result
    result: Optional[dict[str, Any]]
