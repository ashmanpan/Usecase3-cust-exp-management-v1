"""CNC Tunnel Client - From DESIGN.md CNC API Integration"""
import os
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import structlog
import httpx

from ..schemas.tunnels import TunnelConfig, TunnelResult

logger = structlog.get_logger(__name__)

class CNCTunnelClient:
    """Client for CNC PCE tunnel provisioning APIs - From DESIGN.md"""

    def __init__(self, base_url: Optional[str] = None, timeout: int = 60):
        self.base_url = base_url or os.getenv("CNC_BASE_URL", "https://cnc.example.com:30603/crosswork/nbi/optimization/v3/restconf")
        self.auth_url = os.getenv("CNC_AUTH_URL", "https://cnc.example.com:30603/crosswork/sso/v1/tickets")
        self.jwt_url = os.getenv("CNC_JWT_URL", "https://cnc.example.com:30603/crosswork/sso/v2/tickets/jwt")
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
        if self._jwt_token and self._jwt_expires_at and datetime.now(timezone.utc) < self._jwt_expires_at - timedelta(minutes=5):
            return self._jwt_token

        client = await self._get_client()
        username = os.getenv("CNC_USERNAME", "admin")
        password = os.getenv("CNC_PASSWORD", "")

        # Step 1: Get TGT
        tgt_response = await client.post(
            self.auth_url,
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        tgt_response.raise_for_status()
        tgt = tgt_response.text.strip()

        # Step 2: Exchange TGT for JWT
        jwt_response = await client.post(
            self.jwt_url,
            data={"tgt": tgt, "service": f"{self.base_url}/app-dashboard"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        jwt_response.raise_for_status()
        self._jwt_token = jwt_response.text.strip()
        self._jwt_expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
        logger.info("JWT token obtained successfully")
        return self._jwt_token

    async def create_sr_policy(self, config: TunnelConfig) -> TunnelResult:
        """Create SR-MPLS or SRv6 policy via CNC - From DESIGN.md SR Policy Create"""
        client = await self._get_client()
        token = await self._get_jwt_token()

        payload = {
            "input": {
                "sr-policies": [{
                    "head-end": config.head_end,
                    "end-point": config.end_point,
                    "color": config.color or 100,
                    "path-name": config.path_name,
                    "description": f"Protection tunnel for {config.path_name}",
                    "sr-policy-path": {
                        "path-optimization-objective": config.optimization_objective,
                        "protected": config.protected,
                    }
                }]
            }
        }

        if config.binding_sid:
            payload["input"]["sr-policies"][0]["binding-sid"] = config.binding_sid
        if config.explicit_hops:
            payload["input"]["sr-policies"][0]["sr-policy-path"]["hops"] = config.explicit_hops

        endpoint = "/operations/cisco-crosswork-optimization-engine-sr-policy-operations:sr-policy-create"

        try:
            response = await client.post(
                f"{self.base_url}{endpoint}",
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/yang-data+json"},
            )
            if response.status_code == 200:
                data = response.json()
                result = data.get("output", {}).get("results", [{}])[0]
                return TunnelResult(
                    success=result.get("state") == "success",
                    tunnel_id=f"sr-policy-{config.head_end}-{config.end_point}-{config.color or 100}",
                    binding_sid=config.binding_sid,
                    te_type=config.te_type,
                    operational_status="up" if result.get("state") == "success" else "down",
                    state=result.get("state", "failure"),
                    message=result.get("message", "")
                )
            return TunnelResult(success=False, te_type=config.te_type, message=f"API error: {response.status_code}")
        except Exception as e:
            logger.error("Tunnel creation failed", error=str(e))
            return TunnelResult(
                success=False,
                tunnel_id="",
                te_type=config.te_type,
                operational_status="down",
                state="failure",
                message=f"CNC API error: {e}",
            )

    async def create_rsvp_tunnel(self, config: TunnelConfig) -> TunnelResult:
        """Create RSVP-TE tunnel via CNC - From DESIGN.md RSVP-TE Create"""
        client = await self._get_client()
        token = await self._get_jwt_token()

        payload = {
            "input": {
                "rsvp-te-tunnels": [{
                    "head-end": config.head_end,
                    "end-point": config.end_point,
                    "tunnel-name": config.path_name,
                    "bandwidth": config.bandwidth_gbps or 10,
                    "setup-priority": config.setup_priority or 7,
                    "hold-priority": config.hold_priority or 7,
                }]
            }
        }

        endpoint = "/operations/cisco-crosswork-optimization-engine-rsvp-te-operations:rsvp-te-tunnel-create"

        try:
            response = await client.post(
                f"{self.base_url}{endpoint}",
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/yang-data+json"},
            )
            if response.status_code == 200:
                data = response.json()
                result = data.get("output", {}).get("results", [{}])[0]
                return TunnelResult(
                    success=result.get("state") == "success",
                    tunnel_id=f"rsvp-te-{config.head_end}-{config.end_point}",
                    te_type="rsvp-te",
                    operational_status="up" if result.get("state") == "success" else "down",
                    state=result.get("state", "failure"),
                    message=result.get("message", ""),
                )
            return TunnelResult(success=False, te_type="rsvp-te", message=f"API error: {response.status_code}")
        except Exception as e:
            logger.error("RSVP-TE tunnel creation failed", error=str(e))
            return TunnelResult(success=False, tunnel_id="", te_type="rsvp-te", state="failure", message=f"CNC API error: {e}")

    async def verify_tunnel(self, tunnel_id: str, tunnel_type: str) -> Dict[str, Any]:
        """Verify tunnel status via CNC operational state API"""
        client = await self._get_client()
        token = await self._get_jwt_token()

        try:
            response = await client.get(
                f"{self.base_url}/data/cisco-crosswork-optimization-engine-sr-policy-operations:sr-policies/sr-policy={tunnel_id}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/yang-data+json"},
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    "exists": True,
                    "operational_status": data.get("operational-state", "unknown"),
                    "admin_status": data.get("admin-state", "unknown"),
                }
            return {"exists": False, "operational_status": "unknown", "admin_status": "unknown"}
        except Exception as e:
            logger.error("Tunnel verify failed", tunnel_id=tunnel_id, error=str(e))
            return {"exists": False, "operational_status": "error", "admin_status": "unknown", "error": str(e)}

    async def delete_tunnel(self, tunnel_id: str, tunnel_type: str) -> bool:
        """Delete tunnel via CNC API"""
        client = await self._get_client()
        token = await self._get_jwt_token()

        try:
            response = await client.post(
                f"{self.base_url}/operations/cisco-crosswork-optimization-engine-sr-policy-operations:sr-policy-delete",
                json={"input": {"sr-policies": [{"policy-name": tunnel_id}]}},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/yang-data+json"},
            )
            return response.status_code == 200
        except Exception as e:
            logger.error("Tunnel delete failed", tunnel_id=tunnel_id, error=str(e))
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

_cnc_tunnel_client: Optional[CNCTunnelClient] = None

def get_cnc_tunnel_client() -> CNCTunnelClient:
    global _cnc_tunnel_client
    if _cnc_tunnel_client is None:
        _cnc_tunnel_client = CNCTunnelClient()
    return _cnc_tunnel_client
