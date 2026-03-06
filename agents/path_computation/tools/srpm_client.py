"""
SRPM (Segment Routing Performance Monitoring) Client

Provides per-link delay/loss metrics using SR-native measurements.
For use when network has migrated to SR-MPLS (future phase for Jio/Geo).

Krishnan Thirukonda (2026-03-05): "If you have full SR, use link SRPM
for per-hop measurements — much more accurate than overlay PCA sessions."

Current status: SR not yet deployed on Jio/Geo network (expected Sept/Oct 2026).
This client is a stub for future integration.
"""

import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone

import structlog
import httpx

logger = structlog.get_logger(__name__)


class SRPMClient:
    """
    Client for CNC SRPM (Segment Routing Performance Monitoring) API.

    SRPM provides native per-link delay/loss measurements when the network
    runs SR-MPLS, offering higher accuracy than overlay PCA sessions.

    Availability is gated by the SRPM_ENABLED environment variable. When the
    variable is not set to "true" all methods return graceful no-op responses
    so that the rest of the pipeline continues to function.
    """

    def __init__(self) -> None:
        self.base_url: str = os.getenv(
            "CNC_SRPM_URL",
            "https://cnc.example.com:30603/crosswork/nbi/srpm/v1",
        )
        self.auth_url: str = os.getenv(
            "CNC_AUTH_URL",
            "https://cnc.example.com:30603/crosswork/sso/v1/tickets",
        )
        self.jwt_url: str = os.getenv(
            "CNC_JWT_URL",
            "https://cnc.example.com:30603/crosswork/sso/v2/tickets/jwt",
        )
        self.username: str = os.getenv("CNC_USERNAME", "admin")
        self.password: str = os.getenv("CNC_PASSWORD", "")
        self.timeout: int = 30

        # SRPM is only active when SR is deployed and the env var is set
        self._is_available: bool = (
            os.getenv("SRPM_ENABLED", "false").lower() == "true"
        )

        self._jwt_token: Optional[str] = None
        self._jwt_expires_at: Optional[datetime] = None
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared HTTP client."""
        if self._client is None:
            ca_cert = os.getenv("CA_CERT_PATH")
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                verify=ca_cert if ca_cert else True,
            )
        return self._client

    async def _get_jwt_token(self) -> str:
        """
        Obtain a JWT token via TGT exchange.

        Same pattern as CNCTopologyClient. Token cached for 8 hours with a
        5-minute safety margin on renewal.
        """
        if self._jwt_token and self._jwt_expires_at:
            if datetime.now(timezone.utc) < self._jwt_expires_at - timedelta(minutes=5):
                return self._jwt_token

        client = await self._get_client()

        # Step 1: Get TGT
        logger.debug("SRPMClient: getting TGT from CNC SSO")
        tgt_response = await client.post(
            self.auth_url,
            data={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        tgt_response.raise_for_status()
        tgt = tgt_response.text.strip()

        # Step 2: Exchange TGT for JWT
        logger.debug("SRPMClient: exchanging TGT for JWT")
        jwt_response = await client.post(
            self.jwt_url,
            data={"tgt": tgt, "service": f"{self.base_url}/app-dashboard"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        jwt_response.raise_for_status()
        self._jwt_token = jwt_response.text.strip()
        self._jwt_expires_at = datetime.now(timezone.utc) + timedelta(hours=8)

        logger.info("SRPMClient: JWT token obtained successfully")
        return self._jwt_token

    async def is_available(self) -> bool:
        """
        Return whether SRPM measurements are available.

        Returns True only when the SRPM_ENABLED environment variable is set to
        "true", indicating that SR-MPLS has been deployed on the target network.
        """
        return self._is_available

    async def get_link_metrics(
        self,
        link_id: str,
        window_minutes: int = 5,
    ) -> Dict[str, Any]:
        """
        Fetch SRPM per-link delay and loss metrics.

        Calls GET {CNC_SRPM_URL}/links/{link_id}/metrics?window={window_minutes}m

        Args:
            link_id:        CNC topology link ID.
            window_minutes: Measurement aggregation window in minutes.

        Returns:
            Dict with keys:
                link_id, delay_usec, delay_variation_usec,
                packet_loss_pct, measurement_time.
            Returns {"available": False, "reason": ...} when SRPM is not enabled.
            Returns {"available": False, "error": ...} on HTTP/network errors.
        """
        if not self._is_available:
            logger.warning(
                "SRPM not enabled (SR not deployed)",
                link_id=link_id,
            )
            return {"available": False, "reason": "SRPM_ENABLED not set"}

        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            logger.info(
                "Fetching SRPM link metrics",
                link_id=link_id,
                window_minutes=window_minutes,
            )

            response = await client.get(
                f"{self.base_url}/links/{link_id}/metrics",
                params={"window": f"{window_minutes}m"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            data: Dict[str, Any] = response.json()

            logger.info(
                "SRPM link metrics fetched",
                link_id=link_id,
                delay_usec=data.get("delay_usec"),
                packet_loss_pct=data.get("packet_loss_pct"),
            )
            return data

        except Exception as e:
            logger.error(
                "Failed to fetch SRPM link metrics",
                link_id=link_id,
                error=str(e),
            )
            return {"available": False, "error": str(e)}

    async def get_path_metrics(
        self,
        segment_list: List[str],
        window_minutes: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Fetch per-hop SRPM metrics for each segment in an SR policy.

        Args:
            segment_list:   List of link_ids or segment identifiers in the SR path.
            window_minutes: Measurement aggregation window in minutes.

        Returns:
            List of per-hop metric dicts (same schema as get_link_metrics).
            Returns [] when SRPM is not enabled or on error.
        """
        if not self._is_available:
            logger.warning(
                "SRPM not enabled (SR not deployed) — skipping path metrics",
                segment_count=len(segment_list),
            )
            return []

        results: List[Dict[str, Any]] = []
        for segment in segment_list:
            metrics = await self.get_link_metrics(segment, window_minutes=window_minutes)
            results.append(metrics)

        return results

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Module-level singleton
_srpm_client: Optional[SRPMClient] = None


def get_srpm_client() -> SRPMClient:
    """Get singleton SRPMClient instance."""
    global _srpm_client
    if _srpm_client is None:
        _srpm_client = SRPMClient()
    return _srpm_client
