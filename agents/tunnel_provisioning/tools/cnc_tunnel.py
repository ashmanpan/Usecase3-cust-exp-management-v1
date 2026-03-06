"""CNC Tunnel Client - From DESIGN.md CNC API Integration"""
import asyncio
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
        self.nso_url = os.getenv("CNC_NSO_URL", "https://cnc.example.com:8888/api/operations/dispatch/te-operations:create-rsvp-te-tunnel")
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
        """Create RSVP-TE tunnel via CNC - dispatches to PCE or NSO mode based on env var."""
        mode = os.getenv("TUNNEL_PROVISIONING_MODE", "nso").lower()
        logger.info("RSVP-TE tunnel provisioning mode selected", mode=mode, tunnel_name=config.path_name)

        if mode == "pce":
            return await self._create_rsvp_tunnel_via_pce(config)
        else:
            return await self.create_rsvp_tunnel_via_nso(config)

    async def _create_rsvp_tunnel_via_pce(self, config: TunnelConfig) -> TunnelResult:
        """Create RSVP-TE tunnel via CNC PCE (PCE-initiated) - From DESIGN.md RSVP-TE Create"""
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
            logger.error("RSVP-TE PCE tunnel creation failed", error=str(e))
            return TunnelResult(success=False, tunnel_id="", te_type="rsvp-te", state="failure", message=f"CNC API error: {e}")

    async def create_rsvp_tunnel_via_nso(self, config: TunnelConfig) -> TunnelResult:
        """Create RSVP-TE tunnel via NSO RPC (PCC-initiated / NSO-managed).

        Preferred over PCE-initiated because:
        - Config appears in 'show running' on the router
        - NSO can revert/manage the config
        - PCE-initiated requires HTTP (not HTTPS) on PCE which is blocked by security policy
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        payload = {
            "input": {
                "head-end": config.head_end,
                "end-point": config.end_point,
                "tunnel-name": config.path_name,
                "bandwidth": config.bandwidth_gbps or 10,
                "setup-priority": config.setup_priority or 7,
                "hold-priority": config.hold_priority or 7,
                "exclude-links": config.explicit_hops or [],
            }
        }

        logger.info(
            "Creating RSVP-TE tunnel via NSO",
            tunnel_name=config.path_name,
            head_end=config.head_end,
            end_point=config.end_point,
        )

        try:
            response = await client.post(
                self.nso_url,
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/yang-data+json"},
            )
            if response.status_code in (200, 201, 202):
                data = response.json()
                tunnel_id = f"rsvp-te-{config.head_end}-{config.end_point}"
                return TunnelResult(
                    success=True,
                    tunnel_id=tunnel_id,
                    te_type="rsvp-te",
                    operational_status="up",
                    state="success",
                    message=data.get("output", {}).get("message", "NSO tunnel created"),
                )
            return TunnelResult(
                success=False,
                te_type="rsvp-te",
                message=f"NSO API error: {response.status_code} {response.text}",
            )
        except Exception as e:
            logger.error("RSVP-TE NSO tunnel creation failed", error=str(e))
            return TunnelResult(
                success=False,
                tunnel_id="",
                te_type="rsvp-te",
                state="failure",
                message=f"NSO API error: {e}",
            )

    async def delete_rsvp_tunnel_via_nso(self, tunnel_id: str) -> bool:
        """Delete (revert) an RSVP-TE tunnel managed by NSO."""
        client = await self._get_client()
        token = await self._get_jwt_token()

        # Derive the per-tunnel NSO URL by appending the tunnel_id to the base NSO URL
        nso_base = self.nso_url.rstrip("/")
        delete_url = f"{nso_base}/{tunnel_id}"

        logger.info("Deleting RSVP-TE tunnel via NSO", tunnel_id=tunnel_id, url=delete_url)

        try:
            response = await client.delete(
                delete_url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/yang-data+json"},
            )
            success = response.status_code in (200, 204)
            if not success:
                logger.error(
                    "NSO tunnel delete returned unexpected status",
                    tunnel_id=tunnel_id,
                    status_code=response.status_code,
                )
            return success
        except Exception as e:
            logger.error("RSVP-TE NSO tunnel delete failed", tunnel_id=tunnel_id, error=str(e))
            return False

    async def _poll_nso_job(self, job_id: str) -> TunnelResult:
        """Poll NSO job status until completion, timeout, or failure.

        Polls /api/running/jobs/{job_id} every 3 seconds for up to 30 seconds.
        Returns a TunnelResult reflecting the final job outcome.
        """
        poll_url_base = os.getenv(
            "CNC_NSO_JOBS_URL",
            "https://cnc.example.com:8888/api/running/jobs",
        )
        poll_url = f"{poll_url_base}/{job_id}"
        poll_interval = 3
        max_wait = 30
        attempts = 0

        logger.info("Polling NSO job", job_id=job_id, poll_url=poll_url, max_wait_seconds=max_wait)

        async with httpx.AsyncClient(
            timeout=self.timeout,
            verify=os.getenv("CA_CERT_PATH") or True,
        ) as poll_client:
            token = await self._get_jwt_token()
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/yang-data+json"}

            elapsed = 0
            while elapsed < max_wait:
                attempts += 1
                try:
                    resp = await poll_client.get(poll_url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        status = data.get("status", "running")
                        logger.info(
                            "NSO job poll attempt",
                            job_id=job_id,
                            attempt=attempts,
                            status=status,
                        )
                        if status == "completed":
                            return TunnelResult(
                                success=True,
                                te_type="rsvp-te",
                                state="success",
                                operational_status="up",
                                message=f"NSO job {job_id} completed successfully",
                            )
                        if status == "failed":
                            error_msg = data.get("error", "NSO job failed")
                            logger.error("NSO job failed", job_id=job_id, error=error_msg)
                            return TunnelResult(
                                success=False,
                                te_type="rsvp-te",
                                state="failure",
                                operational_status="down",
                                message=f"NSO job {job_id} failed: {error_msg}",
                            )
                        # status == "running" — continue polling
                    else:
                        logger.warning(
                            "NSO job poll returned unexpected status",
                            job_id=job_id,
                            http_status=resp.status_code,
                        )
                except Exception as e:
                    logger.warning("NSO job poll request error", job_id=job_id, attempt=attempts, error=str(e))

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

        logger.error("NSO job polling timed out", job_id=job_id, attempts=attempts)
        return TunnelResult(
            success=False,
            te_type="rsvp-te",
            state="failure",
            operational_status="down",
            message="NSO job timeout",
        )

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
        """Delete tunnel via CNC API.

        Uses the correct endpoint based on tunnel type:
        - SR-MPLS/SRv6: sr-policy-delete
        - RSVP-TE: rsvp-te-tunnel-delete (PCE-initiated) or NSO revert (NSO mode)
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        try:
            if tunnel_type == "rsvp-te":
                mode = os.getenv("TUNNEL_PROVISIONING_MODE", "nso").lower()
                if mode == "nso":
                    logger.info("Deleting RSVP-TE tunnel via NSO", tunnel_id=tunnel_id)
                    return await self.delete_rsvp_tunnel_via_nso(tunnel_id)

                # PCE-initiated RSVP-TE delete
                logger.info("Deleting RSVP-TE tunnel via PCE endpoint", tunnel_id=tunnel_id)
                response = await client.post(
                    f"{self.base_url}/operations/cisco-crosswork-optimization-engine-rsvp-te-operations:rsvp-te-tunnel-delete",
                    json={"input": {"rsvp-te-tunnels": [{"tunnel-name": tunnel_id}]}},
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/yang-data+json"},
                )
                return response.status_code == 200
            else:
                # SR-MPLS or SRv6
                logger.info("Deleting SR policy tunnel", tunnel_id=tunnel_id, tunnel_type=tunnel_type)
                response = await client.post(
                    f"{self.base_url}/operations/cisco-crosswork-optimization-engine-sr-policy-operations:sr-policy-delete",
                    json={"input": {"sr-policies": [{"policy-name": tunnel_id}]}},
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/yang-data+json"},
                )
                return response.status_code == 200
        except Exception as e:
            logger.error("Tunnel delete failed", tunnel_id=tunnel_id, tunnel_type=tunnel_type, error=str(e))
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
