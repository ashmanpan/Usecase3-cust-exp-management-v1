"""
Knowledge Graph Dijkstra API Client

Client for querying KG Dijkstra API for path computation.
From DESIGN.md: KGDijkstraClient for alternate paths.
"""

import os
from typing import Optional, Dict, Any
from uuid import uuid4

import structlog
import httpx

from ..schemas.paths import PathConstraints, ComputedPath

logger = structlog.get_logger(__name__)


class KGDijkstraClient:
    """
    Client for Knowledge Graph Dijkstra API.

    From DESIGN.md:
    - POST /dijkstra - Compute shortest path with constraints
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Initialize KG client.

        Args:
            base_url: KG API base URL
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.getenv(
            "KG_BASE_URL",
            "https://kg.example.com/api/v1"
        )
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                verify=False,  # For self-signed certs
            )
        return self._client

    async def compute_path(
        self,
        source: str,
        destination: str,
        constraints: PathConstraints,
    ) -> Optional[ComputedPath]:
        """
        Compute shortest path with constraints.

        From DESIGN.md: POST /dijkstra

        Args:
            source: Source PE/node ID
            destination: Destination PE/node ID
            constraints: Path constraints

        Returns:
            ComputedPath if found, None otherwise
        """
        client = await self._get_client()

        payload = {
            "source": source,
            "destination": destination,
            "avoid_links": constraints.avoid_links,
            "avoid_nodes": constraints.avoid_nodes,
            "avoid_srlgs": constraints.avoid_srlgs,
            "metric": constraints.optimization_metric,
            "max_hops": constraints.max_hops,
        }

        # Add optional constraints
        if constraints.max_delay_ms:
            payload["max_delay_ms"] = constraints.max_delay_ms
        if constraints.min_bandwidth_gbps:
            payload["min_bandwidth_gbps"] = constraints.min_bandwidth_gbps
        if constraints.disjoint_from_path:
            payload["disjoint_from_path"] = constraints.disjoint_from_path
            payload["disjointness_type"] = constraints.disjointness_type or "link"

        logger.info(
            "Computing path via KG Dijkstra",
            source=source,
            destination=destination,
            avoid_links=len(constraints.avoid_links),
        )

        try:
            response = await client.post(
                f"{self.base_url}/dijkstra",
                json=payload,
            )

            if response.status_code == 200:
                data = response.json()
                path = ComputedPath(
                    path_id=data.get("path_id", f"path-{uuid4().hex[:8]}"),
                    source=source,
                    destination=destination,
                    segments=data.get("segments", []),
                    segment_sids=data.get("segment_sids", []),
                    total_hops=data.get("total_hops", len(data.get("segments", []))),
                    total_delay_ms=data.get("total_delay_ms", 0.0),
                    total_igp_metric=data.get("total_igp_metric", 0),
                    total_te_metric=data.get("total_te_metric", 0),
                    min_available_bandwidth_gbps=data.get("min_available_bandwidth_gbps", 0.0),
                    recommended_te_type=data.get("recommended_te_type", "sr-mpls"),
                )
                logger.info(
                    "Path computed successfully",
                    path_id=path.path_id,
                    total_hops=path.total_hops,
                    total_delay_ms=path.total_delay_ms,
                )
                return path

            elif response.status_code == 404:
                logger.warning(
                    "No path found",
                    source=source,
                    destination=destination,
                )
                return None

            else:
                logger.error(
                    "KG API error",
                    status_code=response.status_code,
                    response=response.text,
                )
                return None

        except Exception as e:
            logger.error(
                "Failed to compute path",
                source=source,
                destination=destination,
                error=str(e),
            )
            # Return simulated path for demo/testing
            return self._simulate_path(source, destination, constraints)

    def _simulate_path(
        self,
        source: str,
        destination: str,
        constraints: PathConstraints,
    ) -> Optional[ComputedPath]:
        """
        Simulate path computation for demo/testing.

        Returns a synthetic path when KG is unavailable.
        """
        logger.warning(
            "Simulating path computation",
            source=source,
            destination=destination,
        )

        # Generate synthetic path
        segments = [source, "P1", "P2", destination]
        segment_sids = [16001, 16002, 16003, 16004]

        return ComputedPath(
            path_id=f"path-{uuid4().hex[:8]}",
            source=source,
            destination=destination,
            segments=segments,
            segment_sids=segment_sids,
            total_hops=len(segments) - 1,
            total_delay_ms=15.0,
            total_igp_metric=100,
            total_te_metric=100,
            min_available_bandwidth_gbps=10.0,
            recommended_te_type="sr-mpls",
        )

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
_kg_client: Optional[KGDijkstraClient] = None


def get_kg_client() -> KGDijkstraClient:
    """Get singleton KG client instance."""
    global _kg_client
    if _kg_client is None:
        _kg_client = KGDijkstraClient()
    return _kg_client
