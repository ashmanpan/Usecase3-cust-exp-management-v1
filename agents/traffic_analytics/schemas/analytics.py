"""Analytics Data Schemas - From DESIGN.md"""
from typing import Optional, List, Literal, Tuple
from datetime import datetime
from pydantic import BaseModel, Field


class DemandMatrix(BaseModel):
    """PE-to-PE traffic demand matrix - From DESIGN.md"""
    matrix: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="PE-to-PE demand matrix: {src_pe: {dst_pe: gbps}}",
    )
    timestamp: datetime = Field(default_factory=datetime.now)

    def get_demand(self, src: str, dst: str) -> float:
        """Get demand between two PEs"""
        return self.matrix.get(src, {}).get(dst, 0.0)

    def get_total_demand(self) -> float:
        """Get total demand across all PE pairs"""
        total = 0.0
        for src_demands in self.matrix.values():
            total += sum(src_demands.values())
        return total

    def get_pe_count(self) -> int:
        """Get number of unique PEs"""
        pes = set(self.matrix.keys())
        for demands in self.matrix.values():
            pes.update(demands.keys())
        return len(pes)


class CongestionRisk(BaseModel):
    """Congestion risk assessment for a link - From DESIGN.md"""
    link_id: str
    link_endpoints: Tuple[str, str] = Field(default=("", ""))
    current_utilization: float = Field(..., ge=0.0, le=1.0)
    projected_utilization: float = Field(..., ge=0.0)
    capacity_gbps: float
    current_traffic_gbps: float = 0.0
    projected_traffic_gbps: float = 0.0
    risk_level: Literal["low", "medium", "high"]
    affected_pe_pairs: List[Tuple[str, str]] = Field(default_factory=list)
    affected_services: List[str] = Field(default_factory=list)


class ProactiveAlert(BaseModel):
    """
    Proactive alert generated BEFORE SLA degradation.
    From DESIGN.md: Triggers same protection workflow as reactive alerts.
    """
    alert_type: Literal["proactive"] = "proactive"
    alert_id: str
    timestamp: datetime = Field(default_factory=datetime.now)

    # Predicted congestion
    at_risk_links: List[str]
    predicted_utilization: float
    time_to_congestion_minutes: Optional[int] = None

    # Services that will be affected
    at_risk_services: List[str] = Field(default_factory=list)
    highest_sla_tier: str = "silver"

    # Recommendation
    recommended_action: Literal["pre_provision_tunnel", "load_balance", "alert_only"] = "alert_only"


class RiskAnalysis(BaseModel):
    """Risk analysis result"""
    overall_risk_level: Literal["low", "medium", "high"]
    high_risk_links: List[CongestionRisk] = Field(default_factory=list)
    medium_risk_links: List[CongestionRisk] = Field(default_factory=list)
    total_at_risk_services: int = 0
    highest_sla_tier: str = "bronze"
    recommended_action: Literal["pre_provision_tunnel", "load_balance", "alert_only"] = "alert_only"


class AnalyticsResponse(BaseModel):
    """Traffic analytics response - A2A task response"""
    task_id: str
    analysis_timestamp: datetime = Field(default_factory=datetime.now)

    # Demand matrix summary
    pe_count: int = 0
    total_demand_gbps: float = 0.0

    # Congestion prediction summary
    high_risk_count: int = 0
    medium_risk_count: int = 0
    max_utilization: float = 0.0

    # Risk analysis
    overall_risk_level: str = "low"
    at_risk_links: List[str] = Field(default_factory=list)
    at_risk_services: List[str] = Field(default_factory=list)

    # Alert status
    proactive_alert_emitted: bool = False
    alert_id: Optional[str] = None

    # Error
    error: Optional[str] = None


class BuildMatrixInput(BaseModel):
    """Input for demand matrix building - From DESIGN.md Tool 2"""
    telemetry_data: dict  # TelemetryData as dict


class BuildMatrixOutput(BaseModel):
    """Output from demand matrix building"""
    matrix: DemandMatrix
    pe_count: int
    total_demand_gbps: float


class PredictCongestionInput(BaseModel):
    """Input for congestion prediction - From DESIGN.md Tool 3"""
    demand_matrix: dict  # DemandMatrix as dict


class PredictCongestionOutput(BaseModel):
    """Output from congestion prediction"""
    risks: List[CongestionRisk]
    high_risk_count: int
    medium_risk_count: int


class EmitProactiveAlertInput(BaseModel):
    """Input for proactive alert emission - From DESIGN.md Tool 4"""
    risks: List[CongestionRisk]
    at_risk_services: List[str] = Field(default_factory=list)
    highest_sla_tier: str = "silver"


class EmitProactiveAlertOutput(BaseModel):
    """Output from proactive alert emission"""
    alert_id: str
    sent_to_orchestrator: bool
