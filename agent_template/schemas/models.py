"""
Domain Models for Customer Experience Management

These Pydantic models represent the core domain objects used across agents.
"""

from typing import Any, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class ServiceInfo(BaseModel):
    """Information about a network service"""
    service_id: str
    service_name: str
    customer_id: str
    customer_name: Optional[str] = None
    sla_tier: Literal["platinum", "gold", "silver", "bronze"]

    # Endpoints
    source_pe: str
    destination_pe: str

    # Current path info
    current_path_type: Literal["rsvp-te", "sr-mpls", "srv6"]
    current_path_id: Optional[str] = None

    # SLA targets
    target_latency_ms: Optional[float] = None
    target_jitter_ms: Optional[float] = None
    target_packet_loss_pct: Optional[float] = None
    target_availability_pct: Optional[float] = None

    # Status
    status: Literal["healthy", "degraded", "down"] = "healthy"

    class Config:
        json_schema_extra = {
            "example": {
                "service_id": "SVC-001",
                "service_name": "Enterprise VPN - Acme Corp",
                "customer_id": "CUST-100",
                "customer_name": "Acme Corporation",
                "sla_tier": "platinum",
                "source_pe": "PE-SJ-01",
                "destination_pe": "PE-NY-01",
                "current_path_type": "sr-mpls",
                "target_latency_ms": 50.0,
                "target_availability_pct": 99.99
            }
        }


class PathSegment(BaseModel):
    """A segment in a network path"""
    node_id: str
    node_name: Optional[str] = None
    interface_id: Optional[str] = None
    segment_id: Optional[int] = None  # SID for SR
    hop_index: int


class PathInfo(BaseModel):
    """Information about a network path"""
    path_id: str
    path_type: Literal["rsvp-te", "sr-mpls", "srv6"]

    # Endpoints
    head_end: str
    tail_end: str

    # Path details
    segments: list[PathSegment] = Field(default_factory=list)
    segment_list: list[int] = Field(default_factory=list, description="Ordered SID list")

    # Metrics
    igp_metric: Optional[int] = None
    te_metric: Optional[int] = None
    latency_ms: Optional[float] = None
    bandwidth_mbps: Optional[float] = None

    # Constraints used
    constraints: dict[str, Any] = Field(default_factory=dict)
    avoided_links: list[str] = Field(default_factory=list)
    avoided_nodes: list[str] = Field(default_factory=list)

    # Computation metadata
    computed_at: datetime = Field(default_factory=datetime.utcnow)
    computation_time_ms: Optional[int] = None

    class Config:
        json_schema_extra = {
            "example": {
                "path_id": "PATH-001",
                "path_type": "sr-mpls",
                "head_end": "PE-SJ-01",
                "tail_end": "PE-NY-01",
                "segment_list": [16001, 16005, 16010, 16015],
                "igp_metric": 40,
                "latency_ms": 45.5
            }
        }


class TunnelInfo(BaseModel):
    """Information about a provisioned tunnel"""
    tunnel_id: str
    tunnel_name: Optional[str] = None

    # Type
    te_type: Literal["rsvp-te", "sr-mpls", "srv6"]
    path_type: Literal["dynamic", "explicit"] = "explicit"

    # Endpoints
    head_end: str
    tail_end: str

    # SR-specific
    binding_sid: Optional[int] = None
    segment_list: list[int] = Field(default_factory=list)

    # RSVP-TE specific
    setup_priority: Optional[int] = None
    hold_priority: Optional[int] = None

    # Status
    admin_status: Literal["up", "down"] = "up"
    oper_status: Literal["up", "down", "unknown"] = "unknown"

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None  # Agent that created it
    incident_id: Optional[str] = None  # Related incident

    # Protection
    is_protection_tunnel: bool = False
    protects_tunnel_id: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "tunnel_id": "TUN-PROT-001",
                "tunnel_name": "Protection_PE-SJ-01_to_PE-NY-01",
                "te_type": "sr-mpls",
                "head_end": "PE-SJ-01",
                "tail_end": "PE-NY-01",
                "binding_sid": 900001,
                "segment_list": [16002, 16006, 16011, 16015],
                "oper_status": "up",
                "is_protection_tunnel": True
            }
        }


