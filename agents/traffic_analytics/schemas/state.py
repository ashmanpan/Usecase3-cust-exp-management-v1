"""Traffic Analytics Agent State Schema - From DESIGN.md"""
from typing import TypedDict, Optional, List, Any, Literal


class TrafficAnalyticsState(TypedDict, total=False):
    """
    LangGraph state for Traffic Analytics workflow.
    From DESIGN.md: COLLECT_TELEMETRY -> BUILD_MATRIX -> PREDICT_CONGESTION ->
                    ANALYZE_RISK -> EMIT_PROACTIVE_ALERT | STORE_METRICS | WARN
    """
    # Task identification
    task_id: str
    task_type: str
    incident_id: Optional[str]
    correlation_id: Optional[str]

    # Telemetry collection state
    telemetry_sources: List[str]  # ["sr-pm", "mdt", "netflow"]
    telemetry_window_minutes: int
    telemetry_collected: bool
    raw_telemetry: Optional[dict[str, Any]]
    collection_time_ms: int

    # Demand matrix state
    demand_matrix: Optional[dict[str, Any]]
    pe_count: int
    total_demand_gbps: float
    matrix_built: bool

    # Congestion prediction state
    congestion_risks: List[dict[str, Any]]
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    max_utilization: float
    prediction_complete: bool

    # Risk analysis state
    risk_level: Literal["low", "medium", "high"]
    at_risk_links: List[str]
    at_risk_services: List[str]
    highest_sla_tier: Optional[str]
    time_to_congestion_minutes: Optional[int]
    recommended_action: Optional[Literal["pre_provision_tunnel", "load_balance", "alert_only"]]

    # Alert emission state
    proactive_alert_emitted: bool
    alert_id: Optional[str]
    sent_to_orchestrator: bool

    # Metrics storage state
    metrics_stored: bool

    # Workflow tracking
    iteration: int
    stage: str
    status: Literal["pending", "collecting", "building", "predicting", "analyzing", "alerting", "completed", "failed"]
    error: Optional[str]

    # Result
    result: Optional[dict[str, Any]]
