"""Telemetry Data Schemas - From DESIGN.md"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class SRPMMetric(BaseModel):
    """SR Performance Measurement metric - From DESIGN.md"""
    metric_id: str
    timestamp: datetime = Field(default_factory=datetime.now)

    # Path identification
    headend: str = Field(..., description="Head-end PE router")
    endpoint: str = Field(..., description="End-point PE router")

    # SR-MPLS identification
    sr_policy_bsid: Optional[int] = Field(None, description="SR Policy BSID")
    sr_policy_name: Optional[str] = None

    # SRv6 identification
    srv6_locator: Optional[str] = Field(None, description="SRv6 locator")
    source_locator: Optional[str] = None
    dest_locator: Optional[str] = None

    # Metrics
    traffic_gbps: float = Field(default=0.0, description="Traffic in Gbps")
    latency_ms: float = Field(default=0.0, description="One-way delay in ms")
    jitter_ms: float = Field(default=0.0, description="Delay variation in ms")
    packet_loss_pct: float = Field(default=0.0, description="Packet loss percentage")


class InterfaceCounter(BaseModel):
    """Model-Driven Telemetry interface counter - From DESIGN.md"""
    device_name: str
    interface_name: str
    timestamp: datetime = Field(default_factory=datetime.now)

    # Counters
    bytes_in: int = 0
    bytes_out: int = 0
    packets_in: int = 0
    packets_out: int = 0

    # Calculated rates
    bps_in: float = Field(default=0.0, description="Bits per second in")
    bps_out: float = Field(default=0.0, description="Bits per second out")
    pps_in: float = Field(default=0.0, description="Packets per second in")
    pps_out: float = Field(default=0.0, description="Packets per second out")

    # Utilization
    utilization_pct: float = Field(default=0.0, description="Interface utilization %")
    capacity_gbps: float = Field(default=10.0, description="Interface capacity in Gbps")


class FlowRecord(BaseModel):
    """NetFlow/IPFIX flow record - From DESIGN.md"""
    flow_id: str
    timestamp: datetime = Field(default_factory=datetime.now)

    # Flow identification
    src_ip: str
    dst_ip: str
    src_port: int = 0
    dst_port: int = 0
    protocol: int = 6  # TCP

    # SRv6 identification (if available)
    srv6_sid: Optional[str] = None
    srv6_locator: Optional[str] = None

    # Traffic stats
    bytes: int = 0
    packets: int = 0

    # Derived fields
    src_pe: Optional[str] = None
    dst_pe: Optional[str] = None


class TelemetryData(BaseModel):
    """Unified telemetry data from all sources - From DESIGN.md"""
    collection_timestamp: datetime = Field(default_factory=datetime.now)
    window_minutes: int = 5

    # Data from each source
    sr_pm: List[SRPMMetric] = Field(default_factory=list)
    mdt: List[InterfaceCounter] = Field(default_factory=list)
    netflow: List[FlowRecord] = Field(default_factory=list)

    # Collection stats
    sr_pm_count: int = 0
    mdt_count: int = 0
    netflow_count: int = 0
    collection_time_ms: int = 0

    def total_records(self) -> int:
        return len(self.sr_pm) + len(self.mdt) + len(self.netflow)


class CollectTelemetryInput(BaseModel):
    """Input for telemetry collection - From DESIGN.md Tool 1"""
    sources: List[str] = Field(
        default=["sr-pm", "mdt", "netflow"],
        description="Telemetry sources to collect from",
    )
    window_minutes: int = Field(default=5, description="Collection window in minutes")


class CollectTelemetryOutput(BaseModel):
    """Output from telemetry collection"""
    telemetry: TelemetryData
    collection_time_ms: int
