"""
Event Correlator Agent State Schema

Based on DESIGN.md - EventCorrelatorState.
"""

from typing import Any, TypedDict, Optional, List


class EventCorrelatorState(TypedDict, total=False):
    """
    Event Correlator Agent State Schema

    From DESIGN.md - EventCorrelatorState TypedDict
    """

    # ============== Task Identification ==============
    task_id: str
    correlation_id: Optional[str]

    # ============== Input Alert ==============
    alert_source: str  # pca, cnc, proactive
    raw_alert: dict[str, Any]

    # ============== Processing State ==============
    normalized_alert: Optional[dict]
    is_duplicate: bool
    duplicate_of: Optional[str]  # ID of original alert

    # ============== Correlation ==============
    correlated_alerts: List[dict]  # List of related alerts
    correlation_rule: Optional[str]  # Which rule matched
    incident_id: Optional[str]  # Created or existing incident

    # ============== Flap Detection ==============
    is_flapping: bool
    flap_count: int
    dampen_seconds: int
    dampen_until: Optional[str]  # ISO timestamp

    # ============== Output ==============
    degraded_links: List[str]
    severity: str
    alert_count: int

    # ============== Execution Tracking ==============
    current_node: str
    nodes_executed: List[str]
    started_at: str

    # ============== Result ==============
    action_taken: str  # emit_incident, suppress, discard
    result: Optional[dict]
    error: Optional[str]
