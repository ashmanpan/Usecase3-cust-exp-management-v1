"""Congestion Predictor - From DESIGN.md CongestionPredictor"""
import os
from typing import Optional, List, Dict, Tuple
import random
import httpx
import structlog

from ..schemas.analytics import DemandMatrix, CongestionRisk

logger = structlog.get_logger(__name__)


class CongestionPredictor:
    """
    Predict congestion based on demand matrix and link capacities.
    From DESIGN.md CongestionPredictor
    """

    # Thresholds - From DESIGN.md
    UTILIZATION_THRESHOLD = 0.70  # 70% = warning
    CRITICAL_THRESHOLD = 0.85     # 85% = proactive alert

    def __init__(
        self,
        kg_base_url: Optional[str] = None,
        utilization_threshold: float = 0.70,
        critical_threshold: float = 0.85,
    ):
        self.kg_base_url = kg_base_url or os.getenv("KG_API_URL", "http://kg-api:8080")
        self.UTILIZATION_THRESHOLD = utilization_threshold
        self.CRITICAL_THRESHOLD = critical_threshold
        self._client: Optional[httpx.AsyncClient] = None
        # Cached topology (link capacities, paths)
        self._topology: Optional[dict] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    async def predict(
        self,
        demand_matrix: DemandMatrix,
    ) -> List[CongestionRisk]:
        """
        Analyze each link for congestion risk.
        From DESIGN.md CongestionPredictor.predict()
        """
        logger.info("Predicting congestion from demand matrix")

        # Get network topology (links with capacities)
        topology = await self._get_topology()
        risks = []

        for link in topology.get("links", []):
            link_id = link["link_id"]
            capacity_gbps = link.get("capacity_gbps", 10.0)
            endpoints = link.get("endpoints", ("", ""))

            # Get current utilization
            current_traffic = link.get("current_traffic_gbps", 0.0)
            current_util = current_traffic / capacity_gbps if capacity_gbps > 0 else 0

            # Get projected demand through this link
            projected_demand = self._get_demand_through_link(
                link_id, endpoints, demand_matrix, topology
            )
            projected_util = projected_demand / capacity_gbps if capacity_gbps > 0 else 0

            # Assess risk level - From DESIGN.md
            if projected_util >= self.CRITICAL_THRESHOLD:
                risk_level = "high"
            elif projected_util >= self.UTILIZATION_THRESHOLD:
                risk_level = "medium"
            else:
                risk_level = "low"

            # Only include medium and high risk links
            if risk_level != "low":
                affected_pairs = self._get_affected_pairs(link_id, demand_matrix, topology)

                risks.append(CongestionRisk(
                    link_id=link_id,
                    link_endpoints=tuple(endpoints) if len(endpoints) == 2 else ("", ""),
                    current_utilization=current_util,
                    projected_utilization=projected_util,
                    capacity_gbps=capacity_gbps,
                    current_traffic_gbps=current_traffic,
                    projected_traffic_gbps=projected_demand,
                    risk_level=risk_level,
                    affected_pe_pairs=affected_pairs,
                ))

                logger.info(
                    "Congestion risk detected",
                    link_id=link_id,
                    risk_level=risk_level,
                    projected_utilization=f"{projected_util:.1%}",
                )

        # Sort by projected utilization (highest first) - From DESIGN.md
        risks = sorted(risks, key=lambda r: r.projected_utilization, reverse=True)

        logger.info(
            "Congestion prediction complete",
            total_risks=len(risks),
            high_risk=sum(1 for r in risks if r.risk_level == "high"),
            medium_risk=sum(1 for r in risks if r.risk_level == "medium"),
        )

        return risks

    async def _get_topology(self) -> dict:
        """Get network topology from Knowledge Graph"""
        if self._topology:
            return self._topology

        try:
            client = await self._get_client()
            response = await client.get(f"{self.kg_base_url}/api/v1/topology/links")
            response.raise_for_status()
            self._topology = response.json()
            return self._topology

        except httpx.HTTPError as e:
            logger.warning("KG API unavailable, using simulated topology", error=str(e))
            return self._simulate_topology()

    def _simulate_topology(self) -> dict:
        """Simulate network topology for demo"""
        links = [
            {"link_id": "link-PE1-PE2", "endpoints": ["PE1", "PE2"], "capacity_gbps": 10.0, "current_traffic_gbps": random.uniform(5, 8)},
            {"link_id": "link-PE1-PE3", "endpoints": ["PE1", "PE3"], "capacity_gbps": 10.0, "current_traffic_gbps": random.uniform(3, 6)},
            {"link_id": "link-PE2-PE3", "endpoints": ["PE2", "PE3"], "capacity_gbps": 10.0, "current_traffic_gbps": random.uniform(4, 7)},
            {"link_id": "link-PE2-PE4", "endpoints": ["PE2", "PE4"], "capacity_gbps": 10.0, "current_traffic_gbps": random.uniform(6, 9)},
            {"link_id": "link-PE3-PE4", "endpoints": ["PE3", "PE4"], "capacity_gbps": 10.0, "current_traffic_gbps": random.uniform(2, 5)},
            {"link_id": "link-PE1-PE4", "endpoints": ["PE1", "PE4"], "capacity_gbps": 10.0, "current_traffic_gbps": random.uniform(3, 6)},
        ]

        # Pre-computed paths through links
        paths = {
            ("PE1", "PE2"): ["link-PE1-PE2"],
            ("PE1", "PE3"): ["link-PE1-PE3"],
            ("PE1", "PE4"): ["link-PE1-PE4"],
            ("PE2", "PE3"): ["link-PE2-PE3"],
            ("PE2", "PE4"): ["link-PE2-PE4"],
            ("PE3", "PE4"): ["link-PE3-PE4"],
            ("PE2", "PE1"): ["link-PE1-PE2"],
            ("PE3", "PE1"): ["link-PE1-PE3"],
            ("PE4", "PE1"): ["link-PE1-PE4"],
            ("PE3", "PE2"): ["link-PE2-PE3"],
            ("PE4", "PE2"): ["link-PE2-PE4"],
            ("PE4", "PE3"): ["link-PE3-PE4"],
        }

        return {"links": links, "paths": paths}

    def _get_demand_through_link(
        self,
        link_id: str,
        endpoints: List[str],
        demand_matrix: DemandMatrix,
        topology: dict,
    ) -> float:
        """
        Calculate total demand flowing through a specific link.
        From DESIGN.md DemandMatrix.get_total_demand_through_link()
        """
        total = 0.0
        paths = topology.get("paths", {})

        for src_pe, destinations in demand_matrix.matrix.items():
            for dst_pe, demand in destinations.items():
                # Get path from topology
                path_key = (src_pe, dst_pe)
                path_links = paths.get(path_key, [])

                if link_id in path_links:
                    total += demand

        return total

    def _get_affected_pairs(
        self,
        link_id: str,
        demand_matrix: DemandMatrix,
        topology: dict,
    ) -> List[Tuple[str, str]]:
        """Get PE pairs affected by congestion on a link"""
        affected = []
        paths = topology.get("paths", {})

        for src_pe, destinations in demand_matrix.matrix.items():
            for dst_pe, demand in destinations.items():
                if demand > 0:
                    path_key = (src_pe, dst_pe)
                    path_links = paths.get(path_key, [])
                    if link_id in path_links:
                        affected.append((src_pe, dst_pe))

        return affected

    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
_congestion_predictor: Optional[CongestionPredictor] = None


def get_congestion_predictor(
    utilization_threshold: float = 0.70,
    critical_threshold: float = 0.85,
) -> CongestionPredictor:
    """Get or create congestion predictor singleton"""
    global _congestion_predictor
    if _congestion_predictor is None:
        _congestion_predictor = CongestionPredictor(
            utilization_threshold=utilization_threshold,
            critical_threshold=critical_threshold,
        )
    return _congestion_predictor
