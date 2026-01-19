"""
A2A Task Schemas

Defines input/output schemas for A2A protocol communication between agents.
Based on Google A2A (Agent-to-Agent) specification.
"""

from typing import Any, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import uuid4


class TaskStatus(BaseModel):
    """Status of an A2A task"""
    state: Literal["pending", "running", "completed", "failed", "cancelled"]
    progress: Optional[int] = Field(None, ge=0, le=100, description="Progress percentage")
    message: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TaskInput(BaseModel):
    """
    A2A Task Input Schema

    This is what an agent receives when called via A2A protocol.
    """
    # Task identification
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    task_type: str = Field(..., description="Type of task to perform")

    # Context
    incident_id: Optional[str] = Field(None, description="Related incident ID")
    correlation_id: Optional[str] = Field(None, description="For distributed tracing")
    parent_task_id: Optional[str] = Field(None, description="Parent task if subtask")

    # Payload
    payload: dict[str, Any] = Field(default_factory=dict)

    # Metadata
    priority: int = Field(default=5, ge=1, le=10, description="1=highest, 10=lowest")
    timeout_seconds: int = Field(default=300)
    callback_url: Optional[str] = Field(None, description="URL to POST result")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task-123-456",
                "task_type": "assess_impact",
                "incident_id": "INC-2026-0001",
                "payload": {
                    "degraded_links": ["link-001", "link-002"],
                    "severity": "critical"
                },
                "priority": 1,
                "timeout_seconds": 60
            }
        }


class TaskOutput(BaseModel):
    """
    A2A Task Output Schema

    This is what an agent returns after processing a task.
    """
    # Task identification
    task_id: str
    task_type: str

    # Status
    status: TaskStatus

    # Result
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None

    # Metadata
    agent_name: str
    agent_version: str

    # Timing
    started_at: datetime
    completed_at: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: Optional[int] = None

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task-123-456",
                "task_type": "assess_impact",
                "status": {
                    "state": "completed",
                    "progress": 100,
                    "message": "Impact assessment complete"
                },
                "result": {
                    "total_affected": 15,
                    "services_by_tier": {"platinum": 2, "gold": 5}
                },
                "agent_name": "service_impact_agent",
                "agent_version": "1.0.0",
                "started_at": "2026-01-19T10:00:00Z",
                "completed_at": "2026-01-19T10:00:05Z",
                "duration_ms": 5000
            }
        }


class AgentCapability(BaseModel):
    """Describes a single agent capability"""
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class AgentCard(BaseModel):
    """
    A2A Agent Card

    Describes the agent's capabilities for service discovery.
    Other agents use this to understand what this agent can do.
    """
    # Identity
    name: str
    version: str
    description: str

    # Endpoint
    url: str
    protocol: Literal["a2a", "grpc", "http"] = "a2a"

    # Capabilities
    capabilities: list[AgentCapability]

    # Task types this agent handles
    supported_task_types: list[str]

    # Metadata
    tags: list[str] = Field(default_factory=list)
    owner: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "service_impact_agent",
                "version": "1.0.0",
                "description": "Assesses service impact from network degradation",
                "url": "http://service-impact-agent:8080",
                "protocol": "a2a",
                "capabilities": [
                    {
                        "name": "assess_impact",
                        "description": "Assess service impact from degraded links",
                        "input_schema": {"type": "object"},
                        "output_schema": {"type": "object"}
                    }
                ],
                "supported_task_types": ["assess_impact"],
                "tags": ["service", "impact", "sla"]
            }
        }


# ============== Agent-Specific Task Types ==============
# Define specific task input/output for each agent type

class CorrelateAlertInput(BaseModel):
    """Input for Event Correlator's correlate_alert task"""
    alert_source: Literal["pca", "cnc", "proactive"]
    raw_alert: dict[str, Any]


class CorrelateAlertOutput(BaseModel):
    """Output from Event Correlator's correlate_alert task"""
    incident_id: str
    degraded_links: list[str]
    severity: str
    alert_count: int
    is_flapping: bool
    correlated_alerts: list[dict[str, Any]]


class AssessImpactInput(BaseModel):
    """Input for Service Impact Agent's assess_impact task"""
    incident_id: str
    degraded_links: list[str]


class AssessImpactOutput(BaseModel):
    """Output from Service Impact Agent's assess_impact task"""
    incident_id: str
    total_affected: int
    services_by_tier: dict[str, int]
    affected_services: list[dict[str, Any]]


class ComputePathInput(BaseModel):
    """Input for Path Computation Agent's compute_path task"""
    incident_id: str
    source_pe: str
    destination_pe: str
    degraded_links: list[str]
    service_sla_tier: str
    current_te_type: Optional[str] = None


class ComputePathOutput(BaseModel):
    """Output from Path Computation Agent's compute_path task"""
    incident_id: str
    path_found: bool
    path: Optional[dict[str, Any]] = None
    computation_time_ms: Optional[int] = None


class ProvisionTunnelInput(BaseModel):
    """Input for Tunnel Provisioning Agent's provision_tunnel task"""
    incident_id: str
    service_id: str
    te_type: Literal["rsvp-te", "sr-mpls", "srv6"]
    head_end: str
    end_point: str
    computed_path: dict[str, Any]
    path_type: Literal["dynamic", "explicit"] = "explicit"


class ProvisionTunnelOutput(BaseModel):
    """Output from Tunnel Provisioning Agent's provision_tunnel task"""
    incident_id: str
    success: bool
    tunnel_id: Optional[str] = None
    binding_sid: Optional[int] = None
    te_type: str
    operational_status: Optional[str] = None
    error: Optional[str] = None


class MonitorRestorationInput(BaseModel):
    """Input for Restoration Monitor Agent's monitor_restoration task"""
    incident_id: str
    protection_tunnel_id: str
    original_path: dict[str, Any]
    sla_tier: str
    cutover_mode: Literal["immediate", "gradual"]


class MonitorRestorationOutput(BaseModel):
    """Output from Restoration Monitor Agent's monitor_restoration task"""
    incident_id: str
    restored: bool
    hold_timer_seconds: int
    cutover_mode: str
    tunnel_deleted: bool
    total_protection_duration_seconds: int
