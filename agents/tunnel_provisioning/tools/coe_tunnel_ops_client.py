"""
COE Tunnel Operations Client

Crosswork Optimization Engine (COE) — RSVP-TE Tunnel Operations and SR Policy Operations APIs (v7.1.0)

References:
  - api_specs/coe_rsvp_te_tunnel_ops.yaml  (Cisco Crosswork RSVP-TE Tunnel Operations API)
  - api_specs/coe_sr_policy_ops.yaml        (Cisco Crosswork SR Policy Operations API)

Base path: /crosswork/nbi/optimization/v3/restconf

RSVP-TE Tunnel Operations endpoints:
  POST  /operations/cisco-crosswork-optimization-engine-rsvp-te-tunnel-operations:rsvp-te-datalist-oper
  POST  /operations/cisco-crosswork-optimization-engine-rsvp-te-tunnel-operations:rsvp-te-tunnel-create
  POST  /operations/cisco-crosswork-optimization-engine-rsvp-te-tunnel-operations:rsvp-te-tunnel-delete
  POST  /operations/cisco-crosswork-optimization-engine-rsvp-te-tunnel-operations:rsvp-te-tunnel-modify
  POST  /operations/cisco-crosswork-optimization-engine-rsvp-te-tunnel-operations:rsvp-te-tunnel-dryrun

SR Policy Operations endpoints:
  POST  /operations/cisco-crosswork-optimization-engine-sr-policy-operations:sr-datalist-oper
  POST  /operations/cisco-crosswork-optimization-engine-sr-policy-operations:sr-policy-create
  POST  /operations/cisco-crosswork-optimization-engine-sr-policy-operations:sr-policy-delete
  POST  /operations/cisco-crosswork-optimization-engine-sr-policy-operations:sr-policy-modify
  POST  /operations/cisco-crosswork-optimization-engine-sr-policy-operations:sr-policy-dryrun

Authentication: Two-step JWT — TGT via SSO v1, then JWT via SSO v2 (same pattern as cnc_tunnel.py).
"""

import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone

import structlog
import httpx

logger = structlog.get_logger(__name__)

# YANG content-type used by all COE RESTCONF endpoints
_YANG_JSON = "application/yang-data+json"

# Endpoint path prefix constants
_RSVP_PREFIX = (
    "/operations/cisco-crosswork-optimization-engine-rsvp-te-tunnel-operations:"
)
_SR_PREFIX = (
    "/operations/cisco-crosswork-optimization-engine-sr-policy-operations:"
)


