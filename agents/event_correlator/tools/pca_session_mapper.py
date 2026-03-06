"""
PCA Session to CNC Link Mapper

Maps PCA session endpoints (source_ip/dest_ip) to CNC topology link_ids.
Required because PCA reports sessions by IP, but CNC Service Health API
uses topology link_ids.

The mapping is built by querying CNC Topology API for links matching
the given PE/P router loopback addresses.
"""

import os
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta, timezone

import structlog
import httpx

logger = structlog.get_logger(__name__)


class PCASessionMapper:
    """
    Maps PCA session (source_ip, dest_ip) pairs to CNC topology link_ids.

    PCA measures overlay sessions identified by loopback IP pairs. CNC Service
    Health and Topology APIs use opaque link_id strings. This class bridges the
    gap by querying the CNC Topology API with loopback IPs and caching results.

    Cache entries expire after _cache_ttl_seconds (default 300 s / 5 min) to
    allow topology changes to propagate without a service restart.
    """

    def __init__(self) -> None:
        self.base_url: str = os.getenv(
            "CNC_TOPOLOGY_URL",
            "https://cnc.example.com:30603/crosswork/nbi/topology/v1",
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

        # Cache: (source_ip, dest_ip) -> {"link_id": str, "cached_at": datetime}
        self._cache: Dict[Tuple[str, str], Dict] = {}
        self._cache_ttl_seconds: int = 300

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
        logger.debug("PCASessionMapper: getting TGT from CNC SSO")
        tgt_response = await client.post(
            self.auth_url,
            data={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        tgt_response.raise_for_status()
        tgt = tgt_response.text.strip()

        # Step 2: Exchange TGT for JWT
        logger.debug("PCASessionMapper: exchanging TGT for JWT")
        jwt_response = await client.post(
            self.jwt_url,
            data={"tgt": tgt, "service": f"{self.base_url}/app-dashboard"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        jwt_response.raise_for_status()
        self._jwt_token = jwt_response.text.strip()
        self._jwt_expires_at = datetime.now(timezone.utc) + timedelta(hours=8)

        logger.info("PCASessionMapper: JWT token obtained successfully")
        return self._jwt_token

    def _cache_key(self, source_ip: str, dest_ip: str) -> Tuple[str, str]:
        return (source_ip, dest_ip)

    def _get_cached_link_id(self, source_ip: str, dest_ip: str) -> Optional[str]:
        """Return cached link_id if present and not expired."""
        key = self._cache_key(source_ip, dest_ip)
        entry = self._cache.get(key)
        if entry is None:
            return None
        age = (datetime.now(timezone.utc) - entry["cached_at"]).total_seconds()
        if age > self._cache_ttl_seconds:
            del self._cache[key]
            return None
        return entry["link_id"]

    def _store_cached_link_id(
        self, source_ip: str, dest_ip: str, link_id: str
    ) -> None:
        """Store a link_id in the cache."""
        key = self._cache_key(source_ip, dest_ip)
        self._cache[key] = {
            "link_id": link_id,
            "cached_at": datetime.now(timezone.utc),
        }

    async def resolve_link_id(self, source_ip: str, dest_ip: str) -> str:
        """
        Resolve a PCA session (source_ip, dest_ip) to a CNC topology link_id.

        Resolution order:
        1. In-memory cache (TTL: _cache_ttl_seconds).
        2. CNC Topology API: GET .../topology/links?source_loopback=<ip>&dest_loopback=<ip>
        3. Fallback string "link-{source_ip}-{dest_ip}" with a warning log.

        Args:
            source_ip: Source PE/P router loopback address from PCA session.
            dest_ip:   Destination PE/P router loopback address from PCA session.

        Returns:
            CNC topology link_id string (real or synthesised fallback).
        """
        fallback = f"link-{source_ip}-{dest_ip}"

        # 1. Cache hit
        cached = self._get_cached_link_id(source_ip, dest_ip)
        if cached is not None:
            logger.debug(
                "PCASessionMapper: cache hit",
                source_ip=source_ip,
                dest_ip=dest_ip,
                link_id=cached,
            )
            return cached

        # 2. Topology API lookup
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            response = await client.get(
                f"{self.base_url}/topology/links",
                params={
                    "source_loopback": source_ip,
                    "dest_loopback": dest_ip,
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            data = response.json()

            links = data.get("links", [])
            if links:
                link_id: str = links[0]["link_id"]
                self._store_cached_link_id(source_ip, dest_ip, link_id)
                logger.info(
                    "PCASessionMapper: resolved link_id from topology",
                    source_ip=source_ip,
                    dest_ip=dest_ip,
                    link_id=link_id,
                )
                return link_id

            # No links found in topology response
            logger.warning(
                "PCA session could not be mapped to CNC link_id, using fallback",
                source_ip=source_ip,
                dest_ip=dest_ip,
                fallback=fallback,
            )
            return fallback

        except Exception as e:
            logger.error(
                "PCASessionMapper: error resolving link_id, using fallback",
                source_ip=source_ip,
                dest_ip=dest_ip,
                fallback=fallback,
                error=str(e),
            )
            return fallback

    async def resolve_pe_nodes(
        self, source_ip: str, dest_ip: str
    ) -> Tuple[str, str]:
        """
        Resolve loopback IPs to CNC node_ids (used for topology path lookup).

        Queries GET .../topology/nodes?loopback=<ip> for both IPs.

        Args:
            source_ip: Source loopback IP.
            dest_ip:   Destination loopback IP.

        Returns:
            Tuple (pe_source_node_id, pe_dest_node_id).
            Falls back to (source_ip, dest_ip) on any error.
        """
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            auth_headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/yang-data+json",
            }

            # Fetch both nodes concurrently
            import asyncio

            source_resp, dest_resp = await asyncio.gather(
                client.get(
                    f"{self.base_url}/topology/nodes",
                    params={"loopback": source_ip},
                    headers=auth_headers,
                ),
                client.get(
                    f"{self.base_url}/topology/nodes",
                    params={"loopback": dest_ip},
                    headers=auth_headers,
                ),
                return_exceptions=True,
            )

            pe_source = source_ip
            pe_dest = dest_ip

            if not isinstance(source_resp, Exception):
                source_resp.raise_for_status()
                pe_source = source_resp.json().get("node_id", source_ip)

            if not isinstance(dest_resp, Exception):
                dest_resp.raise_for_status()
                pe_dest = dest_resp.json().get("node_id", dest_ip)

            logger.info(
                "PCASessionMapper: resolved PE nodes",
                source_ip=source_ip,
                dest_ip=dest_ip,
                pe_source=pe_source,
                pe_dest=pe_dest,
            )
            return (pe_source, pe_dest)

        except Exception as e:
            logger.error(
                "PCASessionMapper: error resolving PE nodes, using IP fallback",
                source_ip=source_ip,
                dest_ip=dest_ip,
                error=str(e),
            )
            return (source_ip, dest_ip)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Module-level singleton
_pca_session_mapper: Optional[PCASessionMapper] = None


def get_pca_session_mapper() -> PCASessionMapper:
    """Get singleton PCASessionMapper instance."""
    global _pca_session_mapper
    if _pca_session_mapper is None:
        _pca_session_mapper = PCASessionMapper()
    return _pca_session_mapper
