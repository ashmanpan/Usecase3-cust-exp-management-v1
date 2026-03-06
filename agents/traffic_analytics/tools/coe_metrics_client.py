"""COE Performance Metrics Client - Crosswork Optimization Engine APIs"""
import os
from typing import Any, Dict, List, Optional
import httpx
import structlog

logger = structlog.get_logger(__name__)

# Default base URLs derived from spec server definitions
_DEFAULT_COE_URL = "https://cnc.example.com:30603/crosswork/nbi/optimization/v3/restconf"
_DEFAULT_PM_URL = "https://cnc.example.com:30603/crosswork/nbi/topology/v3/restconf"
_DEFAULT_NPM_URL = "https://cnc.example.com:30603/crosswork/optima-analytics"

# YANG module prefix used by the Performance Metrics RESTCONF paths
_PM_MODULE = "cisco-crosswork-performance-metrics"
# YANG module prefix used by the COE Operations RPC paths
_COE_OPS_MODULE = "cisco-crosswork-optimization-engine-operations"


class COEMetricsClient:
    """
    Client for Cisco Crosswork Optimization Engine (COE) metrics APIs.

    Covers three API surfaces:
    - Performance Metrics (RESTCONF GET) - IGP links, SR policies, RSVP LSPs
    - COE Operations (RESTCONF POST RPC) - SR policy metrics, routes, node/interface queries
    - NPM Analytics (REST POST) - LSP utilization time-series

    Authentication follows the JWT Bearer pattern used by the COE Operations API
    (api_key header) and Basic Auth fallback for the performance metrics RESTCONF
    endpoints which declare basicAuth security.

    Environment variables
    ---------------------
    CNC_COE_URL   : Base URL for the COE Operations RESTCONF interface.
                    Default: https://cnc.example.com:30603/crosswork/nbi/optimization/v3/restconf
    CNC_PM_URL    : Base URL for the Performance Metrics RESTCONF interface.
                    Default: https://cnc.example.com:30603/crosswork/nbi/topology/v3/restconf
    CNC_NPM_URL   : Base URL for the NPM Analytics (optima-analytics) service.
                    Default: https://cnc.example.com:30603/crosswork/optima-analytics
    CNC_JWT_TOKEN : Bearer token injected as the ``Authorization`` header.
    CNC_USERNAME  : Username for Basic Auth (performance metrics endpoints).
    CNC_PASSWORD  : Password for Basic Auth (performance metrics endpoints).
    CA_CERT_PATH  : Path to a CA certificate bundle for TLS verification.
    """

    def __init__(
        self,
        coe_base_url: Optional[str] = None,
        pm_base_url: Optional[str] = None,
        npm_base_url: Optional[str] = None,
        timeout: int = 30,
    ):
        self.coe_base_url = (
            coe_base_url or os.getenv("CNC_COE_URL", _DEFAULT_COE_URL)
        ).rstrip("/")
        self.pm_base_url = (
            pm_base_url or os.getenv("CNC_PM_URL", _DEFAULT_PM_URL)
        ).rstrip("/")
        self.npm_base_url = (
            npm_base_url or os.getenv("CNC_NPM_URL", _DEFAULT_NPM_URL)
        ).rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        """Return a shared async HTTP client, creating it on first call."""
        if self._client is None or self._client.is_closed:
            ca_cert = os.getenv("CA_CERT_PATH")
            verify: Any = ca_cert if ca_cert else True

            # Build default headers shared across all requests
            headers: Dict[str, str] = {
                "Accept": "application/yang-data+json",
                "Content-Type": "application/yang-data+json",
            }

            jwt_token = os.getenv("CNC_JWT_TOKEN")
            if jwt_token:
                headers["Authorization"] = f"Bearer {jwt_token}"

            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                verify=verify,
                headers=headers,
            )
        return self._client

    def _basic_auth(self) -> Optional[httpx.BasicAuth]:
        """Return Basic Auth credentials if username/password are configured."""
        username = os.getenv("CNC_USERNAME")
        password = os.getenv("CNC_PASSWORD")
        if username and password:
            return httpx.BasicAuth(username, password)
        return None

    async def _get(self, base_url: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        """Perform a GET request and return the parsed JSON body."""
        url = f"{base_url}{path}"
        client = await self._get_client()
        auth = self._basic_auth()
        logger.debug("COE GET request", url=url)
        response = await client.get(url, auth=auth, **kwargs)
        response.raise_for_status()
        return response.json()

    async def _post(
        self,
        base_url: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Perform a POST request with an optional JSON body and return parsed JSON."""
        url = f"{base_url}{path}"
        client = await self._get_client()
        logger.debug("COE POST request", url=url, body=body)
        response = await client.post(url, json=body, **kwargs)
        response.raise_for_status()
        # Some operations return 204 No Content - return empty dict in that case
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    # ------------------------------------------------------------------
    # Performance Metrics API  (RESTCONF GET, coe_performance_metrics.json)
    # Spec server base: /crosswork/nbi/topology/v3/restconf
    # These collection-level GETs omit the key predicate to retrieve all items.
    # ------------------------------------------------------------------

    async def get_igp_links_metrics(self) -> Dict[str, Any]:
        """
        Retrieve IGP links performance metrics for all links.

        RESTCONF GET
        /data/cisco-crosswork-performance-metrics:igp-links-performance-metrics

        Returns the raw response dict.  The key
        ``cisco-crosswork-performance-metrics:igp-links-performance-metrics``
        contains a list of igp-link-pm objects with fields: link-id, source,
        destination, max-bandwidth-kbps, bandwidth-utilization-kbps, delay,
        delay-telemetry, jitter-telemetry, interfaces.
        """
        path = f"/data/{_PM_MODULE}:igp-links-performance-metrics"
        logger.info("Fetching IGP links performance metrics")
        try:
            return await self._get(self.pm_base_url, path)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "IGP links metrics request failed",
                status_code=exc.response.status_code,
                url=str(exc.request.url),
            )
            raise
        except httpx.HTTPError as exc:
            logger.error("IGP links metrics HTTP error", error=str(exc))
            raise

    async def get_sr_policies_metrics(self) -> Dict[str, Any]:
        """
        Retrieve SR policies performance metrics for all SR policies.

        RESTCONF GET
        /data/cisco-crosswork-performance-metrics:sr-policies-performance-metrics

        Each policy in the response carries: headend, endpoint, color,
        bandwidth-utilization-kbps, delay, delay-telemetry, jitter-telemetry,
        liveness-telemetry.
        """
        path = f"/data/{_PM_MODULE}:sr-policies-performance-metrics"
        logger.info("Fetching SR policies performance metrics")
        try:
            return await self._get(self.pm_base_url, path)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "SR policies metrics request failed",
                status_code=exc.response.status_code,
                url=str(exc.request.url),
            )
            raise
        except httpx.HTTPError as exc:
            logger.error("SR policies metrics HTTP error", error=str(exc))
            raise

    async def get_rsvp_policies_metrics(self) -> Dict[str, Any]:
        """
        Retrieve RSVP LSP performance metrics for all RSVP LSPs.

        RESTCONF GET
        /data/cisco-crosswork-performance-metrics:rsvp-policies-performance-metrics

        Each LSP in the response carries: headend, endpoint, tunnel-id,
        bandwidth-utilization-kbps, delay, delay-telemetry, jitter-telemetry.
        """
        path = f"/data/{_PM_MODULE}:rsvp-policies-performance-metrics"
        logger.info("Fetching RSVP policies performance metrics")
        try:
            return await self._get(self.pm_base_url, path)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "RSVP policies metrics request failed",
                status_code=exc.response.status_code,
                url=str(exc.request.url),
            )
            raise
        except httpx.HTTPError as exc:
            logger.error("RSVP policies metrics HTTP error", error=str(exc))
            raise

    # ------------------------------------------------------------------
    # COE Operations API  (RESTCONF POST RPCs, coe_optimization_engine.yaml)
    # Spec server base: /crosswork/nbi/optimization/v3/restconf
    # Request body wraps fields under {"input": {...}}.
    # ------------------------------------------------------------------

    async def get_sr_policy_metrics(
        self,
        head_end: str,
        color: int,
        end_point: str,
    ) -> Dict[str, Any]:
        """
        Retrieve metrics for a specific SR policy.

        RESTCONF POST
        /operations/cisco-crosswork-optimization-engine-operations:sr-policy-metrics

        Request body (sr.policy.common.SrPolicyKeyList):
            input.sr-policies[].head-end  - Source IP of the SR policy
            input.sr-policies[].color     - SR policy color (integer)
            input.sr-policies[].end-point - Destination IP of the SR policy

        Response includes: head-end, end-point, color, igp-metric, delay,
        te-metric, path-computation-status.

        Parameters
        ----------
        head_end : str
            Head-end (source) IP address of the SR policy.
        color : int
            Color associated with the SR policy.
        end_point : str
            End-point (destination) IP address of the SR policy.
        """
        path = f"/operations/{_COE_OPS_MODULE}:sr-policy-metrics"
        body = {
            "input": {
                "sr-policies": [
                    {
                        "head-end": head_end,
                        "color": color,
                        "end-point": end_point,
                    }
                ]
            }
        }
        logger.info(
            "Fetching SR policy metrics",
            head_end=head_end,
            color=color,
            end_point=end_point,
        )
        try:
            return await self._post(self.coe_base_url, path, body=body)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "SR policy metrics request failed",
                status_code=exc.response.status_code,
                head_end=head_end,
                color=color,
                end_point=end_point,
            )
            raise
        except httpx.HTTPError as exc:
            logger.error(
                "SR policy metrics HTTP error", error=str(exc),
                head_end=head_end, color=color, end_point=end_point,
            )
            raise

    async def get_sr_policies_on_interface(
        self,
        router_id: str,
        interface_name: str,
    ) -> Dict[str, Any]:
        """
        Retrieve SR policies traversing a specific interface.

        RESTCONF POST
        /operations/cisco-crosswork-optimization-engine-operations:sr-policies-on-interface

        Request body (common.InterfaceKeyList):
            input.interfaces[].node      - Hostname of the source node
            input.interfaces[].interface - Interface name on that node

        Response includes: interface-sr-policies[] with interface, node,
        sr-policies list, and message.

        Parameters
        ----------
        router_id : str
            Hostname of the router (node) that owns the interface.
        interface_name : str
            Interface name (e.g. ``GigabitEthernet0/0/0/0``).
        """
        path = f"/operations/{_COE_OPS_MODULE}:sr-policies-on-interface"
        body = {
            "input": {
                "interfaces": [
                    {
                        "node": router_id,
                        "interface": interface_name,
                    }
                ]
            }
        }
        logger.info(
            "Fetching SR policies on interface",
            router_id=router_id,
            interface_name=interface_name,
        )
        try:
            return await self._post(self.coe_base_url, path, body=body)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "SR policies on interface request failed",
                status_code=exc.response.status_code,
                router_id=router_id,
                interface_name=interface_name,
            )
            raise
        except httpx.HTTPError as exc:
            logger.error(
                "SR policies on interface HTTP error", error=str(exc),
                router_id=router_id, interface_name=interface_name,
            )
            raise

    async def get_sr_policies_on_node(
        self,
        router_id: str,
        filter_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve SR policies associated with a specific node.

        RESTCONF POST
        /operations/cisco-crosswork-optimization-engine-operations:sr-policies-on-node

        Request body (operations.srpoliciesonnode.Input):
            input.nodes[].node  - Hostname of the target node
            input.filter        - Optional filter enumeration:
                                  "through-nodes" | "nodes-as-source" |
                                  "nodes-as-destination" |
                                  "nodes-as-source-or-destination"

        Response includes: node-sr-policies[] with node, sr-policies list,
        and message.

        Parameters
        ----------
        router_id : str
            Hostname of the router whose SR policies should be retrieved.
        filter_mode : str, optional
            Filter to scope which policies are returned.  One of:
            ``through-nodes``, ``nodes-as-source``,
            ``nodes-as-destination``, ``nodes-as-source-or-destination``.
        """
        path = f"/operations/{_COE_OPS_MODULE}:sr-policies-on-node"
        input_body: Dict[str, Any] = {
            "nodes": [{"node": router_id}]
        }
        if filter_mode is not None:
            input_body["filter"] = filter_mode
        body = {"input": input_body}
        logger.info(
            "Fetching SR policies on node",
            router_id=router_id,
            filter_mode=filter_mode,
        )
        try:
            return await self._post(self.coe_base_url, path, body=body)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "SR policies on node request failed",
                status_code=exc.response.status_code,
                router_id=router_id,
            )
            raise
        except httpx.HTTPError as exc:
            logger.error(
                "SR policies on node HTTP error", error=str(exc),
                router_id=router_id,
            )
            raise

    async def get_sr_policy_routes(
        self,
        head_end: str,
        color: int,
        end_point: str,
    ) -> Dict[str, Any]:
        """
        Retrieve the IGP routes used by a specific SR policy.

        RESTCONF POST
        /operations/cisco-crosswork-optimization-engine-operations:sr-policy-routes

        Request body (sr.policy.common.SrPolicyKeyList):
            input.sr-policies[].head-end  - Source IP of the SR policy
            input.sr-policies[].color     - SR policy color (integer)
            input.sr-policies[].end-point - Destination IP of the SR policy

        Response includes: results[] with head-end, end-point, color,
        igp-route (list of interface/node/interface-use), path-computation-status.

        Parameters
        ----------
        head_end : str
            Head-end (source) IP address of the SR policy.
        color : int
            Color associated with the SR policy.
        end_point : str
            End-point (destination) IP address of the SR policy.
        """
        path = f"/operations/{_COE_OPS_MODULE}:sr-policy-routes"
        body = {
            "input": {
                "sr-policies": [
                    {
                        "head-end": head_end,
                        "color": color,
                        "end-point": end_point,
                    }
                ]
            }
        }
        logger.info(
            "Fetching SR policy routes",
            head_end=head_end,
            color=color,
            end_point=end_point,
        )
        try:
            return await self._post(self.coe_base_url, path, body=body)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "SR policy routes request failed",
                status_code=exc.response.status_code,
                head_end=head_end,
                color=color,
                end_point=end_point,
            )
            raise
        except httpx.HTTPError as exc:
            logger.error(
                "SR policy routes HTTP error", error=str(exc),
                head_end=head_end, color=color, end_point=end_point,
            )
            raise

    async def get_optimization_plan(
        self,
        format: Optional[str] = None,
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve the current COE optimization plan.

        RESTCONF POST
        /operations/cisco-crosswork-optimization-engine-operations:get-plan

        Request body (operations.getplan.Input) - all fields optional:
            input.format  - Output format: "pln" or "txt"
            input.version - Plan version (default: "current")

        Response includes: planfile-content (string), status, message.

        Parameters
        ----------
        format : str, optional
            Requested format for the plan output.  One of ``"pln"`` or ``"txt"``.
        version : str, optional
            Plan version to retrieve (defaults to ``"current"`` server-side).
        """
        path = f"/operations/{_COE_OPS_MODULE}:get-plan"
        input_body: Dict[str, Any] = {}
        if format is not None:
            input_body["format"] = format
        if version is not None:
            input_body["version"] = version
        body: Optional[Dict[str, Any]] = {"input": input_body} if input_body else None
        logger.info("Fetching optimization plan", format=format, version=version)
        try:
            return await self._post(self.coe_base_url, path, body=body)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Optimization plan request failed",
                status_code=exc.response.status_code,
            )
            raise
        except httpx.HTTPError as exc:
            logger.error("Optimization plan HTTP error", error=str(exc))
            raise

    # ------------------------------------------------------------------
    # NPM Analytics API  (REST POST, coe_npm_metrics.json)
    # Spec server base: https://{cnc-server}:30603/crosswork/optima-analytics/
    # The primary metrics endpoint is POST /api/v1/lsp/utilizations which
    # returns time-series utilization data for a given LSP.
    # ------------------------------------------------------------------

    async def get_npm_metrics(
        self,
        lsp_type: str = "SR",
        peer_address: Optional[str] = None,
        dest_address: Optional[str] = None,
        color: Optional[str] = None,
        tunnel_id: Optional[str] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve NPM LSP utilization time-series data.

        POST /api/v1/lsp/utilizations

        Request body fields (from coe_npm_metrics.json examples):
            lspType      - "SR" or "RSVP"
            peerAddress  - Head-end / peer IP address
            destAddress  - Destination IP address
            color        - SR policy color (SR only, as string)
            tunnelId     - RSVP tunnel ID (RSVP only, as string)
            from         - ISO 8601 start timestamp (e.g. "2021-10-13T15:55:07.000Z")
            to           - ISO 8601 end timestamp

        Response is a list of objects with ``util`` (float) and ``tst`` (string)
        fields representing the utilization percentage at each sample timestamp.

        Parameters
        ----------
        lsp_type : str
            LSP type - either ``"SR"`` (default) or ``"RSVP"``.
        peer_address : str, optional
            Head-end / peer IP address of the LSP.
        dest_address : str, optional
            Destination IP address of the LSP.
        color : str, optional
            SR policy color (used when lsp_type is ``"SR"``).
        tunnel_id : str, optional
            RSVP tunnel ID (used when lsp_type is ``"RSVP"``).
        from_time : str, optional
            Start of the query time window (ISO 8601).
        to_time : str, optional
            End of the query time window (ISO 8601).
        """
        path = "/api/v1/lsp/utilizations"

        request_body: Dict[str, Any] = {"lspType": lsp_type}
        if peer_address is not None:
            request_body["peerAddress"] = peer_address
        if dest_address is not None:
            request_body["destAddress"] = dest_address
        if color is not None:
            request_body["color"] = color
        if tunnel_id is not None:
            request_body["tunnelId"] = tunnel_id
        if from_time is not None:
            request_body["from"] = from_time
        if to_time is not None:
            request_body["to"] = to_time

        logger.info(
            "Fetching NPM LSP utilization metrics",
            lsp_type=lsp_type,
            peer_address=peer_address,
            dest_address=dest_address,
        )

        client = await self._get_client()
        url = f"{self.npm_base_url}{path}"
        # The NPM service uses standard JSON (not yang-data+json)
        npm_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            response = await client.post(
                url,
                json=request_body,
                headers=npm_headers,
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return []
            data = response.json()
            # Spec example shows the response is a list directly
            if isinstance(data, list):
                return data
            return [data]
        except httpx.HTTPStatusError as exc:
            logger.error(
                "NPM metrics request failed",
                status_code=exc.response.status_code,
                url=url,
            )
            raise
        except httpx.HTTPError as exc:
            logger.error("NPM metrics HTTP error", error=str(exc), url=url)
            raise

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client and release connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.debug("COEMetricsClient HTTP client closed")


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_coe_metrics_client: Optional[COEMetricsClient] = None


def get_coe_metrics_client(
    coe_base_url: Optional[str] = None,
    pm_base_url: Optional[str] = None,
    npm_base_url: Optional[str] = None,
    timeout: int = 30,
) -> COEMetricsClient:
    """
    Return a module-level singleton ``COEMetricsClient`` instance.

    On first call the client is constructed using the supplied arguments (or
    environment variables when arguments are omitted).  Subsequent calls
    return the cached instance regardless of the arguments passed.

    Parameters
    ----------
    coe_base_url : str, optional
        Override for the COE Operations RESTCONF base URL.
        Defaults to ``CNC_COE_URL`` env var or the built-in default.
    pm_base_url : str, optional
        Override for the Performance Metrics RESTCONF base URL.
        Defaults to ``CNC_PM_URL`` env var or the built-in default.
    npm_base_url : str, optional
        Override for the NPM Analytics base URL.
        Defaults to ``CNC_NPM_URL`` env var or the built-in default.
    timeout : int
        HTTP request timeout in seconds (default 30).
    """
    global _coe_metrics_client
    if _coe_metrics_client is None:
        _coe_metrics_client = COEMetricsClient(
            coe_base_url=coe_base_url,
            pm_base_url=pm_base_url,
            npm_base_url=npm_base_url,
            timeout=timeout,
        )
    return _coe_metrics_client
