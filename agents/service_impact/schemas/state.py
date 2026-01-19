"""
Service Impact Agent State Schema

TypedDict for LangGraph workflow state.
From DESIGN.md Service Impact Agent.
"""

from typing import TypedDict, List, Optional, Literal, Any


class ServiceImpactState(TypedDict, total=False):
    """
    Service Impact workflow state.

    From DESIGN.md workflow:
    QUERY_SERVICES -> ANALYZE_IMPACT -> ENRICH_SLA -> RETURN_AFFECTED
    """

    # Task identification
    task_id: str
    incident_id: str
    correlation_id: Optional[str]

    # Input from Orchestrator
    degraded_links: List[str]
    severity: Literal["critical", "major", "minor", "warning"]
    input_payload: dict

    # Query results
    raw_services: List[dict]
    query_success: bool
    query_error: Optional[str]

    # Analyzed impact
    impact_assessment: dict
    total_affected: int
    services_by_tier: dict  # {"platinum": 5, "gold": 10, ...}
    services_by_type: dict  # {"l3vpn": 10, "l2vpn": 5, ...}

    # Enriched services
    affected_services: List[dict]
    highest_priority_tier: Optional[str]
    auto_protect_required: bool

    # Workflow control
    current_node: str
    nodes_executed: List[str]
    iteration_count: int
    max_iterations: int
    status: Literal["running", "success", "failed"]
    error: Optional[str]

    # Timestamps
    started_at: str
    completed_at: Optional[str]

    # Result for Orchestrator
    result: Optional[dict]
