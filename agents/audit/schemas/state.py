"""Audit Workflow State - From DESIGN.md"""
from typing import TypedDict, Optional, Any


class AuditState(TypedDict, total=False):
    """
    Audit Agent State - From DESIGN.md
    Flow: CAPTURE_EVENT -> FORMAT_LOG -> STORE_DB -> INDEX_ASYNC
    """

    # Task identification
    task_id: str
    task_type: str
    incident_id: Optional[str]
    correlation_id: Optional[str]

    # Input payload
    payload: dict[str, Any]

    # Captured event data
    event_type: str
    agent_name: str
    node_name: Optional[str]
    event_payload: dict[str, Any]
    previous_state: Optional[str]
    new_state: Optional[str]
    decision_type: Optional[str]
    decision_reasoning: Optional[str]
    actor: str

    # Formatted log
    event_id: str
    timestamp: str
    formatted_log: dict[str, Any]
    log_formatted: bool

    # Storage state
    db_stored: bool
    db_store_error: Optional[str]

    # Index state (async)
    indexed: bool
    index_error: Optional[str]
    es_enabled: bool

    # Timeline query (for get_timeline)
    timeline_events: list[dict[str, Any]]
    timeline_count: int

    # Report generation (for generate_report)
    report_start_date: Optional[str]
    report_end_date: Optional[str]
    report_data: dict[str, Any]

    # Workflow tracking
    iteration: int
    stage: str
    status: str
    error: Optional[str]

    # Result
    result: dict[str, Any]
