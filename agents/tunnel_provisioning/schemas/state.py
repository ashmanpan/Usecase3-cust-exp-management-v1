"""Tunnel Provisioning Agent State Schema - From DESIGN.md"""
from typing import TypedDict, List, Optional, Literal, Any

class TunnelProvisioningState(TypedDict, total=False):
    task_id: str
    incident_id: str
    correlation_id: Optional[str]
    # Input
    service_id: str
    head_end: str
    end_point: str
    computed_path: dict
    path_type: Literal["dynamic", "explicit"]
    requested_te_type: Optional[str]
    input_payload: dict
    # Detection
    detected_te_type: str
    device_capabilities: dict
    # Payload
    tunnel_payload: dict
    binding_sid: Optional[int]
    color: Optional[int]
    # Creation
    tunnel_id: Optional[str]
    creation_success: bool
    creation_error: Optional[str]
    retry_count: int
    # Verification
    tunnel_verified: bool
    operational_status: str
    # Steering
    traffic_steered: bool
    # Workflow
    current_node: str
    nodes_executed: List[str]
    status: Literal["running", "success", "failed", "escalated"]
    error: Optional[str]
    started_at: str
    completed_at: Optional[str]
    result: Optional[dict]
