"""
Path Computation Agent State Schema

TypedDict for LangGraph workflow state.
From DESIGN.md Path Computation Agent.
"""

from typing import TypedDict, List, Optional, Literal, Any


class PathComputationState(TypedDict, total=False):
    """
    Path Computation workflow state.

    From DESIGN.md workflow:
    BUILD_CONSTRAINTS -> QUERY_KG -> VALIDATE_PATH -> RETURN_PATH
    Or: -> RELAX_CONSTRAINTS -> QUERY_KG (retry loop)
    """

    # Task identification
    task_id: str
    incident_id: str
    correlation_id: Optional[str]

    # Input from Orchestrator
    source_pe: str
    destination_pe: str
    degraded_links: List[str]
    avoid_nodes: List[str]
    avoid_srlgs: List[str]
    service_sla_tier: str
    current_te_type: str
    existing_policies: List[str]  # For disjointness
    required_sla: dict  # {max_delay_ms, min_bandwidth_gbps}
    input_payload: dict

    # Constraints
    constraints: dict
    original_constraints: dict  # Before relaxation
    relaxation_level: int

    # Query results
    path_found: bool
    computed_path: Optional[dict]
    query_attempts: int
    query_errors: List[str]

    # Validation
    path_valid: bool
    validation_violations: List[str]

    # Workflow control
    current_node: str
    nodes_executed: List[str]
    iteration_count: int
    max_iterations: int
    status: Literal["running", "success", "failed", "no_path"]
    error: Optional[str]

    # Timestamps
    started_at: str
    completed_at: Optional[str]

    # Result for Orchestrator
    result: Optional[dict]
