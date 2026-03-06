"""
CNC Topology API Client

Client for querying CNC live IGP topology — real-time network state,
not cached Knowledge Graph data. Used to walk P-to-P hop paths between
PEs and to retrieve link metrics.

From Krishnan Thirukonda (CNC product team):
- Live real-time IGP topology from CNC (not cached KG data)
- P-to-P hop path between two PEs (to find which P-to-P link is degraded)
- Link neighbors with IGP metrics
"""

import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone

import structlog
import httpx

logger = structlog.get_logger(__name__)


class CNCTopologyClient:
    """
    Client for CNC Topology API.

    Provides live real-time IGP topology data from CNC:
    - IGP path (hop-by-hop) between two PE nodes
    - Link metrics (IGP metric, TE metric, bandwidth)
    - Neighbor links per node
    """

    def __init__(self):
        self.base_url = os.getenv(
            "CNC_TOPOLOGY_URL",
            "https://cnc.example.com:30603/crosswork/nbi/topology/v1",
        )
        self.auth_url = os.getenv(
            "CNC_AUTH_URL",
            "https://cnc.example.com:30603/crosswork/sso/v1/tickets",
        )
        self.jwt_url = os.getenv(
            "CNC_JWT_URL",
            "https://cnc.example.com:30603/crosswork/sso/v2/tickets/jwt",
        )
        self.username: str = os.getenv("CNC_USERNAME", "admin")
        self.password: str = os.getenv("CNC_PASSWORD", "")
        self.timeout: int = 30

        # JWT token caching (same pattern as CNCServiceHealthClient)
        self._jwt_token: Optional[str] = None
        self._jwt_expires_at: Optional[datetime] = None
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            ca_cert = os.getenv("CA_CERT_PATH")
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                verify=ca_cert if ca_cert else True,
            )
        return self._client

    async def _get_jwt_token(self) -> str:
        """
        Get JWT token via TGT exchange.

        Same pattern as CNCServiceHealthClient in agents/service_impact/tools/cnc_client.py.
        Token is cached for 8 hours with a 5-minute safety margin on renewal.
        """
        # Check if token is still valid (with 5-minute safety margin)
        if self._jwt_token and self._jwt_expires_at:
            if datetime.now(timezone.utc) < self._jwt_expires_at - timedelta(minutes=5):
                return self._jwt_token

        client = await self._get_client()

        # Step 1: Get TGT
        logger.debug("Getting TGT from CNC SSO")
        tgt_response = await client.post(
            self.auth_url,
            data={
                "username": self.username,
                "password": self.password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        tgt_response.raise_for_status()
        tgt = tgt_response.text.strip()

        # Step 2: Exchange TGT for JWT
        logger.debug("Exchanging TGT for JWT")
        jwt_response = await client.post(
            self.jwt_url,
            data={
                "tgt": tgt,
                "service": f"{self.base_url}/app-dashboard",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        jwt_response.raise_for_status()
        self._jwt_token = jwt_response.text.strip()
        self._jwt_expires_at = datetime.now(timezone.utc) + timedelta(hours=8)

        logger.info("JWT token obtained successfully")
        return self._jwt_token

    async def get_igp_path(self, pe_a: str, pe_b: str) -> List[dict]:
        """
        Get the IGP hop-by-hop path between two PE nodes.

        Calls GET {base_url}/topology/igp-path?source={pe_a}&destination={pe_b}

        Args:
            pe_a: Source PE node ID
            pe_b: Destination PE node ID

        Returns:
            List of hop dicts, e.g.:
            [
                {
                    "node": "P1",
                    "interface_in": "Gi0/0/0/1",
                    "interface_out": "Gi0/0/0/2",
                    "link_id": "link-P1-P2",
                },
                ...
            ]
            Returns [] on 404 (no path found) or any error.
        """
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            logger.info(
                "Fetching IGP path from CNC Topology API",
                pe_source=pe_a,
                pe_destination=pe_b,
            )

            response = await client.get(
                f"{self.base_url}/topology/igp-path",
                params={"source": pe_a, "destination": pe_b},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )

            if response.status_code == 404:
                logger.warning(
                    "CNC Topology API returned 404 — no IGP path found",
                    pe_source=pe_a,
                    pe_destination=pe_b,
                )
                return []

            response.raise_for_status()
            data = response.json()
            hops: List[dict] = data.get("hops", [])

            logger.info(
                "IGP path fetched",
                pe_source=pe_a,
                pe_destination=pe_b,
                hop_count=len(hops),
            )
            return hops

        except Exception as e:
            logger.error(
                "Failed to fetch IGP path from CNC Topology API",
                pe_source=pe_a,
                pe_destination=pe_b,
                error=str(e),
            )
            return []

    async def get_link_metrics(self, link_id: str) -> Dict[str, Any]:
        """
        Get IGP/TE metrics and bandwidth for a specific link.

        Calls GET {base_url}/topology/links/{link_id}/metrics

        Args:
            link_id: Topology link ID

        Returns:
            Dict with link metrics, e.g.:
            {
                "link_id": "link-P1-P2",
                "igp_metric": 10,
                "te_metric": 10,
                "bandwidth_gbps": 100.0,
                "available_bandwidth_gbps": 87.5,
            }
            Returns {} on error.
        """
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            logger.info("Fetching link metrics from CNC Topology API", link_id=link_id)

            response = await client.get(
                f"{self.base_url}/topology/links/{link_id}/metrics",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            data: Dict[str, Any] = response.json()

            logger.info(
                "Link metrics fetched",
                link_id=link_id,
                igp_metric=data.get("igp_metric"),
                available_bandwidth_gbps=data.get("available_bandwidth_gbps"),
            )
            return data

        except Exception as e:
            logger.error(
                "Failed to fetch link metrics from CNC Topology API",
                link_id=link_id,
                error=str(e),
            )
            return {}

    async def get_node_links(self, node_id: str) -> List[dict]:
        """
        Get all adjacent links (with IGP metrics) for a given node.

        Calls GET {base_url}/topology/nodes/{node_id}/links

        Args:
            node_id: Node ID (e.g. router hostname or loopback IP)

        Returns:
            List of adjacent link dicts with metrics.
            Returns [] on error.
        """
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            logger.info(
                "Fetching node links from CNC Topology API", node_id=node_id
            )

            response = await client.get(
                f"{self.base_url}/topology/nodes/{node_id}/links",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            data = response.json()
            links: List[dict] = data.get("links", [])

            logger.info(
                "Node links fetched",
                node_id=node_id,
                link_count=len(links),
            )
            return links

        except Exception as e:
            logger.error(
                "Failed to fetch node links from CNC Topology API",
                node_id=node_id,
                error=str(e),
            )
            return []

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Module-level singleton
_cnc_topology_client: Optional[CNCTopologyClient] = None


def get_cnc_topology_client() -> CNCTopologyClient:
    """Get singleton CNCTopologyClient instance."""
    global _cnc_topology_client
    if _cnc_topology_client is None:
        _cnc_topology_client = CNCTopologyClient()
    return _cnc_topology_client
