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
        self.coe_url = os.getenv(
            "CNC_COE_URL",
            "https://cnc.example.com:30603/crosswork/nbi/optimization/v3/restconf",
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

    # ------------------------------------------------------------------
    # Layer 3 & Layer 2 Topology (COE RESTCONF — coe_topology_l3_l2.json)
    # Base: GET {coe_url}/data/ietf-network-state:networks
    # Spec server: /crosswork/nbi/topology/v3/restconf
    # ------------------------------------------------------------------

    async def get_all_networks(
        self,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve all topology networks operational data.

        Calls GET {coe_url}/data/ietf-network-state:networks

        Serves as a top-level container for a list of networks. COE currently
        only supports the concept of a single network.

        Args:
            offset: Number of list elements to skip (pagination).
            limit: Maximum number of list entries to return (pagination).

        Returns:
            Dict with ``ietf-network-state:networks`` key containing a
            ``network`` list. Returns {} on error.
        """
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            params: Dict[str, Any] = {}
            if offset is not None:
                params["offset"] = offset
            if limit is not None:
                params["limit"] = limit

            logger.info("Fetching all networks from COE topology RESTCONF API")

            response = await client.get(
                f"{self.coe_url}/data/ietf-network-state:networks",
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/yang-data+json",
                },
            )

            if response.status_code == 404:
                logger.warning("COE topology API returned 404 for networks")
                return {}

            response.raise_for_status()
            data: Dict[str, Any] = response.json()

            networks = (
                data.get("ietf-network-state:networks", {})
                .get("network", [])
            )
            logger.info("Networks fetched", network_count=len(networks))
            return data

        except Exception as e:
            logger.error(
                "Failed to fetch networks from COE topology API",
                error=str(e),
            )
            return {}

    async def get_network(self, network_id: str) -> Dict[str, Any]:
        """
        Retrieve a single network topology by its network ID.

        Calls GET {coe_url}/data/ietf-network-state:networks/network={network_id}

        Args:
            network_id: Identifies the network (e.g. ``ISIS-L3-topology``).

        Returns:
            Dict with the network object. Returns {} on 404 or error.
        """
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            logger.info(
                "Fetching network from COE topology RESTCONF API",
                network_id=network_id,
            )

            response = await client.get(
                f"{self.coe_url}/data/ietf-network-state:networks/network={network_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/yang-data+json",
                },
            )

            if response.status_code == 404:
                logger.warning(
                    "COE topology API returned 404 for network",
                    network_id=network_id,
                )
                return {}

            response.raise_for_status()
            data: Dict[str, Any] = response.json()

            logger.info("Network fetched", network_id=network_id)
            return data

        except Exception as e:
            logger.error(
                "Failed to fetch network from COE topology API",
                network_id=network_id,
                error=str(e),
            )
            return {}

    async def get_network_node(
        self, network_id: str, node_id: str
    ) -> Dict[str, Any]:
        """
        Retrieve a single node within a network topology.

        Calls GET {coe_url}/data/ietf-network-state:networks/network={network_id}/node={node_id}

        Args:
            network_id: Identifies the network.
            node_id: Uniquely identifies a node within the network.

        Returns:
            Dict with the node object. Returns {} on 404 or error.
        """
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            logger.info(
                "Fetching network node from COE topology RESTCONF API",
                network_id=network_id,
                node_id=node_id,
            )

            response = await client.get(
                f"{self.coe_url}/data/ietf-network-state:networks"
                f"/network={network_id}/node={node_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/yang-data+json",
                },
            )

            if response.status_code == 404:
                logger.warning(
                    "COE topology API returned 404 for network node",
                    network_id=network_id,
                    node_id=node_id,
                )
                return {}

            response.raise_for_status()
            data: Dict[str, Any] = response.json()

            logger.info(
                "Network node fetched",
                network_id=network_id,
                node_id=node_id,
            )
            return data

        except Exception as e:
            logger.error(
                "Failed to fetch network node from COE topology API",
                network_id=network_id,
                node_id=node_id,
                error=str(e),
            )
            return {}

    async def get_network_topology_links(
        self,
        network_id: str,
        link_id: Optional[str] = None,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve topology links for a network.

        When ``link_id`` is provided, calls:
          GET {coe_url}/data/ietf-network-state:networks/network={network_id}/
              ietf-network-topology-state:link={link_id}

        Otherwise calls the parent network endpoint and returns the link list
        embedded in the network response.

        Args:
            network_id: Identifies the network.
            link_id: Optional specific link ID to retrieve.
            offset: Pagination offset (used when link_id is None).
            limit: Pagination limit (used when link_id is None).

        Returns:
            Dict with the link data. Returns {} on 404 or error.
        """
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            if link_id is not None:
                url = (
                    f"{self.coe_url}/data/ietf-network-state:networks"
                    f"/network={network_id}"
                    f"/ietf-network-topology-state:link={link_id}"
                )
                params: Dict[str, Any] = {}
                logger.info(
                    "Fetching specific topology link from COE RESTCONF API",
                    network_id=network_id,
                    link_id=link_id,
                )
            else:
                url = (
                    f"{self.coe_url}/data/ietf-network-state:networks"
                    f"/network={network_id}"
                )
                params = {}
                if offset is not None:
                    params["offset"] = offset
                if limit is not None:
                    params["limit"] = limit
                logger.info(
                    "Fetching topology links from COE RESTCONF API via network",
                    network_id=network_id,
                )

            response = await client.get(
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/yang-data+json",
                },
            )

            if response.status_code == 404:
                logger.warning(
                    "COE topology API returned 404 for network topology links",
                    network_id=network_id,
                    link_id=link_id,
                )
                return {}

            response.raise_for_status()
            data: Dict[str, Any] = response.json()

            logger.info(
                "Network topology links fetched",
                network_id=network_id,
                link_id=link_id,
            )
            return data

        except Exception as e:
            logger.error(
                "Failed to fetch network topology links from COE topology API",
                network_id=network_id,
                link_id=link_id,
                error=str(e),
            )
            return {}

    # ------------------------------------------------------------------
    # RSVP-TE LSP Details (COE RESTCONF — coe_rsvp_te_lsp_details.json)
    # Base: GET {coe_url}/data/cisco-crosswork-rsvp-te-tunnel:rsvp-te-tunnels
    # ------------------------------------------------------------------

    async def get_all_rsvp_tunnels(
        self,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve all RSVP-TE tunnel operational data.

        Calls GET {coe_url}/data/cisco-crosswork-rsvp-te-tunnel:rsvp-te-tunnels

        Args:
            offset: Number of list elements to skip (pagination).
            limit: Maximum number of list entries to return (pagination).

        Returns:
            Dict with ``cisco-crosswork-rsvp-te-tunnel:rsvp-te-tunnels`` key
            containing an ``rsvp-te-tunnel`` list. Returns {} on error.
        """
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            params: Dict[str, Any] = {}
            if offset is not None:
                params["offset"] = offset
            if limit is not None:
                params["limit"] = limit

            logger.info("Fetching all RSVP-TE tunnels from COE RESTCONF API")

            response = await client.get(
                f"{self.coe_url}/data/cisco-crosswork-rsvp-te-tunnel:rsvp-te-tunnels",
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/yang-data+json",
                },
            )

            if response.status_code == 404:
                logger.warning("COE RESTCONF API returned 404 for RSVP-TE tunnels")
                return {}

            response.raise_for_status()
            data: Dict[str, Any] = response.json()

            tunnels = (
                data.get("cisco-crosswork-rsvp-te-tunnel:rsvp-te-tunnels", {})
                .get("rsvp-te-tunnel", [])
            )
            logger.info("RSVP-TE tunnels fetched", tunnel_count=len(tunnels))
            return data

        except Exception as e:
            logger.error(
                "Failed to fetch RSVP-TE tunnels from COE RESTCONF API",
                error=str(e),
            )
            return {}

    async def get_rsvp_tunnel(
        self,
        headend: str,
        endpoint: str,
        tunnel_id: int,
    ) -> Dict[str, Any]:
        """
        Retrieve a single RSVP-TE tunnel by its composite key.

        Calls GET {coe_url}/data/cisco-crosswork-rsvp-te-tunnel:rsvp-te-tunnels/
            rsvp-te-tunnel={headend},{endpoint},{tunnel_id}

        The composite key is formed from three path parameters as defined in
        the COE RESTCONF spec (coe_rsvp_te_lsp_details.json):
          - rsvp-te-tunnel-headend: Head-end router IP address
          - rsvp-te-tunnel-endpoint: End-point IP address
          - rsvp-te-tunnel-tunnel-id: Tunnel ID (uint32)

        Args:
            headend: Head-end IP address of the RSVP-TE tunnel.
            endpoint: End-point IP address of the RSVP-TE tunnel.
            tunnel_id: Numeric tunnel ID associated with the TE tunnel.

        Returns:
            Dict with the tunnel object. Returns {} on 404 or error.
        """
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            logger.info(
                "Fetching RSVP-TE tunnel from COE RESTCONF API",
                headend=headend,
                endpoint=endpoint,
                tunnel_id=tunnel_id,
            )

            response = await client.get(
                f"{self.coe_url}/data/cisco-crosswork-rsvp-te-tunnel:rsvp-te-tunnels"
                f"/rsvp-te-tunnel={headend},{endpoint},{tunnel_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/yang-data+json",
                },
            )

            if response.status_code == 404:
                logger.warning(
                    "COE RESTCONF API returned 404 for RSVP-TE tunnel",
                    headend=headend,
                    endpoint=endpoint,
                    tunnel_id=tunnel_id,
                )
                return {}

            response.raise_for_status()
            data: Dict[str, Any] = response.json()

            logger.info(
                "RSVP-TE tunnel fetched",
                headend=headend,
                endpoint=endpoint,
                tunnel_id=tunnel_id,
            )
            return data

        except Exception as e:
            logger.error(
                "Failed to fetch RSVP-TE tunnel from COE RESTCONF API",
                headend=headend,
                endpoint=endpoint,
                tunnel_id=tunnel_id,
                error=str(e),
            )
            return {}

    # ------------------------------------------------------------------
    # SR Policy Details (COE RESTCONF — coe_sr_policy_details.json)
    # Base: GET {coe_url}/data/cisco-crosswork-segment-routing-policy:sr-policies
    # ------------------------------------------------------------------

    async def get_all_sr_policy_details(
        self,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve all SR policy operational data.

        Calls GET {coe_url}/data/cisco-crosswork-segment-routing-policy:sr-policies

        Args:
            offset: Number of list elements to skip (pagination).
            limit: Maximum number of list entries to return (pagination).

        Returns:
            Dict with ``cisco-crosswork-segment-routing-policy:sr-policies``
            key containing a ``policy`` list. Returns {} on error.
        """
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            params: Dict[str, Any] = {}
            if offset is not None:
                params["offset"] = offset
            if limit is not None:
                params["limit"] = limit

            logger.info("Fetching all SR policies from COE RESTCONF API")

            response = await client.get(
                f"{self.coe_url}/data/cisco-crosswork-segment-routing-policy:sr-policies",
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/yang-data+json",
                },
            )

            if response.status_code == 404:
                logger.warning("COE RESTCONF API returned 404 for SR policies")
                return {}

            response.raise_for_status()
            data: Dict[str, Any] = response.json()

            logger.info("SR policies fetched")
            return data

        except Exception as e:
            logger.error(
                "Failed to fetch SR policies from COE RESTCONF API",
                error=str(e),
            )
            return {}

    async def get_sr_policy_details(
        self,
        head_end: str,
        end_point: str,
        color: int,
    ) -> Dict[str, Any]:
        """
        Retrieve a single SR policy by its composite key.

        Calls GET {coe_url}/data/cisco-crosswork-segment-routing-policy:sr-policies/
            policy={head_end},{end_point},{color}

        The composite key is formed from three path parameters as defined in
        the COE RESTCONF spec (coe_sr_policy_details.json):
          - policy-headend: Head-end router IP address
          - policy-endpoint: End-point IP address
          - policy-color: Color value associated with the SR policy (uint32)

        Args:
            head_end: Head-end router IP address of the SR policy.
            end_point: End-point IP address of the SR policy.
            color: Color value (uint32) associated with the SR policy.

        Returns:
            Dict with the SR policy object. Returns {} on 404 or error.
        """
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            logger.info(
                "Fetching SR policy from COE RESTCONF API",
                head_end=head_end,
                end_point=end_point,
                color=color,
            )

            response = await client.get(
                f"{self.coe_url}/data/cisco-crosswork-segment-routing-policy:sr-policies"
                f"/policy={head_end},{end_point},{color}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/yang-data+json",
                },
            )

            if response.status_code == 404:
                logger.warning(
                    "COE RESTCONF API returned 404 for SR policy",
                    head_end=head_end,
                    end_point=end_point,
                    color=color,
                )
                return {}

            response.raise_for_status()
            data: Dict[str, Any] = response.json()

            logger.info(
                "SR policy fetched",
                head_end=head_end,
                end_point=end_point,
                color=color,
            )
            return data

        except Exception as e:
            logger.error(
                "Failed to fetch SR policy from COE RESTCONF API",
                head_end=head_end,
                end_point=end_point,
                color=color,
                error=str(e),
            )
            return {}

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
