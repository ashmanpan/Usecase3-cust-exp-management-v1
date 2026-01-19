"""Audit Event Schemas - From DESIGN.md"""
from datetime import datetime
from typing import Optional, Literal, Any
from uuid import uuid4
from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """Standard audit event for all workflow activities - From DESIGN.md"""

    # Event identification
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Context
    incident_id: Optional[str] = None
    agent_name: str
    node_name: Optional[str] = None

    # Event details
    event_type: Literal[
        "incident_created",
        "alert_correlated",
        "service_impact_assessed",
        "path_computed",
        "tunnel_provisioned",
        "traffic_steered",
        "sla_recovered",
        "restoration_complete",
        "escalation",
        "notification_sent",
        "error",
        "state_change",
    ]

    # Payload
    payload: dict[str, Any] = Field(default_factory=dict)

    # State change (if applicable)
    previous_state: Optional[str] = None
    new_state: Optional[str] = None

    # Decision tracking (for compliance)
    decision_type: Optional[Literal["rule_based", "llm_assisted", "human"]] = None
    decision_reasoning: Optional[str] = None

    # Actor
    actor: str = "system"


class AuditLog(BaseModel):
    """Collection of audit events for an incident - From DESIGN.md"""

    incident_id: str
    events: list[AuditEvent] = Field(default_factory=list)
    started_at: datetime
    completed_at: Optional[datetime] = None
    final_status: Optional[str] = None


class IncidentSummary(BaseModel):
    """Incident summary for compliance reports - From DESIGN.md"""

    incident_id: str
    created_at: datetime
    closed_at: Optional[datetime] = None
    status: str
    severity: Optional[str] = None
    degraded_links: list[dict[str, Any]] = Field(default_factory=list)
    affected_services: list[str] = Field(default_factory=list)
    protection_tunnel_id: Optional[str] = None
    total_duration_seconds: Optional[int] = None
    final_outcome: Optional[str] = None


class ComplianceReport(BaseModel):
    """Compliance report - From DESIGN.md"""

    start_date: datetime
    end_date: datetime
    incident_count: int
    avg_resolution_time_seconds: float
    llm_decisions_count: int
    error_count: int
    incidents: list[dict[str, Any]] = Field(default_factory=list)
