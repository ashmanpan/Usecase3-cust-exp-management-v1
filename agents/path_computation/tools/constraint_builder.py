"""
Constraint Builder

Builds and relaxes path computation constraints.
From DESIGN.md: Constraint building and relaxation strategy.
"""

import os
from typing import List, Dict, Any, Optional

import structlog

from ..schemas.paths import PathConstraints

logger = structlog.get_logger(__name__)


# Relaxation order from DESIGN.md
RELAXATION_ORDER = [
    "avoid_srlgs",         # First, allow same SRLG
    "max_hops",            # Then, allow more hops (increase by 5)
    "optimization_metric", # Then, switch from delay to igp
    "avoid_nodes",         # Last resort: allow same transit nodes
    # Never relax: avoid_links (the degraded links)
]


class ConstraintBuilder:
    """
    Builds and relaxes path computation constraints.

    From DESIGN.md:
    - Build avoidance constraints from degraded links
    - Progressive relaxation to find a path
    """

    # Default constraint values
    DEFAULT_MAX_HOPS = 10
    DEFAULT_METRIC = "delay"
    HOP_INCREASE_PER_LEVEL = 5
    MAX_RELAXATION_LEVELS = 4

    def __init__(
        self,
        default_max_hops: int = None,
        default_metric: str = None,
        hop_increase: int = None,
        max_relaxation_levels: int = None,
    ):
        """
        Initialize constraint builder.

        Args:
            default_max_hops: Default maximum hops
            default_metric: Default optimization metric
            hop_increase: Hops to add per relaxation level
            max_relaxation_levels: Maximum relaxation levels
        """
        self.default_max_hops = default_max_hops or self.DEFAULT_MAX_HOPS
        self.default_metric = default_metric or self.DEFAULT_METRIC
        self.hop_increase = hop_increase or self.HOP_INCREASE_PER_LEVEL
        self.max_relaxation_levels = max_relaxation_levels or self.MAX_RELAXATION_LEVELS

    def build_constraints(
        self,
        degraded_links: List[str],
        avoid_nodes: List[str] = None,
        avoid_srlgs: List[str] = None,
        existing_policies: List[str] = None,
        required_sla: Dict[str, Any] = None,
        te_type: str = None,
    ) -> PathConstraints:
        """
        Build initial path constraints.

        Args:
            degraded_links: Links to avoid (required)
            avoid_nodes: Additional nodes to avoid
            avoid_srlgs: SRLGs to avoid
            existing_policies: Existing policies for disjointness
            required_sla: SLA requirements {max_delay_ms, min_bandwidth_gbps}
            te_type: Current TE type for metric selection

        Returns:
            PathConstraints object
        """
        # Determine optimization metric based on TE type
        metric = self.default_metric
        if te_type == "rsvp-te":
            metric = "te"  # Use TE metric for RSVP-TE
        elif required_sla and required_sla.get("max_delay_ms"):
            metric = "delay"  # Use delay if SLA specifies delay constraint

        constraints = PathConstraints(
            avoid_links=degraded_links or [],
            avoid_nodes=avoid_nodes or [],
            avoid_srlgs=avoid_srlgs or [],
            optimization_metric=metric,
            max_hops=self.default_max_hops,
            max_delay_ms=required_sla.get("max_delay_ms") if required_sla else None,
            min_bandwidth_gbps=required_sla.get("min_bandwidth_gbps") if required_sla else None,
            disjoint_from_path=existing_policies[0] if existing_policies else None,
            disjointness_type="link" if existing_policies else None,
        )

        logger.info(
            "Constraints built",
            avoid_links=len(constraints.avoid_links),
            avoid_nodes=len(constraints.avoid_nodes),
            metric=constraints.optimization_metric,
            max_hops=constraints.max_hops,
        )

        return constraints

    def relax_constraints(
        self,
        constraints: PathConstraints,
        level: int,
    ) -> PathConstraints:
        """
        Progressively relax constraints to find a path.

        From DESIGN.md relaxation strategy.

        Args:
            constraints: Current constraints
            level: Relaxation level (1-4)

        Returns:
            Relaxed constraints
        """
        if level > self.max_relaxation_levels:
            logger.warning(
                "Max relaxation level exceeded",
                level=level,
                max_level=self.max_relaxation_levels,
            )
            return constraints

        # Create copy
        relaxed = PathConstraints(
            avoid_links=constraints.avoid_links.copy(),  # Never relax
            avoid_nodes=constraints.avoid_nodes.copy(),
            avoid_srlgs=constraints.avoid_srlgs.copy(),
            optimization_metric=constraints.optimization_metric,
            max_hops=constraints.max_hops,
            max_delay_ms=constraints.max_delay_ms,
            min_bandwidth_gbps=constraints.min_bandwidth_gbps,
            disjoint_from_path=constraints.disjoint_from_path,
            disjointness_type=constraints.disjointness_type,
        )

        # Apply relaxations based on level
        if level >= 1:
            # Level 1: Allow same SRLG
            relaxed.avoid_srlgs = []
            logger.debug("Relaxed: removed SRLG avoidance")

        if level >= 2:
            # Level 2: Allow more hops
            relaxed.max_hops = constraints.max_hops + self.hop_increase
            logger.debug("Relaxed: increased max_hops", new_max=relaxed.max_hops)

        if level >= 3:
            # Level 3: Switch metric from delay to IGP
            relaxed.optimization_metric = "igp"
            relaxed.max_delay_ms = None  # Remove delay constraint
            logger.debug("Relaxed: switched to IGP metric")

        if level >= 4:
            # Level 4: Allow same transit nodes
            relaxed.avoid_nodes = []
            logger.debug("Relaxed: removed node avoidance")

        logger.info(
            "Constraints relaxed",
            level=level,
            avoid_srlgs=len(relaxed.avoid_srlgs),
            max_hops=relaxed.max_hops,
            metric=relaxed.optimization_metric,
        )

        return relaxed

    def can_relax_further(self, level: int) -> bool:
        """Check if further relaxation is possible."""
        return level < self.max_relaxation_levels


# Singleton instance
_constraint_builder: Optional[ConstraintBuilder] = None


def get_constraint_builder() -> ConstraintBuilder:
    """Get singleton constraint builder instance."""
    global _constraint_builder
    if _constraint_builder is None:
        _constraint_builder = ConstraintBuilder()
    return _constraint_builder
