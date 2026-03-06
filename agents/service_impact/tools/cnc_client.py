"""
CNC Service Health + Service Inventory API Client

Two complementary APIs for querying affected VPN services:

1. CNC Service Health API (existing):
   - GET /services?filter=link_id={link_id}
   - GET /services/{service_id}

2. CNC Service Inventory API (CNC 7.1 - preferred):
   - POST cat-inventory-rpc-get-associated-services-for-transport
     Retrieves all VPN services (L3VPN, L2VPN, SR-TE, RSVP-TE) associated
     with a given underlay transport link — more complete than Service Health API.
   - POST cat-inventory-rpc-get-service-plan-data
     Returns full service plan/config details for a service instance.
   - POST cat-inventory-rpc-get-available-service-types
     Lists all service types provisioned in CNC.
   - POST cat-inventory-rpc-get-all-services
     Returns all service instance references in a batch.
   - POST cat-inventory-rpc-get-services-count
     Returns total count of provisioned service instances.

Reference: https://developer.cisco.com/docs/crosswork/network-controller/
           api-reference-crosswork-active-topology-service-inventory-api-overview/
"""

import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone

import structlog
import httpx

logger = structlog.get_logger(__name__)


class CNCServiceHealthClient:
    """
    Client for CNC Service Health API + Service Inventory API (CNC 7.1).

    Service Health API:
    - GET /services?filter=link_id={link_id} - Query services by link
    - GET /services/{service_id} - Get service details

    Service Inventory API (preferred for transport-to-service mapping):
    - POST /cat-inventory-rpc-get-associated-services-for-transport
    - POST /cat-inventory-rpc-get-service-plan-data
    - POST /cat-inventory-rpc-get-all-services
    - POST /cat-inventory-rpc-get-available-service-types
    - POST /cat-inventory-rpc-get-services-count
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        inventory_url: Optional[str] = None,
        auth_url: Optional[str] = None,
        jwt_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Initialize CNC client.

        Args:
            base_url: CNC Service Health API base URL
            inventory_url: CNC Service Inventory API base URL (CNC 7.1)
            auth_url: CNC SSO auth URL
            jwt_url: CNC JWT exchange URL
            username: CNC username
            password: CNC password
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.getenv(
            "CNC_SERVICE_HEALTH_URL",
            "https://cnc.example.com:30603/crosswork/nbi/servicehealth/v1"
        )
        self.inventory_url = inventory_url or os.getenv(
            "CNC_SERVICE_INVENTORY_URL",
            "https://cnc.example.com:30603/crosswork/nbi/cat-inventory/v1"
        )
        self.auth_url = auth_url or os.getenv(
            "CNC_AUTH_URL",
            "https://cnc.example.com:30603/crosswork/sso/v1/tickets"
        )
        self.jwt_url = jwt_url or os.getenv(
            "CNC_JWT_URL",
            "https://cnc.example.com:30603/crosswork/sso/v2/tickets/jwt"
        )
        self.username = username or os.getenv("CNC_USERNAME", "admin")
        self.password = password or os.getenv("CNC_PASSWORD", "")
        self.timeout = timeout

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

        From DESIGN.md JWT Authentication flow.
        """
        # Check if token is still valid
        if self._jwt_token and self._jwt_expires_at:
            if datetime.now(timezone.utc) < self._jwt_expires_at - timedelta(minutes=5):
                return self._jwt_token

        client = await self._get_client()

        try:
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

        except Exception as e:
            logger.error("Failed to get JWT token", error=str(e))
            raise

    async def get_services_by_link(self, link_id: str) -> List[dict]:
        """
        Query services traversing a specific link.

        From DESIGN.md: GET /services?filter=link_id={link_id}

        Args:
            link_id: Topology link ID

        Returns:
            List of service dicts
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        logger.info("Querying services by link", link_id=link_id)

        try:
            response = await client.get(
                f"{self.base_url}/services",
                params={"filter": f"link_id={link_id}"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            data = response.json()

            services = data.get("services", [])
            logger.info(
                "Services query complete",
                link_id=link_id,
                service_count=len(services),
            )
            return services

        except Exception as e:
            logger.error(
                "Failed to query services",
                link_id=link_id,
                error=str(e),
            )
            # Return empty list for demo/testing
            return []

    async def get_service_details(self, service_id: str) -> dict:
        """
        Get detailed service information.

        From DESIGN.md: GET /services/{service_id}

        Args:
            service_id: Service identifier

        Returns:
            Service details dict
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        logger.info("Getting service details", service_id=service_id)

        try:
            response = await client.get(
                f"{self.base_url}/services/{service_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(
                "Failed to get service details",
                service_id=service_id,
                error=str(e),
            )
            return {}

    async def get_services_by_links(self, link_ids: List[str]) -> Dict[str, List[dict]]:
        """
        Query services for multiple links.

        Args:
            link_ids: List of link IDs

        Returns:
            Dict mapping link_id to list of services
        """
        result = {}
        for link_id in link_ids:
            services = await self.get_services_by_link(link_id)
            result[link_id] = services
        return result

    # -------------------------------------------------------------------------
    # CNC Service Inventory API (CNC 7.1)
    # Reference: /api-reference-crosswork-active-topology-service-inventory-api
    # -------------------------------------------------------------------------

    async def get_services_by_transport(self, transport_id: str, transport_type: str = "link") -> List[dict]:
        """
        Get VPN services associated with a given underlay transport.

        CNC Service Inventory API: cat-inventory-rpc-get-associated-services-for-transport
        More complete than Service Health API -- covers L3VPN, L2VPN, SR-TE policies,
        and RSVP-TE tunnels traversing the given transport link.

        Args:
            transport_id: Underlay transport identifier (link_id, tunnel_id, etc.)
            transport_type: Type of transport ("link", "tunnel", "sr-policy")

        Returns:
            List of service dicts with service_id, service_type, oper_status, vpn_id
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        logger.info(
            "Querying services by transport (Inventory API)",
            transport_id=transport_id,
            transport_type=transport_type,
        )

        try:
            response = await client.post(
                f"{self.inventory_url}/operations/cat-inventory-rpc-get-associated-services-for-transport",
                json={
                    "input": {
                        "transport-id": transport_id,
                        "transport-type": transport_type,
                    }
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            data = response.json()

            services = data.get("output", {}).get("services", [])
            logger.info(
                "Inventory transport query complete",
                transport_id=transport_id,
                service_count=len(services),
            )
            return services

        except Exception as e:
            logger.warning(
                "Service Inventory API failed, falling back to Service Health API",
                transport_id=transport_id,
                error=str(e),
            )
            # Fallback to Service Health API
            return await self.get_services_by_link(transport_id)

    async def get_service_plan(self, service_id: str, service_type: str) -> dict:
        """
        Get full service plan/config details for a service instance.

        CNC Service Inventory API: cat-inventory-rpc-get-service-plan-data

        Args:
            service_id: Service instance identifier
            service_type: Service type (e.g., "ietf-l3vpn", "ietf-l2vpn", "sr-policy")

        Returns:
            Service plan details dict with endpoints, SLA tier, VRF info
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        logger.info("Getting service plan", service_id=service_id, service_type=service_type)

        try:
            response = await client.post(
                f"{self.inventory_url}/operations/cat-inventory-rpc-get-service-plan-data",
                json={
                    "input": {
                        "service-id": service_id,
                        "service-type": service_type,
                    }
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            return response.json().get("output", {})

        except Exception as e:
            logger.error("Failed to get service plan", service_id=service_id, error=str(e))
            # Fallback to Service Health API
            return await self.get_service_details(service_id)

    async def get_all_services(self) -> List[dict]:
        """
        Retrieve all service instance references in a batch.

        CNC Service Inventory API: cat-inventory-rpc-get-all-services

        Returns:
            List of all service instance references
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        logger.info("Fetching all service instances")

        try:
            response = await client.post(
                f"{self.inventory_url}/operations/cat-inventory-rpc-get-all-services",
                json={"input": {}},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            return response.json().get("output", {}).get("services", [])

        except Exception as e:
            logger.error("Failed to get all services", error=str(e))
            return []

    async def get_available_service_types(self) -> List[str]:
        """
        Query supported service types in CNC.

        CNC Service Inventory API: cat-inventory-rpc-get-available-service-types

        Returns:
            List of service type identifiers (e.g., "ietf-l3vpn", "sr-policy")
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        try:
            response = await client.post(
                f"{self.inventory_url}/operations/cat-inventory-rpc-get-available-service-types",
                json={"input": {}},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            return response.json().get("output", {}).get("service-types", [])

        except Exception as e:
            logger.error("Failed to get service types", error=str(e))
            return []

    async def get_service_count(self) -> int:
        """
        Get total count of provisioned service instances.

        CNC Service Inventory API: cat-inventory-rpc-get-services-count

        Returns:
            Total service instance count
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        try:
            response = await client.post(
                f"{self.inventory_url}/operations/cat-inventory-rpc-get-services-count",
                json={"input": {}},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            return response.json().get("output", {}).get("count", 0)

        except Exception as e:
            logger.error("Failed to get service count", error=str(e))
            return 0

    async def get_l3vpn_sub_service_paths(self, vpn_id: str) -> List[dict]:
        """
        Get IETF-L3VPN sub-service instance references.

        CNC Service Inventory API: cat-inventory-rpc-get-sub-service-paths
        Returns sub-service paths within a parent L3VPN service (e.g., per-PE VRF instances).

        Args:
            vpn_id: L3VPN service VPN ID

        Returns:
            List of sub-service path references
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        logger.info("Getting L3VPN sub-service paths", vpn_id=vpn_id)

        try:
            response = await client.post(
                f"{self.inventory_url}/operations/cat-inventory-rpc-get-sub-service-paths",
                json={"input": {"vpn-id": vpn_id}},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            return response.json().get("output", {}).get("sub-service-paths", [])

        except Exception as e:
            logger.error("Failed to get L3VPN sub-service paths", vpn_id=vpn_id, error=str(e))
            return []

    async def get_l3vpn_sub_service_count(self, vpn_id: str) -> int:
        """
        Get count of sub-services within an IETF-L3VPN service instance.

        CNC Service Inventory API: cat-inventory-rpc-get-sub-service-count

        Args:
            vpn_id: L3VPN service VPN ID

        Returns:
            Count of sub-service instances
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        try:
            response = await client.post(
                f"{self.inventory_url}/operations/cat-inventory-rpc-get-sub-service-count",
                json={"input": {"vpn-id": vpn_id}},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            return response.json().get("output", {}).get("count", 0)

        except Exception as e:
            logger.error("Failed to get L3VPN sub-service count", vpn_id=vpn_id, error=str(e))
            return 0

    async def get_l3vpn_service(self, vpn_id: str) -> dict:
        """
        Get L3VPN service configuration and operational state via RESTCONF.

        IETF L3VPN Service Config API (RESTCONF):
        GET /ietf-l3vpn-ntw/vpn-services/vpn-service={vpn-id}

        Returns full service definition including:
        - vpn-id, customer-name, sla-tier
        - vpn-nodes (PE devices, VRFs, CE endpoints)
        - underlay-transport references
        - oper-status

        Args:
            vpn_id: L3VPN VPN identifier

        Returns:
            L3VPN service dict
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        restconf_url = os.getenv(
            "CNC_RESTCONF_URL",
            "https://cnc.example.com:30603/crosswork/nbi/restconf/data"
        )

        logger.info("Getting L3VPN service config", vpn_id=vpn_id)

        try:
            response = await client.get(
                f"{restconf_url}/ietf-l3vpn-ntw:l3vpn-ntw/vpn-services/vpn-service={vpn_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("ietf-l3vpn-svc:vpn-service", data)

        except Exception as e:
            logger.error("Failed to get L3VPN service", vpn_id=vpn_id, error=str(e))
            return {}

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
_cnc_client: Optional[CNCServiceHealthClient] = None


def get_cnc_client() -> CNCServiceHealthClient:
    """Get singleton CNC client instance."""
    global _cnc_client
    if _cnc_client is None:
        _cnc_client = CNCServiceHealthClient()
    return _cnc_client
