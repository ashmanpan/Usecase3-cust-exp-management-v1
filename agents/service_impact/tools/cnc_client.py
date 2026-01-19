"""
CNC Service Health API Client

Client for querying CNC Service Health API.
From DESIGN.md: CNCServiceHealthClient for affected services.
"""

import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

import structlog
import httpx

logger = structlog.get_logger(__name__)


class CNCServiceHealthClient:
    """
    Client for CNC Service Health API.

    From DESIGN.md:
    - GET /services?filter=link_id={link_id} - Query services by link
    - GET /services/{service_id} - Get service details
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
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
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                verify=False,  # For self-signed certs
            )
        return self._client

    async def _get_jwt_token(self) -> str:
        """
        Get JWT token via TGT exchange.

        From DESIGN.md JWT Authentication flow.
        """
        # Check if token is still valid
        if self._jwt_token and self._jwt_expires_at:
            if datetime.utcnow() < self._jwt_expires_at - timedelta(minutes=5):
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
            self._jwt_expires_at = datetime.utcnow() + timedelta(hours=8)

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
