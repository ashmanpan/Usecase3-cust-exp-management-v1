"""
Path Validator

Validates computed paths against SLA requirements.
From DESIGN.md: Check path meets SLA requirements (delay, BW).
"""

import os
from typing import List, Dict, Any, Optional

import structlog

from ..schemas.paths import ComputedPath, PathValidationResult

logger = structlog.get_logger(__name__)


class PathValidator:
    """
    Validates computed paths against SLA requirements.

    From DESIGN.md:
    - Check delay constraints
    - Check bandwidth constraints
    - Check hop count constraints
    """

    # Default validation thresholds
    DEFAULT_MAX_DELAY_MULTIPLIER = 2.0  # Allow up to 2x original delay
    DEFAULT_MIN_BANDWIDTH_FACTOR = 0.8  # Require at least 80% of requested BW

    def __init__(
        self,
        max_delay_multiplier: float = None,
        min_bandwidth_factor: float = None,
    ):
        """
        Initialize path validator.

        Args:
            max_delay_multiplier: Allowed delay multiplier vs SLA
            min_bandwidth_factor: Required bandwidth as factor of requested
        """
        self.max_delay_multiplier = max_delay_multiplier or self.DEFAULT_MAX_DELAY_MULTIPLIER
        self.min_bandwidth_factor = min_bandwidth_factor or self.DEFAULT_MIN_BANDWIDTH_FACTOR

    def validate_path(
        self,
        path: ComputedPath,
        required_sla: Dict[str, Any] = None,
        max_hops: int = None,
    ) -> PathValidationResult:
        """
        Validate a computed path against SLA requirements.

        Args:
            path: Computed path to validate
            required_sla: SLA requirements {max_delay_ms, min_bandwidth_gbps}
            max_hops: Maximum allowed hops

        Returns:
            PathValidationResult
        """
        required_sla = required_sla or {}
        violations = []

        # Check delay
        required_delay = required_sla.get("max_delay_ms")
        delay_ok = True
        if required_delay and path.total_delay_ms > 0:
            allowed_delay = required_delay * self.max_delay_multiplier
            if path.total_delay_ms > allowed_delay:
                delay_ok = False
                violations.append(
                    f"Delay {path.total_delay_ms}ms exceeds allowed {allowed_delay}ms"
                )

        # Check bandwidth
        required_bw = required_sla.get("min_bandwidth_gbps")
        bandwidth_ok = True
        if required_bw and path.min_available_bandwidth_gbps > 0:
            min_required = required_bw * self.min_bandwidth_factor
            if path.min_available_bandwidth_gbps < min_required:
                bandwidth_ok = False
                violations.append(
                    f"Bandwidth {path.min_available_bandwidth_gbps}Gbps below required {min_required}Gbps"
                )

        # Check hop count
        hop_count_ok = True
        if max_hops and path.total_hops > max_hops:
            hop_count_ok = False
            violations.append(
                f"Hop count {path.total_hops} exceeds max {max_hops}"
            )

        is_valid = delay_ok and bandwidth_ok and hop_count_ok

        result = PathValidationResult(
            is_valid=is_valid,
            path_id=path.path_id,
            violations=violations,
            delay_ok=delay_ok,
            bandwidth_ok=bandwidth_ok,
            hop_count_ok=hop_count_ok,
            actual_delay_ms=path.total_delay_ms,
            required_delay_ms=required_delay,
            actual_bandwidth_gbps=path.min_available_bandwidth_gbps,
            required_bandwidth_gbps=required_bw,
        )

        logger.info(
            "Path validation complete",
            path_id=path.path_id,
            is_valid=is_valid,
            violation_count=len(violations),
        )

        return result

    def select_best_path(
        self,
        paths: List[ComputedPath],
        required_sla: Dict[str, Any] = None,
        optimization: str = "delay",
    ) -> Optional[ComputedPath]:
        """
        Select best path from multiple candidates.

        Args:
            paths: List of candidate paths
            required_sla: SLA requirements for filtering
            optimization: What to optimize (delay, hops, bandwidth)

        Returns:
            Best path or None if none valid
        """
        if not paths:
            return None

        # Filter valid paths
        valid_paths = []
        for path in paths:
            result = self.validate_path(path, required_sla)
            if result.is_valid:
                valid_paths.append(path)

        if not valid_paths:
            logger.warning("No valid paths found")
            # Return best invalid path for escalation
            if optimization == "delay":
                return min(paths, key=lambda p: p.total_delay_ms)
            elif optimization == "hops":
                return min(paths, key=lambda p: p.total_hops)
            else:
                return paths[0]

        # Sort by optimization criteria
        if optimization == "delay":
            valid_paths.sort(key=lambda p: p.total_delay_ms)
        elif optimization == "hops":
            valid_paths.sort(key=lambda p: p.total_hops)
        elif optimization == "bandwidth":
            valid_paths.sort(key=lambda p: -p.min_available_bandwidth_gbps)

        best = valid_paths[0]
        logger.info(
            "Best path selected",
            path_id=best.path_id,
            optimization=optimization,
            delay_ms=best.total_delay_ms,
            hops=best.total_hops,
        )

        return best


# Singleton instance
_path_validator: Optional[PathValidator] = None


def get_path_validator() -> PathValidator:
    """Get singleton path validator instance."""
    global _path_validator
    if _path_validator is None:
        _path_validator = PathValidator()
    return _path_validator
