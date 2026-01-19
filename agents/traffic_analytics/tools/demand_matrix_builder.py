"""Demand Matrix Builder - From DESIGN.md DemandMatrixBuilder"""
from typing import Optional
from collections import defaultdict
from datetime import datetime
import structlog

from ..schemas.telemetry import TelemetryData
from ..schemas.analytics import DemandMatrix

logger = structlog.get_logger(__name__)


class DemandMatrixBuilder:
    """
    Build PE-to-PE traffic demand matrix.
    From DESIGN.md: Works with SRv6, SR-MPLS, and RSVP-TE.
    """

    def __init__(self):
        # PE locator mapping for SRv6
        self._locator_to_pe: dict[str, str] = {}
        # IP to PE mapping
        self._ip_to_pe: dict[str, str] = {}

    def build_matrix(self, telemetry: TelemetryData) -> DemandMatrix:
        """
        Aggregate telemetry into PE-to-PE demand matrix.
        From DESIGN.md: Matrix[src_pe][dst_pe] = total_traffic_gbps
        """
        logger.info(
            "Building demand matrix",
            sr_pm_count=telemetry.sr_pm_count,
            mdt_count=telemetry.mdt_count,
            netflow_count=telemetry.netflow_count,
        )

        matrix = defaultdict(lambda: defaultdict(float))

        # SRv6: Use SRv6 locator counters (best visibility)
        for metric in telemetry.sr_pm:
            if metric.srv6_locator and metric.source_locator and metric.dest_locator:
                src_pe = self.locator_to_pe(metric.source_locator)
                dst_pe = self.locator_to_pe(metric.dest_locator)
                if src_pe and dst_pe:
                    matrix[src_pe][dst_pe] += metric.traffic_gbps

            # SR-MPLS: Use policy/BSID counters
            elif metric.sr_policy_bsid:
                src_pe = metric.headend
                dst_pe = metric.endpoint
                matrix[src_pe][dst_pe] += metric.traffic_gbps

            # Generic path metrics
            elif metric.headend and metric.endpoint:
                matrix[metric.headend][metric.endpoint] += metric.traffic_gbps

        # NetFlow: Aggregate by source/dest PE
        for flow in telemetry.netflow:
            if flow.src_pe and flow.dst_pe:
                # Convert bytes over 5-minute window to Gbps
                gbps = flow.bytes / 1e9 / 300
                matrix[flow.src_pe][flow.dst_pe] += gbps
            elif flow.src_ip and flow.dst_ip:
                src_pe = self.ip_to_pe(flow.src_ip)
                dst_pe = self.ip_to_pe(flow.dst_ip)
                if src_pe and dst_pe and src_pe != dst_pe:
                    gbps = flow.bytes / 1e9 / 300
                    matrix[src_pe][dst_pe] += gbps

        # Convert defaultdict to regular dict
        demand_matrix = DemandMatrix(
            matrix={src: dict(dests) for src, dests in matrix.items()},
            timestamp=datetime.now(),
        )

        logger.info(
            "Demand matrix built",
            pe_count=demand_matrix.get_pe_count(),
            total_demand_gbps=demand_matrix.get_total_demand(),
        )

        return demand_matrix

    def locator_to_pe(self, locator: str) -> Optional[str]:
        """
        Map SRv6 locator to PE name.
        From DESIGN.md: self.locator_to_pe(metric.source_locator)
        """
        if locator in self._locator_to_pe:
            return self._locator_to_pe[locator]

        # Try to extract PE from locator format fc00:<pe>::
        # Example: fc00:pe1::1 -> PE1
        if locator.startswith("fc00:"):
            parts = locator.split(":")
            if len(parts) >= 2:
                pe_part = parts[1].upper()
                if pe_part:
                    self._locator_to_pe[locator] = pe_part
                    return pe_part

        return None

    def ip_to_pe(self, ip: str) -> Optional[str]:
        """
        Map IP address to PE name.
        Uses simple heuristic based on IP range.
        """
        if ip in self._ip_to_pe:
            return self._ip_to_pe[ip]

        # Simple mapping: 10.X.Y.Z -> PE(X % 4 + 1)
        try:
            parts = ip.split(".")
            if len(parts) == 4:
                pe_num = (int(parts[1]) % 4) + 1
                pe_name = f"PE{pe_num}"
                self._ip_to_pe[ip] = pe_name
                return pe_name
        except ValueError:
            pass

        return None

    def register_locator_mapping(self, locator: str, pe: str):
        """Register a locator to PE mapping"""
        self._locator_to_pe[locator] = pe

    def register_ip_mapping(self, ip: str, pe: str):
        """Register an IP to PE mapping"""
        self._ip_to_pe[ip] = pe


# Singleton instance
_matrix_builder: Optional[DemandMatrixBuilder] = None


def get_demand_matrix_builder() -> DemandMatrixBuilder:
    """Get or create demand matrix builder singleton"""
    global _matrix_builder
    if _matrix_builder is None:
        _matrix_builder = DemandMatrixBuilder()
    return _matrix_builder
