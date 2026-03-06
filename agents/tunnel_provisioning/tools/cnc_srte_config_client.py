"""
CNC SR-TE Policy Service Config API Client

Crosswork Active Topology — Cisco SR-TE Policy Service Config API (v7.1.0)
Reference: /api-reference-crosswork-active-topology-cisco-sr-te-policy-service-config-api

Endpoints (RESTCONF over YANG):
  GET/PUT/PATCH/DELETE  /cisco-sr-te-cfp:sr-te/policies/policy={head-end},{color},{end-point}
  POST                  /cisco-sr-te-cfp:sr-te/policies  (create)

Key request fields:
  - head-end:      source router (head-end PE)
  - color:         numeric color (maps to service intent / SLA class)
  - end-point:     destination router IPv4/IPv6
  - segment-list:  ordered list of SIDs [{index, sid-type, mpls-label|ipv6-address}]
  - binding-sid:   MPLS label for policy (BSID)
  - preference:    candidate path priority (0-4294967295)
  - name:          human-readable policy name

Complements cnc_tunnel.py which handles both NSO-initiated RSVP-TE
and CNC PCE-initiated SR policies. This client adds RESTCONF-based
SR-TE config for cases where CNC Crosswork Active Topology is the
provisioning system (not PCE REST API).
"""

import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone

import structlog
import httpx

logger = structlog.get_logger(__name__)


