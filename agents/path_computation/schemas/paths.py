"""
Path Schemas

Pydantic models for path computation.
From DESIGN.md Path Computation Agent.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class PathConstraints(BaseModel):
    """
    Constraints for path computation.

    From DESIGN.md PathConstraints schema.
    """

    # Avoidance constraints
    avoid_links: List[str] = Field(default_factory=list, description="Link IDs to avoid")
    avoid_nodes: List[str] = Field(default_factory=list, description="Node IDs to avoid")
    avoid_srlgs: List[str] = Field(default_factory=list, description="SRLG IDs to avoid")

    # Optimization objective
    optimization_metric: Literal["igp", "te", "delay", "hop_count"] = Field(
        default="delay",
        description="Metric to optimize"
    )

    # Affinity constraints (from CNC)
    include_affinities: int = Field(default=0, description="Include affinity bitmask")
    exclude_affinities: int = Field(default=0, description="Exclude affinity bitmask")

    # Limits
    max_hops: int = Field(default=10, description="Maximum hop count")
    max_delay_ms: Optional[float] = Field(None, description="Maximum end-to-end delay")
    min_bandwidth_gbps: Optional[float] = Field(None, description="Minimum available bandwidth")

    # Disjointness
    disjoint_from_path: Optional[List[str]] = Field(None, description="Path to be disjoint from")
    disjointness_type: Optional[Literal["node", "link", "srlg"]] = Field(
        None,
        description="Type of disjointness"
    )


class ComputedPath(BaseModel):
    """
    Computed path from Knowledge Graph.

    From DESIGN.md ComputedPath schema.
    """

    path_id: str
    source: str
    destination: str

    # Path details
    segments: List[str] = Field(default_factory=list, description="Ordered list of node/link IDs")
    segment_sids: List[int] = Field(default_factory=list, description="Corresponding SIDs for SR")
    total_hops: int = 0

    # Metrics
    total_delay_ms: float = 0.0
    total_igp_metric: int = 0
    total_te_metric: int = 0
    min_available_bandwidth_gbps: float = 0.0

    # TE type recommendation
    recommended_te_type: Literal["sr-mpls", "srv6", "rsvp-te"] = "sr-mpls"

    # Relaxation info (if constraints were relaxed)
    constraints_relaxed: bool = False
    relaxation_level: int = 0


class PathValidationResult(BaseModel):
    """Result of path validation against SLA requirements."""

    is_valid: bool
    path_id: str
    violations: List[str] = Field(default_factory=list)

    # Metrics comparison
    delay_ok: bool = True
    bandwidth_ok: bool = True
    hop_count_ok: bool = True

    # Actual vs required
    actual_delay_ms: Optional[float] = None
    required_delay_ms: Optional[float] = None
    actual_bandwidth_gbps: Optional[float] = None
    required_bandwidth_gbps: Optional[float] = None
