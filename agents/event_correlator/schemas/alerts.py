"""
Alert Schemas

Based on DESIGN.md alert normalization and input schemas.
"""

from typing import Any, Optional, Literal, List
from datetime import datetime
from pydantic import BaseModel, Field


class NormalizedAlert(BaseModel):
    """
    Normalized Alert Schema

    From DESIGN.md - internal alert format after normalization.
    """
    alert_id: str
    source: Literal["pca", "cnc", "proactive"]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Link identification
    link_id: str
    interface_a: str  # e.g., "PE1:GigE0/0/0/1"
    interface_z: str  # e.g., "P1:GigE0/0/0/2"

    # SLA metrics (from PCA)
    latency_ms: Optional[float] = None
    jitter_ms: Optional[float] = None
    packet_loss_pct: Optional[float] = None

    # Thresholds violated
    violated_thresholds: List[str] = Field(default_factory=list)

    # Severity
    severity: Literal["critical", "major", "minor", "warning"]

    # Raw alert for audit
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "alert_id": "PCA-ALERT-001",
                "source": "pca",
                "link_id": "link-pe1-p1-001",
                "interface_a": "PE1:GigE0/0/0/1",
                "interface_z": "P1:GigE0/0/0/2",
                "latency_ms": 75.5,
                "violated_thresholds": ["latency"],
                "severity": "major",
            }
        }


class PCAAlert(BaseModel):
    """
    PCA Webhook Alert

    From DESIGN.md - Tool 1: PCA Webhook Handler.
    """
    alert_id: str
    probe_id: str
    metric_type: Literal["latency", "jitter", "loss"]
    current_value: float
    threshold_value: float
    source_ip: str
    dest_ip: str
    timestamp: str

    class Config:
        json_schema_extra = {
            "example": {
                "alert_id": "PCA-001",
                "probe_id": "probe-sj-ny-001",
                "metric_type": "latency",
                "current_value": 75.5,
                "threshold_value": 50.0,
                "source_ip": "10.1.1.1",
                "dest_ip": "10.2.1.1",
                "timestamp": "2026-01-19T10:00:00Z",
            }
        }


class CNCAlarm(BaseModel):
    """
    CNC Alarm

    From DESIGN.md - Tool 2: CNC Alarm Handler.
    """
    alarm_id: str
    alarm_type: str
    severity: Literal["critical", "major", "minor", "warning", "clear"]
    resource_type: str
    resource_id: str
    description: str
    timestamp: str
    additional_info: dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "alarm_id": "CNC-ALM-001",
                "alarm_type": "LINK_DEGRADATION",
                "severity": "major",
                "resource_type": "link",
                "resource_id": "link-pe1-p1-001",
                "description": "Link performance degraded",
                "timestamp": "2026-01-19T10:00:00Z",
            }
        }


class CorrelatedEvent(BaseModel):
    """
    Correlated Event

    Output of correlation logic - grouped related alerts.
    """
    incident_id: str
    primary_alert_id: str
    correlated_alert_ids: List[str] = Field(default_factory=list)
    alert_count: int = 1

    # Aggregated data
    degraded_links: List[str] = Field(default_factory=list)
    severity: Literal["critical", "major", "minor", "warning"]

    # Correlation metadata
    correlation_rule: Optional[str] = None
    correlation_reason: Optional[str] = None

    # Flap detection
    is_flapping: bool = False
    dampen_until: Optional[str] = None

    # Timestamps
    first_alert_time: datetime
    last_alert_time: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "incident_id": "INC-2026-0001",
                "primary_alert_id": "PCA-ALERT-001",
                "correlated_alert_ids": ["PCA-ALERT-002", "CNC-ALM-001"],
                "alert_count": 3,
                "degraded_links": ["link-pe1-p1-001"],
                "severity": "critical",
                "correlation_rule": "same_link_multiple_metrics",
                "is_flapping": False,
            }
        }
