"""
Service Schemas

Pydantic models for services and impact assessment.
From DESIGN.md Service Impact Agent.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class ServiceEndpoint(BaseModel):
    """Service endpoint details."""

    device_name: str = Field(..., description="PE router name")
    device_ip: str = Field(..., description="Management IP")
    interface_name: str = Field(..., description="Interface name")
    vrf_name: Optional[str] = Field(None, description="VRF name for L3VPN")
    vlan_id: Optional[int] = Field(None, description="VLAN ID for L2VPN")


class ServiceDetails(BaseModel):
    """
    Detailed service information from CNC.

    From DESIGN.md: Service details include endpoints, TE type, and path.
    """

    service_id: str
    service_name: str
    service_type: Literal["l3vpn", "l2vpn", "evpn", "p2p"]

    # Endpoints
    endpoint_a: ServiceEndpoint
    endpoint_z: ServiceEndpoint

    # Customer info
    customer_id: str
    customer_name: str

    # SLA info
    sla_tier: Literal["platinum", "gold", "silver", "bronze"]

    # TE type and path
    current_te_type: Literal["rsvp-te", "sr-mpls", "srv6", "igp"]
    current_path: List[str] = Field(default_factory=list)

    # Bandwidth
    committed_bandwidth_mbps: Optional[float] = None
    current_utilization_pct: Optional[float] = None


class AffectedService(BaseModel):
    """
    Affected service with impact assessment.

    From DESIGN.md: AffectedService schema with impact level.
    """

    service_id: str
    service_name: str
    service_type: Literal["l3vpn", "l2vpn", "evpn", "p2p"]

    # Endpoints
    endpoint_a: str  # PE router A
    endpoint_z: str  # PE router Z

    # Customer info
    customer_id: str
    customer_name: str

    # SLA tier (determines priority)
    sla_tier: Literal["platinum", "gold", "silver", "bronze"]

    # Current path info
    current_te_type: Literal["rsvp-te", "sr-mpls", "srv6", "igp"]
    current_path: List[str] = Field(default_factory=list)

    # Impact assessment
    impact_level: Literal["full_outage", "degraded", "at_risk"]
    redundancy_available: bool

    # Degraded link affecting this service
    affected_by_link: str

    # Priority score (computed from SLA tier and impact)
    priority_score: int = 0


class ServiceImpactResponse(BaseModel):
    """
    Response to Orchestrator with affected services.

    From DESIGN.md: ServiceImpactResponse schema.
    """

    incident_id: str
    total_affected: int
    services_by_tier: dict  # {"platinum": 5, "gold": 10, ...}
    services_by_type: dict  # {"l3vpn": 10, "l2vpn": 5, ...}
    affected_services: List[AffectedService]
    highest_priority_tier: Optional[str] = None
    auto_protect_required: bool = False
