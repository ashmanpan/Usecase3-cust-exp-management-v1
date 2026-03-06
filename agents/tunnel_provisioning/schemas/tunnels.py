"""Tunnel Schemas - From DESIGN.md"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class TunnelConfig(BaseModel):
    te_type: Literal["sr-mpls", "srv6", "rsvp-te"]
    head_end: str
    end_point: str
    path_name: str
    color: Optional[int] = None
    binding_sid: Optional[int] = None
    path_type: Literal["dynamic", "explicit"] = "dynamic"
    optimization_objective: str = "delay"
    protected: bool = True
    explicit_hops: Optional[List[dict]] = None
    segment_sids: Optional[List[int]] = None
    bandwidth_gbps: Optional[float] = None
    setup_priority: Optional[int] = None
    hold_priority: Optional[int] = None
    # Provisioning mode — overrides TUNNEL_PROVISIONING_MODE env var when set.
    # "nso" = PCC-initiated (NSO pushes config to router, config visible on device)
    # "pce" = PCE-initiated (COE REST → PCEP, no config on router)
    # None  = use TUNNEL_PROVISIONING_MODE env var (default "nso")
    provisioning_mode: Optional[Literal["nso", "pce"]] = None

class TunnelResult(BaseModel):
    success: bool
    tunnel_id: Optional[str] = None
    binding_sid: Optional[int] = None
    te_type: str
    operational_status: Literal["up", "down", "unknown"] = "unknown"
    state: Literal["success", "failure", "degraded"] = "failure"
    message: str = ""

class BSIDAllocation(BaseModel):
    head_end: str
    te_type: Literal["sr-mpls", "srv6"]
    bsid: int
    allocated_at: str
