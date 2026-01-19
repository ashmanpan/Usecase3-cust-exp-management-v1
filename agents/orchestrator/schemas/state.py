"""
Orchestrator Agent State Schema

Based on DESIGN.md - LangGraph State Schema for Orchestrator Agent.
"""

from typing import Any, TypedDict, Optional, Literal, List
from enum import Enum


# Status values as per DESIGN.md
IncidentStatus = Literal[
    "detecting",
    "assessing",
    "computing",
    "provisioning",
    "steering",
    "monitoring",
    "restoring",
    "closed",
    "escalated",
    "dampening",
]

AlertType = Literal["pca_sla", "cnc_alarm", "proactive"]

Severity = Literal["critical", "major", "minor", "warning"]

CutoverMode = Literal["immediate", "gradual"]


class OrchestratorState(TypedDict, total=False):
    """
    Orchestrator Agent State Schema

    From DESIGN.md - IncidentState TypedDict
    """

    # ============== Task Identification (from template) ==============
    task_id: str
    correlation_id: Optional[str]

    # ============== Incident Identification ==============
    incident_id: str
    status: IncidentStatus

    # ============== Alert Data ==============
    alert_type: AlertType
    degraded_links: List[str]
    severity: Severity

    # ============== Affected Services ==============
    # List of {service_id, type, sla_tier, endpoints}
    affected_services: List[dict]

    # ============== Protection Path ==============
    # {path_id, segments, te_type, metrics}
    alternate_path: Optional[dict]
    tunnel_id: Optional[str]
    binding_sid: Optional[int]

    # ============== Restoration ==============
    hold_timer_start: Optional[str]  # ISO timestamp
    sla_recovered: bool
    cutover_mode: CutoverMode
    cutover_progress: Optional[int]  # 0-100%

    # ============== Workflow Control ==============
    retry_count: int
    max_retries: int
    error_message: Optional[str]
    llm_reasoning: Optional[str]  # For edge cases

    # ============== Execution Tracking (from template) ==============
    current_node: str
    nodes_executed: List[str]
    started_at: str

    # ============== A2A Communication ==============
    a2a_tasks_sent: List[dict]
    a2a_responses: dict

    # ============== Final Result ==============
    result: Optional[dict]
    final_status: str  # success, failed, escalated


def create_initial_state(
    task_id: str,
    incident_id: str,
    alert_type: AlertType,
    degraded_links: List[str],
    severity: Severity,
    correlation_id: Optional[str] = None,
) -> OrchestratorState:
    """
    Create initial state for orchestrator workflow.

    Args:
        task_id: Unique task identifier
        incident_id: Incident identifier
        alert_type: Type of alert (pca_sla, cnc_alarm, proactive)
        degraded_links: List of degraded link IDs
        severity: Alert severity
        correlation_id: Optional correlation ID for tracing

    Returns:
        Initial OrchestratorState
    """
    from datetime import datetime

    return OrchestratorState(
        # Task identification
        task_id=task_id,
        correlation_id=correlation_id,
        # Incident identification
        incident_id=incident_id,
        status="detecting",
        # Alert data
        alert_type=alert_type,
        degraded_links=degraded_links,
        severity=severity,
        # Affected services (populated by assess node)
        affected_services=[],
        # Protection path (populated by compute/provision nodes)
        alternate_path=None,
        tunnel_id=None,
        binding_sid=None,
        # Restoration
        hold_timer_start=None,
        sla_recovered=False,
        cutover_mode="gradual",
        cutover_progress=None,
        # Workflow control
        retry_count=0,
        max_retries=3,
        error_message=None,
        llm_reasoning=None,
        # Execution tracking
        current_node="start",
        nodes_executed=[],
        started_at=datetime.utcnow().isoformat(),
        # A2A communication
        a2a_tasks_sent=[],
        a2a_responses={},
        # Result
        result=None,
        final_status="running",
    )