class CNCSRTEConfigClient:
    """
    Client for CNC SR-TE Policy Service Config API (RESTCONF).

    API: Crosswork Active Topology - Cisco SR-TE Policy Service Config v7.1.0
    OpenAPI spec: cisco_sr_te_cfp_7_1_0.json

    CRUD operations for SR-TE policies via RESTCONF YANG:
    - Create SR-TE policy with segment list
    - Query policy status and provisioning state
    - Update candidate paths / segment lists
    - Delete SR-TE policy
    """

    def __init__(
        self,
        restconf_url: Optional[str] = None,
        auth_url: Optional[str] = None,
        jwt_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 30,
    ):
        self.restconf_url = restconf_url or os.getenv(
            "CNC_RESTCONF_URL",
            "https://cnc.example.com:30603/crosswork/nbi/restconf/data"
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
        if self._client is None:
            ca_cert = os.getenv("CA_CERT_PATH")
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                verify=ca_cert if ca_cert else True,
            )
        return self._client

    async def _get_jwt_token(self) -> str:
        if self._jwt_token and self._jwt_expires_at:
            if datetime.now(timezone.utc) < self._jwt_expires_at - timedelta(minutes=5):
                return self._jwt_token

        client = await self._get_client()

        tgt_response = await client.post(
            self.auth_url,
            data={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        tgt_response.raise_for_status()
        tgt = tgt_response.text.strip()

        jwt_response = await client.post(
            self.jwt_url,
            data={"tgt": tgt, "service": f"{self.restconf_url}/app-dashboard"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        jwt_response.raise_for_status()
        self._jwt_token = jwt_response.text.strip()
        self._jwt_expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
        return self._jwt_token

    def _policy_key(self, head_end: str, color: int, end_point: str) -> str:
        """Build RESTCONF key for SR-TE policy."""
        return f"{head_end},{color},{end_point}"

    async def create_sr_policy(
        self,
        head_end: str,
        color: int,
        end_point: str,
        segment_list: List[Dict[str, Any]],
        binding_sid: Optional[int] = None,
        preference: int = 100,
        name: Optional[str] = None,
    ) -> dict:
        """
        Create an SR-TE policy via RESTCONF.

        Args:
            head_end:     Source head-end PE IP
            color:        Policy color (maps to SLA class / ODN intent)
            end_point:    Destination PE IP
            segment_list: Ordered SIDs, e.g.:
                          [{"index": 1, "sid-type": "mpls", "mpls-label": 16001},
                           {"index": 2, "sid-type": "mpls", "mpls-label": 16002}]
            binding_sid:  BSID MPLS label (optional)
            preference:   Candidate path preference (default 100)
            name:         Human-readable policy name

        Returns:
            Created policy response dict
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        policy_name = name or f"cem-{head_end}-c{color}-{end_point}"

        payload: Dict[str, Any] = {
            "cisco-sr-te-cfp:policy": {
                "name": policy_name,
                "head-end": head_end,
                "color": color,
                "end-point": end_point,
                "candidate-paths": {
                    "preference": preference,
                    "explicit-segment-list": {
                        "name": f"sl-{policy_name}",
                        "hops": segment_list,
                    },
                },
            }
        }

        if binding_sid is not None:
            payload["cisco-sr-te-cfp:policy"]["binding-sid"] = {
                "mpls-label": binding_sid
            }

        logger.info(
            "Creating SR-TE policy (RESTCONF)",
            head_end=head_end,
            color=color,
            end_point=end_point,
        )

        try:
            response = await client.post(
                f"{self.restconf_url}/cisco-sr-te-cfp:sr-te/policies",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                    "Accept": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            return response.json() if response.content else {"status": "created"}

        except Exception as e:
            logger.error(
                "Failed to create SR-TE policy",
                head_end=head_end,
                color=color,
                end_point=end_point,
                error=str(e),
            )
            raise

    async def get_sr_policy(self, head_end: str, color: int, end_point: str) -> dict:
        """
        Get SR-TE policy configuration and operational state.

        Returns policy including:
        - oper-status: active / down / programmed
        - provisioning-state: provisioned / failed
        - candidate-paths with segment lists
        - binding-sid value

        Args:
            head_end:  Head-end PE IP
            color:     Policy color
            end_point: Destination PE IP

        Returns:
            Policy dict
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        key = self._policy_key(head_end, color, end_point)

        try:
            response = await client.get(
                f"{self.restconf_url}/cisco-sr-te-cfp:sr-te/policies/policy={key}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("cisco-sr-te-cfp:policy", data)

        except Exception as e:
            logger.error("Failed to get SR-TE policy", key=key, error=str(e))
            return {}

    async def update_sr_policy_segment_list(
        self,
        head_end: str,
        color: int,
        end_point: str,
        segment_list: List[Dict[str, Any]],
        preference: int = 100,
    ) -> dict:
        """
        Update the segment list of an existing SR-TE policy (PATCH).

        Args:
            head_end:     Head-end PE IP
            color:        Policy color
            end_point:    Destination PE IP
            segment_list: New ordered SID list
            preference:   Candidate path preference

        Returns:
            Updated policy response
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        key = self._policy_key(head_end, color, end_point)
        policy_name = f"cem-{head_end}-c{color}-{end_point}"

        payload = {
            "cisco-sr-te-cfp:policy": {
                "candidate-paths": {
                    "preference": preference,
                    "explicit-segment-list": {
                        "name": f"sl-{policy_name}",
                        "hops": segment_list,
                    },
                }
            }
        }

        logger.info("Updating SR-TE policy segment list", key=key)

        try:
            response = await client.patch(
                f"{self.restconf_url}/cisco-sr-te-cfp:sr-te/policies/policy={key}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            return {"status": "updated", "key": key}

        except Exception as e:
            logger.error("Failed to update SR-TE policy", key=key, error=str(e))
            raise

    async def delete_sr_policy(self, head_end: str, color: int, end_point: str) -> bool:
        """
        Delete an SR-TE policy via RESTCONF.

        Args:
            head_end:  Head-end PE IP
            color:     Policy color
            end_point: Destination PE IP

        Returns:
            True if deleted successfully
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        key = self._policy_key(head_end, color, end_point)

        logger.info("Deleting SR-TE policy (RESTCONF)", key=key)

        try:
            response = await client.delete(
                f"{self.restconf_url}/cisco-sr-te-cfp:sr-te/policies/policy={key}",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            logger.info("SR-TE policy deleted", key=key)
            return True

        except Exception as e:
            logger.error("Failed to delete SR-TE policy", key=key, error=str(e))
            return False

    async def list_sr_policies(self) -> List[dict]:
        """
        List all SR-TE policies.

        Returns:
            List of policy dicts with head-end, color, end-point, oper-status
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        try:
            response = await client.get(
                f"{self.restconf_url}/cisco-sr-te-cfp:sr-te/policies",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("cisco-sr-te-cfp:policies", {}).get("policy", [])

        except Exception as e:
            logger.error("Failed to list SR-TE policies", error=str(e))
            return []

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton
_srte_client: Optional[CNCSRTEConfigClient] = None


def get_srte_config_client() -> CNCSRTEConfigClient:
    """Get singleton SR-TE Config client instance."""
    global _srte_client
    if _srte_client is None:
        _srte_client = CNCSRTEConfigClient()
    return _srte_client