class COETunnelOpsClient:
    """
    Client for Crosswork Optimization Engine (COE) Tunnel Operations APIs.

    Covers both:
    - RSVP-TE Tunnel Operations (coe_rsvp_te_tunnel_ops.yaml v7.1.0)
    - SR Policy Operations      (coe_sr_policy_ops.yaml v7.1.0)

    Authentication uses the same two-step JWT flow as CNCTunnelClient:
      1. POST to SSO v1 with credentials → Ticket Granting Ticket (TGT)
      2. POST to SSO v2 with TGT → short-lived JWT (8-hour cache, 5-min early refresh)

    All requests carry:
      Authorization: Bearer <jwt>
      Content-Type: application/yang-data+json
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        auth_url: Optional[str] = None,
        jwt_url: Optional[str] = None,
        timeout: int = 60,
    ):
        self.base_url = base_url or os.getenv(
            "CNC_COE_URL",
            "https://cnc.example.com:30603/crosswork/nbi/optimization/v3/restconf",
        )
        self.auth_url = auth_url or os.getenv(
            "CNC_AUTH_URL",
            "https://cnc.example.com:30603/crosswork/sso/v1/tickets",
        )
        self.jwt_url = jwt_url or os.getenv(
            "CNC_JWT_URL",
            "https://cnc.example.com:30603/crosswork/sso/v2/tickets/jwt",
        )
        self.timeout = timeout

        self._jwt_token: Optional[str] = None
        self._jwt_expires_at: Optional[datetime] = None
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        """Return (or lazily create) the shared async HTTP client."""
        if self._client is None:
            ca_cert = os.getenv("CA_CERT_PATH")
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                verify=ca_cert if ca_cert else True,
            )
        return self._client

    async def _get_jwt_token(self) -> str:
        """
        Return a valid JWT, refreshing if expired or within 5 minutes of expiry.

        Two-step SSO flow (identical to cnc_tunnel.py):
          Step 1: POST credentials → TGT (text/plain response)
          Step 2: POST TGT         → JWT (text/plain response)
        """
        if (
            self._jwt_token
            and self._jwt_expires_at
            and datetime.now(timezone.utc) < self._jwt_expires_at - timedelta(minutes=5)
        ):
            return self._jwt_token

        client = await self._get_client()
        username = os.getenv("CNC_USERNAME", "admin")
        password = os.getenv("CNC_PASSWORD", "")

        # Step 1: Obtain TGT
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

        logger.info("COE JWT token obtained successfully")
        return self._jwt_token

    def _auth_headers(self, token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": _YANG_JSON,
        }

    async def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST *payload* to *endpoint* (relative to base_url) and return the
        parsed JSON response body.  Raises on non-2xx responses.
        """
        client = await self._get_client()
        token = await self._get_jwt_token()

        url = f"{self.base_url}{endpoint}"
        logger.debug("COE POST", url=url)

        response = await client.post(
            url,
            json=payload,
            headers=self._auth_headers(token),
        )
        response.raise_for_status()
        # 204 No Content is a valid success with an empty body
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    # ==================================================================
    # RSVP-TE Tunnel Operations
    # ==================================================================

    async def list_rsvp_tunnels(
        self, filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Retrieve the RSVP-TE tunnel data list from COE.

        POST /operations/..:rsvp-te-datalist-oper

        Spec: rsvp.te.tunnel.operations.rsvptedatalistoper.Input
          Optional filter fields (all optional per spec):
            action          (GET | SAVE | DELETE | RESPONSE | SYNC_START | SYNC_DONE)
            not-pce-initiated (bool)
            last-update-time  (int32 Unix epoch)
            offset            (int64)
            end-of-list       (bool)
            application-id    (str)
            is-orphan         (bool)
            source-app-id     (str)
            rsvp-datalist     (list of RsvpDatalist entries for SAVE/DELETE)

        Args:
            filters: Optional dict of input fields to include in the request body.
                     Defaults to a simple GET action when omitted.

        Returns:
            Parsed output dict containing rsvp-datalist, state, message, etc.
        """
        input_body: Dict[str, Any] = {"action": "GET"}
        if filters:
            input_body.update(filters)

        endpoint = f"{_RSVP_PREFIX}rsvp-te-datalist-oper"
        logger.info("Listing RSVP-TE tunnels from COE", filters=filters)

        try:
            data = await self._post(endpoint, {"input": input_body})
            return data.get("output", data)
        except Exception as e:
            logger.error("list_rsvp_tunnels failed", error=str(e))
            raise

    async def create_rsvp_tunnel(
        self,
        tunnel_name: str,
        source: str,
        destination: str,
        bandwidth: int,
        path_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new RSVP-TE tunnel via COE PCE.

        POST /operations/..:rsvp-te-tunnel-create

        Spec: rsvp.te.tunnel.common.RsvpTeTunnelDetailList
          rsvp-te-tunnels[]:
            head-end         (str, required) – source router IP / hostname
            end-point        (str, required) – destination router IP / hostname
            path-name        (str, required) – tunnel path name (key field)
            signaled-bandwidth (int32, default 0) – bandwidth in Mbps
            setup-priority   (int64, optional)
            hold-priority    (int64, optional)
            fast-re-route    ("enable"|"disable", optional)
            binding-label    (int64, optional)
            description      (str, optional)
            rsvp-te-tunnel-path (RsvpTeTunnelPath, optional):
              hops[]           – explicit path hops (x-choice: explicit-path)
              optimization-objective – igp-metric | te-metric | delay (dynamic-path)
              affinities       – include-all/exclude-any/include-any bitmasks
              disjointness     – association-group/type/sub-group

        Args:
            tunnel_name:  Path name identifying the tunnel (maps to path-name).
            source:       Head-end router IP or hostname.
            destination:  End-point router IP or hostname.
            bandwidth:    Signaled bandwidth in Mbps (int32).
            path_options: Optional dict merged into rsvp-te-tunnel-path.
                          Example for dynamic path:
                            {"optimization-objective": "igp-metric"}
                          Example for explicit path:
                            {"hops": [{"step": 1, "hop-type": "strict",
                                       "hop": {"node-address": "10.0.0.1"}}]}

        Returns:
            Parsed output dict; output.results[] contains per-tunnel state/message.
        """
        tunnel_entry: Dict[str, Any] = {
            "head-end": source,
            "end-point": destination,
            "path-name": tunnel_name,
            "signaled-bandwidth": bandwidth,
        }
        if path_options:
            tunnel_entry["rsvp-te-tunnel-path"] = path_options

        endpoint = f"{_RSVP_PREFIX}rsvp-te-tunnel-create"
        logger.info(
            "Creating RSVP-TE tunnel via COE",
            tunnel_name=tunnel_name,
            source=source,
            destination=destination,
            bandwidth=bandwidth,
        )

        try:
            data = await self._post(
                endpoint,
                {"input": {"rsvp-te-tunnels": [tunnel_entry]}},
            )
            return data.get("output", data)
        except Exception as e:
            logger.error(
                "create_rsvp_tunnel failed",
                tunnel_name=tunnel_name,
                source=source,
                error=str(e),
            )
            raise

    async def delete_rsvp_tunnel(
        self, tunnel_name: str, source: str
    ) -> Dict[str, Any]:
        """
        Delete an existing RSVP-TE tunnel via COE PCE.

        POST /operations/..:rsvp-te-tunnel-delete

        Spec: rsvp.te.tunnel.common.RsvpTeTunnelKeyList
          rsvp-te-tunnels[]:
            head-end   (str, required) – source router IP / hostname
            path-name  (str, required) – tunnel path name

        Note: end-point is part of RsvpTeTunnelEndPoints (parent of KeyFields) but
        the spec marks head-end + path-name as the minimal key for deletion.
        Callers may pass end-point inside a subclassed call if needed.

        Args:
            tunnel_name: Path name of the tunnel to delete (maps to path-name).
            source:      Head-end router IP or hostname (maps to head-end).

        Returns:
            Parsed output dict; output.results[] contains per-tunnel state/message.
        """
        tunnel_key: Dict[str, Any] = {
            "head-end": source,
            "path-name": tunnel_name,
        }

        endpoint = f"{_RSVP_PREFIX}rsvp-te-tunnel-delete"
        logger.info(
            "Deleting RSVP-TE tunnel via COE",
            tunnel_name=tunnel_name,
            source=source,
        )

        try:
            data = await self._post(
                endpoint,
                {"input": {"rsvp-te-tunnels": [tunnel_key]}},
            )
            return data.get("output", data)
        except Exception as e:
            logger.error(
                "delete_rsvp_tunnel failed",
                tunnel_name=tunnel_name,
                source=source,
                error=str(e),
            )
            raise

    async def modify_rsvp_tunnel(
        self,
        tunnel_name: str,
        source: str,
        bandwidth: Optional[int] = None,
        path_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Modify an existing RSVP-TE tunnel via COE PCE.

        POST /operations/..:rsvp-te-tunnel-modify

        Spec: rsvp.te.tunnel.common.RsvpTeTunnelDetailList  (same schema as create)
          rsvp-te-tunnels[]:
            head-end          (str, required)
            path-name         (str, required)
            signaled-bandwidth (int32, optional)
            rsvp-te-tunnel-path (RsvpTeTunnelPath, optional)
            setup-priority    (int64, optional)
            hold-priority     (int64, optional)
            fast-re-route     ("enable"|"disable", optional)
            binding-label     (int64, optional)
            description       (str, optional)

        Args:
            tunnel_name:  Path name of the tunnel to modify.
            source:       Head-end router IP or hostname.
            bandwidth:    New signaled bandwidth in Mbps (omit to leave unchanged).
            path_options: Optional dict replacing rsvp-te-tunnel-path.

        Returns:
            Parsed output dict; output.results[] contains per-tunnel state/message.
        """
        tunnel_entry: Dict[str, Any] = {
            "head-end": source,
            "path-name": tunnel_name,
        }
        if bandwidth is not None:
            tunnel_entry["signaled-bandwidth"] = bandwidth
        if path_options is not None:
            tunnel_entry["rsvp-te-tunnel-path"] = path_options

        endpoint = f"{_RSVP_PREFIX}rsvp-te-tunnel-modify"
        logger.info(
            "Modifying RSVP-TE tunnel via COE",
            tunnel_name=tunnel_name,
            source=source,
            bandwidth=bandwidth,
        )

        try:
            data = await self._post(
                endpoint,
                {"input": {"rsvp-te-tunnels": [tunnel_entry]}},
            )
            return data.get("output", data)
        except Exception as e:
            logger.error(
                "modify_rsvp_tunnel failed",
                tunnel_name=tunnel_name,
                source=source,
                error=str(e),
            )
            raise

    async def dryrun_rsvp_tunnel(
        self,
        tunnel_name: str,
        source: str,
        destination: str,
        bandwidth: int,
        path_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Simulate RSVP-TE tunnel creation/modification without applying changes.

        POST /operations/..:rsvp-te-tunnel-dryrun

        Spec: rsvp.te.tunnel.common.RsvpTeTunnelDryrunInput
          Extends RsvpTeTunnelPath with:
            head-end           (str, required) – source router IP / hostname
            end-point          (str, required) – destination router IP / hostname
            signaled-bandwidth (int32, default 0) – bandwidth in Mbps
          Plus inherited path fields from RsvpTeTunnelPath:
            rsvp-te-tunnel-path (RsvpTeTunnelPath):
              hops[]             – explicit path hops
              optimization-objective
              affinities
              disjointness

        Response: RsvpTeTunnelDryrunResult
          path-hops[]: [{ip-address, step}]
          state:   success | failure | degraded
          message: detail string for non-success states

        Args:
            tunnel_name:  Informational path name (not a key for dryrun, included
                          for logging clarity).
            source:       Head-end router IP or hostname.
            destination:  End-point router IP or hostname.
            bandwidth:    Signaled bandwidth in Mbps.
            path_options: Optional dict merged into the top-level input alongside
                          the endpoint fields (maps to rsvp-te-tunnel-path sub-object
                          per the allOf schema).

        Returns:
            Parsed output dict; output.path-hops, output.state, output.message.
        """
        input_body: Dict[str, Any] = {
            "head-end": source,
            "end-point": destination,
            "signaled-bandwidth": bandwidth,
        }
        if path_options:
            # path_options may contain rsvp-te-tunnel-path or its child fields
            input_body.update(path_options)

        endpoint = f"{_RSVP_PREFIX}rsvp-te-tunnel-dryrun"
        logger.info(
            "Dry-running RSVP-TE tunnel via COE",
            tunnel_name=tunnel_name,
            source=source,
            destination=destination,
            bandwidth=bandwidth,
        )

        try:
            data = await self._post(endpoint, {"input": input_body})
            return data.get("output", data)
        except Exception as e:
            logger.error(
                "dryrun_rsvp_tunnel failed",
                tunnel_name=tunnel_name,
                source=source,
                error=str(e),
            )
            raise

    # ==================================================================
    # SR Policy Operations
    # ==================================================================

    async def list_sr_policies(
        self, filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Retrieve the SR policy data list from COE.

        POST /operations/..:sr-datalist-oper

        Spec: sr.policy.operations.srdatalistoper.Input
          Extends OeDatalistCommonInfo with:
            sr-policy-datalist (list of SrPolicyDatalist, optional)
          Common filter fields (all optional):
            action            (GET | SAVE | DELETE | RESPONSE | SYNC_START | SYNC_DONE)
            not-pce-initiated (bool)
            last-update-time  (int32 Unix epoch)
            offset            (int64)
            end-of-list       (bool)
            application-id    (str)
            is-orphan         (bool)
            source-app-id     (str)

        Args:
            filters: Optional dict of input fields.  Defaults to GET action.

        Returns:
            Parsed output dict containing sr-policy-datalist, rsvp-datalist,
            state, message, etc.
        """
        input_body: Dict[str, Any] = {"action": "GET"}
        if filters:
            input_body.update(filters)

        endpoint = f"{_SR_PREFIX}sr-datalist-oper"
        logger.info("Listing SR policies from COE", filters=filters)

        try:
            data = await self._post(endpoint, {"input": input_body})
            return data.get("output", data)
        except Exception as e:
            logger.error("list_sr_policies failed", error=str(e))
            raise

    async def create_sr_policy_coe(
        self,
        head_end: str,
        color: int,
        end_point: str,
        segment_list: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Create a new SR policy via COE PCE operations API.

        POST /operations/..:sr-policy-create

        Spec: sr.policy.common.SrPolicyDetailList
          sr-policies[]:
            head-end    (str, required) – source head-end PE IP / hostname
            end-point   (str, required) – destination PE IP / hostname
            color       (int64, required) – policy color (SLA class)
            path-name   (str, optional)
            description (str, optional)
            binding-sid (int64, optional)
            profile-id  (int64, optional)
            sr-policy-path (SrPolicyPath, optional):
              hops[]                   – explicit path (x-choice: explicit-path)
                Each hop: {step, hop: {node-ipv4-address|adjacency-ipv4-sid|...}}
              path-optimization-objective – igp-metric|te-metric|delay|hop-count
              disjointness             – association-group/type/sub-group
              protected                (bool)
              bandwidth                (int32, bandwidth-path mode)
              affinities               – include-all/exclude-any/include-any
              sid-algorithm            (int32)

        Args:
            head_end:     Source head-end PE IP or hostname.
            color:        Policy color (numeric, maps to SLA class).
            end_point:    Destination PE IP or hostname.
            segment_list: Explicit path hops in SrPolicyPath.hops format.
                          Example:
                            [{"step": 1,
                              "hop": {"node-ipv4-address": "10.0.0.1",
                                      "node-ipv4-sid": 16001}}]
                          Pass an empty list [] for a dynamic (PCE-computed) path
                          without explicit hops.

        Returns:
            Parsed output dict; output.results[] contains per-policy state/message/color.
        """
        policy_entry: Dict[str, Any] = {
            "head-end": head_end,
            "end-point": end_point,
            "color": color,
        }
        if segment_list:
            policy_entry["sr-policy-path"] = {"hops": segment_list}

        endpoint = f"{_SR_PREFIX}sr-policy-create"
        logger.info(
            "Creating SR policy via COE",
            head_end=head_end,
            color=color,
            end_point=end_point,
            hop_count=len(segment_list),
        )

        try:
            data = await self._post(
                endpoint,
                {"input": {"sr-policies": [policy_entry]}},
            )
            return data.get("output", data)
        except Exception as e:
            logger.error(
                "create_sr_policy_coe failed",
                head_end=head_end,
                color=color,
                end_point=end_point,
                error=str(e),
            )
            raise

    async def delete_sr_policy_coe(
        self, head_end: str, color: int, end_point: str
    ) -> Dict[str, Any]:
        """
        Delete an existing SR policy via COE PCE operations API.

        POST /operations/..:sr-policy-delete

        Spec: sr.policy.common.SrPolicyKeyList
          sr-policies[]:
            head-end  (str, required)
            end-point (str, required)
            color     (int64, required)

        Args:
            head_end:  Source head-end PE IP or hostname.
            color:     Policy color.
            end_point: Destination PE IP or hostname.

        Returns:
            Parsed output dict; output.results[] contains per-policy state/message.
        """
        policy_key: Dict[str, Any] = {
            "head-end": head_end,
            "end-point": end_point,
            "color": color,
        }

        endpoint = f"{_SR_PREFIX}sr-policy-delete"
        logger.info(
            "Deleting SR policy via COE",
            head_end=head_end,
            color=color,
            end_point=end_point,
        )

        try:
            data = await self._post(
                endpoint,
                {"input": {"sr-policies": [policy_key]}},
            )
            return data.get("output", data)
        except Exception as e:
            logger.error(
                "delete_sr_policy_coe failed",
                head_end=head_end,
                color=color,
                end_point=end_point,
                error=str(e),
            )
            raise

    async def modify_sr_policy_coe(
        self,
        head_end: str,
        color: int,
        end_point: str,
        segment_list: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Modify an existing SR policy via COE PCE operations API.

        POST /operations/..:sr-policy-modify

        Spec: sr.policy.common.SrPolicyDetailList (same schema as create)
          sr-policies[]:
            head-end      (str, required)
            end-point     (str, required)
            color         (int64, required)
            path-name     (str, optional)
            description   (str, optional)
            binding-sid   (int64, optional)
            profile-id    (int64, optional)
            sr-policy-path (SrPolicyPath, optional)

        Args:
            head_end:     Source head-end PE IP or hostname.
            color:        Policy color.
            end_point:    Destination PE IP or hostname.
            segment_list: New explicit path hops (SrPolicyPath.hops format).
                          Pass an empty list [] to switch to dynamic PCE path.

        Returns:
            Parsed output dict; output.results[] contains per-policy state/message.
        """
        policy_entry: Dict[str, Any] = {
            "head-end": head_end,
            "end-point": end_point,
            "color": color,
        }
        if segment_list:
            policy_entry["sr-policy-path"] = {"hops": segment_list}

        endpoint = f"{_SR_PREFIX}sr-policy-modify"
        logger.info(
            "Modifying SR policy via COE",
            head_end=head_end,
            color=color,
            end_point=end_point,
            hop_count=len(segment_list),
        )

        try:
            data = await self._post(
                endpoint,
                {"input": {"sr-policies": [policy_entry]}},
            )
            return data.get("output", data)
        except Exception as e:
            logger.error(
                "modify_sr_policy_coe failed",
                head_end=head_end,
                color=color,
                end_point=end_point,
                error=str(e),
            )
            raise

    async def dryrun_sr_policy_coe(
        self,
        head_end: str,
        color: int,
        end_point: str,
        segment_list: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Simulate SR policy creation/modification without applying changes.

        POST /operations/..:sr-policy-dryrun

        Spec: sr.policy.common.SrPolicyDryrunInput
          Extends SrPolicyEndPoints with:
            head-end       (str, required)
            end-point      (str, required)
            sr-policy-path (SrPolicyPath, optional):
              hops[]                   – explicit path hops
              path-optimization-objective
              disjointness
              protected                (bool)
              bandwidth                (int32)
              affinities
              sid-algorithm            (int32)

        Response: SrPolicyDryrunResult
          segment-list-hops[]: [{ip-address, step, type, sid}]
          igp-route[]:         [{interface, node}]
          state:   success | failure | degraded
          message: detail string for non-success states

        Args:
            head_end:     Source head-end PE IP or hostname.
            color:        Policy color (included for caller context; the spec's
                          dryrun input schema inherits SrPolicyEndPoints which does
                          not include color, but color is passed through sr-policy-path
                          context where applicable).
            end_point:    Destination PE IP or hostname.
            segment_list: Explicit path hops in SrPolicyPath.hops format.

        Returns:
            Parsed output dict; output.segment-list-hops, output.state, output.message.
        """
        input_body: Dict[str, Any] = {
            "head-end": head_end,
            "end-point": end_point,
        }
        if segment_list:
            input_body["sr-policy-path"] = {"hops": segment_list}

        endpoint = f"{_SR_PREFIX}sr-policy-dryrun"
        logger.info(
            "Dry-running SR policy via COE",
            head_end=head_end,
            color=color,
            end_point=end_point,
            hop_count=len(segment_list),
        )

        try:
            data = await self._post(endpoint, {"input": input_body})
            return data.get("output", data)
        except Exception as e:
            logger.error(
                "dryrun_sr_policy_coe failed",
                head_end=head_end,
                color=color,
                end_point=end_point,
                error=str(e),
            )
            raise

    # ==================================================================
    # Verification helpers (read-only)
    # ==================================================================

    async def get_rsvp_tunnel(
        self, headend: str, endpoint: str, tunnel_id: str
    ) -> Dict[str, Any]:
        """
        Retrieve a single RSVP-TE tunnel by head-end, end-point, and tunnel-id.

        Calls the datalist-oper GET endpoint and filters the returned
        rsvp-datalist for an entry matching *headend*, *endpoint*, and
        *tunnel_id* (matched against the path-name field).

        Returns:
            Matching tunnel dict, or an empty dict if not found / on error.
            Relevant keys: operational-status, admin-status, path-name,
                           head-end, end-point, signaled-bandwidth.
        """
        logger.info(
            "get_rsvp_tunnel",
            headend=headend,
            endpoint=endpoint,
            tunnel_id=tunnel_id,
        )
        try:
            data = await self.list_rsvp_tunnels()
            entries: List[Dict[str, Any]] = data.get("rsvp-datalist", [])
            for entry in entries:
                if (
                    entry.get("head-end") == headend
                    and entry.get("end-point") == endpoint
                    and entry.get("path-name") == tunnel_id
                ):
                    return entry
            logger.warning(
                "get_rsvp_tunnel: no matching tunnel found",
                headend=headend,
                endpoint=endpoint,
                tunnel_id=tunnel_id,
            )
            return {}
        except Exception as e:
            logger.error(
                "get_rsvp_tunnel failed",
                headend=headend,
                endpoint=endpoint,
                tunnel_id=tunnel_id,
                error=str(e),
            )
            raise

    async def get_sr_policy_details(
        self, head_end: str, end_point: str, color: int
    ) -> Dict[str, Any]:
        """
        Retrieve a single SR policy by head-end, end-point, and color.

        Calls the sr-datalist-oper GET endpoint and filters the returned
        sr-policy-datalist for an entry matching *head_end*, *end_point*,
        and *color*.

        Returns:
            Matching policy dict, or an empty dict if not found / on error.
            Relevant keys: operational-status, admin-status, head-end,
                           end-point, color, binding-sid.
        """
        logger.info(
            "get_sr_policy_details",
            head_end=head_end,
            end_point=end_point,
            color=color,
        )
        try:
            data = await self.list_sr_policies()
            entries: List[Dict[str, Any]] = data.get("sr-policy-datalist", [])
            for entry in entries:
                if (
                    entry.get("head-end") == head_end
                    and entry.get("end-point") == end_point
                    and entry.get("color") == color
                ):
                    return entry
            logger.warning(
                "get_sr_policy_details: no matching policy found",
                head_end=head_end,
                end_point=end_point,
                color=color,
            )
            return {}
        except Exception as e:
            logger.error(
                "get_sr_policy_details failed",
                head_end=head_end,
                end_point=end_point,
                color=color,
                error=str(e),
            )
            raise

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client and clear the JWT cache."""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._jwt_token = None
        self._jwt_expires_at = None


# ---------------------------------------------------------------------------
# Module-level singleton factory
# ---------------------------------------------------------------------------

_coe_tunnel_ops_client: Optional[COETunnelOpsClient] = None


def get_coe_tunnel_ops_client() -> COETunnelOpsClient:
    """
    Return the module-level singleton COETunnelOpsClient instance.

    The instance is created on first call using environment variables:
      CNC_COE_URL   – COE RESTCONF base URL
      CNC_AUTH_URL  – SSO v1 TGT endpoint
      CNC_JWT_URL   – SSO v2 JWT endpoint
      CNC_USERNAME  – login username
      CNC_PASSWORD  – login password
      CA_CERT_PATH  – optional CA bundle for TLS verification
    """
    global _coe_tunnel_ops_client
    if _coe_tunnel_ops_client is None:
        _coe_tunnel_ops_client = COETunnelOpsClient()
    return _coe_tunnel_ops_client
