"""Restoration Monitor Data Schemas - From DESIGN.md"""
from typing import Optional, List, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class SLAMetrics(BaseModel):
    """SLA metrics from PCA - From DESIGN.md"""
    latency_ms: float = Field(..., description="Measured latency in milliseconds")
    jitter_ms: float = Field(..., description="Measured jitter in milliseconds")
    packet_loss_pct: float = Field(..., description="Packet loss percentage")
    measurement_time: datetime = Field(default_factory=datetime.now)

    def meets_threshold(self, thresholds: dict) -> bool:
        """Check if metrics meet SLA thresholds"""
        return (
            self.latency_ms <= thresholds.get("max_latency_ms", float("inf"))
            and self.jitter_ms <= thresholds.get("max_jitter_ms", float("inf"))
            and self.packet_loss_pct <= thresholds.get("max_loss_pct", float("inf"))
        )


class HoldTimer(BaseModel):
    """Hold timer state - From DESIGN.md"""
    timer_id: str = Field(..., description="Timer ID (timer:{incident_id})")
    incident_id: str
    sla_tier: str
    recovery_time: datetime
    expiry_time: datetime
    status: Literal["waiting", "expired", "cancelled"] = "waiting"
    remaining_seconds: int = 0

    def is_expired(self) -> bool:
        """Check if hold timer has expired"""
        return datetime.now() >= self.expiry_time


class CutoverStage(BaseModel):
    """Cutover stage state - From DESIGN.md gradual cutover"""
    stage_index: int
    protection_weight: int = Field(..., ge=0, le=100)
    original_weight: int = Field(..., ge=0, le=100)
    completed_at: Optional[datetime] = None
    sla_verified: bool = False


class CutoverProgress(BaseModel):
    """Track gradual cutover progress"""
    incident_id: str
    mode: Literal["immediate", "gradual"]
    current_stage: int = 0
    total_stages: int = 4
    stages: List[CutoverStage] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    success: bool = False


class RestorationRequest(BaseModel):
    """Restoration monitoring request - From DESIGN.md A2A Task Schema"""
    incident_id: str = Field(..., description="Incident being monitored")
    protection_tunnel_id: str = Field(..., description="Protection tunnel to monitor")
    original_path: dict = Field(..., description="Original path endpoints {source, dest}")
    sla_tier: str = Field(default="silver", description="SLA tier for thresholds")
    cutover_mode: Literal["immediate", "gradual"] = Field(
        default="immediate",
        description="Cutover strategy: immediate or gradual"
    )


class RestorationResponse(BaseModel):
    """Restoration complete response - From DESIGN.md A2A Task Schema"""
    incident_id: str
    restored: bool = False
    hold_timer_seconds: int = 0
    cutover_mode: str = "immediate"
    tunnel_deleted: bool = False
    bsid_released: Optional[int] = None
    total_protection_duration_seconds: float = 0.0
    error: Optional[str] = None


class PollSLAInput(BaseModel):
    """Input for SLA polling - From DESIGN.md Tool 1"""
    source_pe: str
    dest_pe: str
    path_type: Literal["original", "protection"] = "original"


class PollSLAOutput(BaseModel):
    """Output from SLA polling"""
    metrics: SLAMetrics
    meets_sla: bool


class CheckTimerInput(BaseModel):
    """Input for timer check - From DESIGN.md Tool 2"""
    timer_id: str


class CheckTimerOutput(BaseModel):
    """Output from timer check"""
    expired: bool
    remaining_seconds: int


class UpdateWeightsInput(BaseModel):
    """Input for ECMP weight update - From DESIGN.md Tool 3"""
    protection_tunnel_id: str
    original_path_id: str
    protection_weight: int = Field(..., ge=0, le=100)
    original_weight: int = Field(..., ge=0, le=100)


class UpdateWeightsOutput(BaseModel):
    """Output from weight update"""
    success: bool
    message: str


class DeleteTunnelInput(BaseModel):
    """Input for tunnel deletion - From DESIGN.md Tool 4"""
    tunnel_id: str
    tunnel_type: Literal["sr-policy", "rsvp-te"]


class DeleteTunnelOutput(BaseModel):
    """Output from tunnel deletion"""
    success: bool
    bsid_released: Optional[int] = None