class AlertInfo(BaseModel):
    """Information about a network alert"""
    alert_id: str
    alert_source: Literal["pca", "cnc", "proactive", "syslog", "snmp"]

    # Alert details
    alert_type: str
    severity: Literal["critical", "major", "minor", "warning", "info"]
    message: str

    # Affected entities
    affected_links: list[str] = Field(default_factory=list)
    affected_nodes: list[str] = Field(default_factory=list)
    affected_services: list[str] = Field(default_factory=list)

    # Timestamps
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    cleared_at: Optional[datetime] = None

    # Correlation
    incident_id: Optional[str] = None
    correlated_alert_ids: list[str] = Field(default_factory=list)

    # Raw data
    raw_data: dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "alert_id": "ALERT-2026-0001",
                "alert_source": "pca",
                "alert_type": "sla_violation",
                "severity": "critical",
                "message": "Latency exceeded threshold on link PE-SJ-01--P-01",
                "affected_links": ["link-sj-p01-001"],
                "affected_services": ["SVC-001", "SVC-002"]
            }
        }


class SLAMetrics(BaseModel):
    """SLA metrics for a service or path"""
    # Identifiers
    service_id: Optional[str] = None
    path_id: Optional[str] = None
    link_id: Optional[str] = None

    # Current metrics
    latency_ms: Optional[float] = None
    jitter_ms: Optional[float] = None
    packet_loss_pct: Optional[float] = None
    bandwidth_utilization_pct: Optional[float] = None

    # SLA thresholds
    latency_threshold_ms: Optional[float] = None
    jitter_threshold_ms: Optional[float] = None
    packet_loss_threshold_pct: Optional[float] = None
    bandwidth_threshold_pct: Optional[float] = None

    # Status
    is_violated: bool = False
    violated_metrics: list[str] = Field(default_factory=list)

    # Measurement metadata
    measured_at: datetime = Field(default_factory=datetime.utcnow)
    measurement_source: Optional[str] = None
    sample_count: Optional[int] = None

    class Config:
        json_schema_extra = {
            "example": {
                "service_id": "SVC-001",
                "latency_ms": 75.5,
                "latency_threshold_ms": 50.0,
                "jitter_ms": 5.2,
                "is_violated": True,
                "violated_metrics": ["latency"]
            }
        }


class DemandMatrixEntry(BaseModel):
    """Traffic demand between two PE routers"""
    source_pe: str
    destination_pe: str

    # Traffic volumes
    current_traffic_mbps: float
    peak_traffic_mbps: Optional[float] = None
    average_traffic_mbps: Optional[float] = None

    # Predictions
    predicted_traffic_mbps: Optional[float] = None
    prediction_horizon_minutes: Optional[int] = None
    prediction_confidence: Optional[float] = None

    # Risk assessment
    congestion_risk: Literal["low", "medium", "high", "critical"] = "low"
    headroom_pct: Optional[float] = None

    # Timestamps
    measured_at: datetime = Field(default_factory=datetime.utcnow)


class IncidentInfo(BaseModel):
    """Information about an incident being handled"""
    incident_id: str
    incident_type: Literal["sla_violation", "link_down", "node_failure", "congestion", "manual"]

    # Status
    status: Literal["new", "investigating", "mitigating", "monitoring", "resolved", "closed"]
    severity: Literal["critical", "major", "minor", "warning"]

    # Description
    title: str
    description: Optional[str] = None

    # Affected entities
    degraded_links: list[str] = Field(default_factory=list)
    affected_services: list[dict[str, Any]] = Field(default_factory=list)

    # Actions taken
    protection_tunnel_id: Optional[str] = None
    actions_taken: list[dict[str, Any]] = Field(default_factory=list)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None

    # Correlation
    related_alert_ids: list[str] = Field(default_factory=list)
    root_cause: Optional[str] = None
