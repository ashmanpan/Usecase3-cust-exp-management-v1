"""
Service Health Client - Historical Data, Assurance Graph, and Probe Manager APIs

Implements three Crosswork Service Health API groups:

1. Historical Data API  (base: /crosswork/aa/aaapp/v1/)
   - POST /historicalmetrics     - Metrics at a point in time
   - POST /historicalservice     - Service assurance graph at a point in time
   - POST /historicaltimeline    - Timeline of health events over N days
   - POST /dashboard/metrics     - Dashboard service count / health summary
   - POST /dashboard/sla         - Dashboard SLA breach report
   - POST /historicaldatacheck   - Check if historical archive data exists

2. Assurance Graph API  (base: /crosswork/aa/agmgr/v1/)
   - POST /impactedServices      - Given a subservice-id, return parent services
   - POST /matchingSubservices   - Return subservices matching criteria (type/tags)
   - POST /serviceDetails        - Full assurance graph for a service

3. Probe Manager API  (base: /crosswork/probemgr/v1/)
   - POST /probeStatusReport     - Probe status for a service
   - POST /reactivateProbe       - Reactivate a probe that is in error state

Authentication uses the same two-step TGT → JWT flow as other CNC clients:
  Step 1: POST CNC_AUTH_URL  (form-encoded username/password) → TGT string
  Step 2: POST CNC_JWT_URL   (form-encoded tgt=<TGT>)        → JWT string

The Service Health APIs live on a dedicated port/prefix separate from other
CNC APIs.  Configure via:
  CNC_SH_URL     Service Health base URL
                 default: https://cnc.example.com:30603/crosswork/health-insights/v1
  CNC_AUTH_URL   SSO ticket URL  (shared with other CNC clients)
  CNC_JWT_URL    JWT exchange URL (shared with other CNC clients)
  CNC_USERNAME   CNC username
  CNC_PASSWORD   CNC password
  CA_CERT_PATH   Path to CA certificate bundle for TLS verification (optional)

API spec versions: Crosswork Service Health 7.1.0
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

# -------------------------------------------------------------------
# Sub-path prefixes as declared in the OpenAPI specs' `servers` fields
# These are appended to CNC_SH_URL.
# -------------------------------------------------------------------
_HISTORICAL_DATA_PREFIX = "/crosswork/aa/aaapp/v1"
_ASSURANCE_GRAPH_PREFIX = "/crosswork/aa/agmgr/v1"
_PROBE_MANAGER_PREFIX = "/crosswork/probemgr/v1"

_DEFAULT_SH_BASE_URL = "https://cnc.example.com:30603"
_DEFAULT_AUTH_URL = "https://cnc.example.com:30603/crosswork/sso/v1/tickets"
_DEFAULT_JWT_URL = "https://cnc.example.com:30603/crosswork/sso/v2/tickets/jwt"


class ServiceHealthClient:
    """
    Async HTTP client for the Crosswork Service Health APIs.

    Covers three API groups:
      - Historical Data  (/crosswork/aa/aaapp/v1/)
      - Assurance Graph  (/crosswork/aa/agmgr/v1/)
      - Probe Manager    (/crosswork/probemgr/v1/)

    All API groups share the same JWT authentication credentials but have
    different URL prefixes under the Service Health base URL.

    Usage::

        client = ServiceHealthClient()
        services = await client.get_impacted_services(["ss-418316d7-..."])
        await client.close()

    Or use the module-level singleton::

        from agents.restoration_monitor.tools import get_service_health_client
        client = get_service_health_client()
        services = await client.get_impacted_services(["ss-..."])
    """

    def __init__(
        self,
        sh_base_url: Optional[str] = None,
        auth_url: Optional[str] = None,
        jwt_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        """
        Initialise the Service Health client.

        Args:
            sh_base_url: Base URL for Service Health APIs.
                         Env: CNC_SH_URL
                         Default: https://cnc.example.com:30603
            auth_url:    CNC SSO ticket endpoint for TGT acquisition.
                         Env: CNC_AUTH_URL
            jwt_url:     CNC JWT exchange endpoint.
                         Env: CNC_JWT_URL
            username:    CNC login username.  Env: CNC_USERNAME
            password:    CNC login password.  Env: CNC_PASSWORD
            timeout:     Per-request timeout in seconds.
        """
        self._sh_base = (sh_base_url or os.getenv("CNC_SH_URL", _DEFAULT_SH_BASE_URL)).rstrip("/")

        self._historical_url = self._sh_base + _HISTORICAL_DATA_PREFIX
        self._assurance_url = self._sh_base + _ASSURANCE_GRAPH_PREFIX
        self._probe_url = self._sh_base + _PROBE_MANAGER_PREFIX

        self.auth_url = auth_url or os.getenv("CNC_AUTH_URL", _DEFAULT_AUTH_URL)
        self.jwt_url = jwt_url or os.getenv("CNC_JWT_URL", _DEFAULT_JWT_URL)
        self.username = username or os.getenv("CNC_USERNAME", "admin")
        self.password = password or os.getenv("CNC_PASSWORD", "")
        self.timeout = timeout

        self._jwt_token: Optional[str] = None
        self._jwt_expires_at: Optional[datetime] = None
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        """Return (creating if necessary) the shared async HTTP client."""
        if self._client is None or self._client.is_closed:
            ca_cert = os.getenv("CA_CERT_PATH")
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                verify=ca_cert if ca_cert else True,
            )
        return self._client

    async def _get_jwt_token(self) -> str:
        """
        Obtain a valid JWT token, refreshing when within 5 minutes of expiry.

        Two-step flow:
          1. POST CNC_AUTH_URL with form-encoded credentials → TGT string
          2. POST CNC_JWT_URL with form-encoded tgt → JWT string

        The token is cached and reused for up to 8 hours (CNC default expiry).
        """
        if self._jwt_token and self._jwt_expires_at:
            if datetime.now(timezone.utc) < self._jwt_expires_at - timedelta(minutes=5):
                return self._jwt_token

        client = await self._get_client()

        try:
            # Step 1: acquire TGT
            logger.debug("Acquiring TGT from CNC SSO", auth_url=self.auth_url)
            tgt_response = await client.post(
                self.auth_url,
                data={"username": self.username, "password": self.password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            tgt_response.raise_for_status()
            tgt = tgt_response.text.strip()

            # Step 2: exchange TGT for JWT
            logger.debug("Exchanging TGT for JWT", jwt_url=self.jwt_url)
            jwt_response = await client.post(
                self.jwt_url,
                data={"tgt": tgt, "service": f"{self._sh_base}/app-dashboard"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            jwt_response.raise_for_status()
            self._jwt_token = jwt_response.text.strip()
            self._jwt_expires_at = datetime.now(timezone.utc) + timedelta(hours=8)

            logger.info("JWT token obtained successfully")
            return self._jwt_token

        except httpx.HTTPError as exc:
            logger.error("Failed to obtain JWT token", error=str(exc))
            raise

    def _auth_headers(self, token: str) -> Dict[str, str]:
        """Return standard JSON + Bearer auth headers."""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _post(self, url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an authenticated POST request and return the parsed JSON body.

        Args:
            url:  Full endpoint URL.
            body: Request payload dict (will be JSON-serialised).

        Returns:
            Parsed JSON response dict, or empty dict on error.

        Raises:
            httpx.HTTPStatusError: on non-2xx responses (caller decides handling).
        """
        client = await self._get_client()
        token = await self._get_jwt_token()
        response = await client.post(url, json=body, headers=self._auth_headers(token))
        response.raise_for_status()
        return response.json()

    # ==================================================================
    # Historical Data API  (/crosswork/aa/aaapp/v1/)
    # Spec: api_specs/sh_historical_data.json  — version 7.1.0
    # ==================================================================

    async def get_historical_metrics(
        self,
        service_id: str,
        start_time: int,
        end_time: int,
        metric_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve historical metric data for a service at a point in time.

        Spec: POST /historicalmetrics
        Request schema: HistoricalMetricsRequest
          - serviceId       (string) Service identifier
          - eventTimestamp  (string/int) Nanosecond epoch timestamp of event
          - serviceType     (string, optional)
          - vpnNodeIds      (list,   optional) Filter by device IDs

        Args:
            service_id:   Full CNC service identifier string, e.g.
                          "ietf-l2vpn-ntw:l2vpn-ntw/vpn-services/vpn-service=l2nm-evpn-01"
            start_time:   Event timestamp in nanosecond epoch (maps to eventTimestamp).
            end_time:     Unused by this endpoint — included for API signature consistency.
                          Pass the event timestamp of interest as ``start_time``.
            metric_types: Optional list of metric type labels to filter results.
                          If None, all available metrics are returned.

        Returns:
            Parsed response dict.  On success the top-level key is ``data``,
            containing a list of metric records keyed by metric label.

        Example::

            data = await client.get_historical_metrics(
                service_id="ietf-l2vpn-ntw:l2vpn-ntw/vpn-services/vpn-service=svc-01",
                start_time=1627431358591140095,
                end_time=1627431358591140095,
            )
        """
        body: Dict[str, Any] = {
            "service_id": service_id,
            "event_timestamp": start_time,
        }
        if metric_types:
            body["metric_types"] = metric_types

        endpoint = f"{self._historical_url}/historicalmetrics"
        logger.info(
            "Fetching historical metrics",
            service_id=service_id,
            event_timestamp=start_time,
            endpoint=endpoint,
        )

        try:
            return await self._post(endpoint, body)
        except httpx.HTTPError as exc:
            logger.error(
                "Historical metrics request failed",
                service_id=service_id,
                error=str(exc),
            )
            return {}

    async def get_historical_service(
        self,
        service_id: str,
        start_time: int,
        end_time: int,
    ) -> Dict[str, Any]:
        """
        Retrieve the historical assurance graph and health report for a service.

        Spec: POST /historicalservice
        Request schema: HistoricalServiceRequest
          - serviceId      (string) Service identifier
          - eosTimestamp   (string/int) End-of-service timestamp in nanosecond epoch

        Returns the service assurance graph and health report as they were at
        the given timestamp — useful for post-incident analysis.

        Args:
            service_id: Full CNC service identifier string.
            start_time: EOS (end-of-service) timestamp in nanosecond epoch.
            end_time:   Unused by this endpoint; included for signature consistency.

        Returns:
            Parsed response dict.  On success ``data[0]`` contains:
            ``assurance_graph``, ``health_report``, ``rootSubservices``, etc.
        """
        body: Dict[str, Any] = {
            "service_id": service_id,
            "eos_timestamp": start_time,
        }

        endpoint = f"{self._historical_url}/historicalservice"
        logger.info(
            "Fetching historical service graph",
            service_id=service_id,
            eos_timestamp=start_time,
            endpoint=endpoint,
        )

        try:
            return await self._post(endpoint, body)
        except httpx.HTTPError as exc:
            logger.error(
                "Historical service request failed",
                service_id=service_id,
                error=str(exc),
            )
            return {}

    async def get_historical_timeline(
        self,
        service_id: str,
        start_time: int,
        end_time: int,
    ) -> Dict[str, Any]:
        """
        Retrieve a timeline of health events for a service over a date range.

        Spec: POST /historicaltimeline
        Request schema: HistoricalServiceRequest
          - serviceId   (string)  Service identifier
          - numOfDays   (integer) Duration in days to look back
          - vpnNodeIds  (list)    Optional device-ID filter

        Args:
            service_id: Full CNC service identifier string.
            start_time: Unused directly; the API uses ``num_of_days`` instead.
                        The days are computed from (end_time - start_time) //
                        86_400_000_000_000 (nanosecond epoch difference).
                        Defaults to 7 days when the difference is zero.
            end_time:   End of the window in nanosecond epoch.  Used together
                        with ``start_time`` to derive ``num_of_days``.

        Returns:
            Parsed response dict.  On success ``data[0]["time_line_events"]``
            is a list of ``{event_timestamp, service_status, symptoms}`` dicts.
        """
        # Derive num_of_days from the time window; fall back to 7.
        if end_time > start_time:
            num_of_days = max(1, (end_time - start_time) // 86_400_000_000_000)
        else:
            num_of_days = 7

        body: Dict[str, Any] = {
            "service_id": service_id,
            "num_of_days": num_of_days,
            "vpn_node_ids": [],
        }

        endpoint = f"{self._historical_url}/historicaltimeline"
        logger.info(
            "Fetching historical timeline",
            service_id=service_id,
            num_of_days=num_of_days,
            endpoint=endpoint,
        )

        try:
            return await self._post(endpoint, body)
        except httpx.HTTPError as exc:
            logger.error(
                "Historical timeline request failed",
                service_id=service_id,
                error=str(exc),
            )
            return {}

    async def get_dashboard_metrics(
        self,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve dashboard-level service count and health-state summary.

        Spec: POST /dashboard/metrics
        Request schema: DashboardRequest
          - serviceType (string, optional) Filter by service type, e.g. "L3VPN"

        Args:
            filters: Optional dict of filter keys.  Recognised key:
                     ``service_type`` (str) — maps to the ``serviceType`` field.

        Returns:
            Parsed response dict.  On success ``data[0]["servicesCount"]`` is a
            list of per-type summaries with ``totalCount`` and ``healthState``.
        """
        body: Dict[str, Any] = {}
        if filters:
            if "service_type" in filters:
                body["service_type"] = filters["service_type"]

        endpoint = f"{self._historical_url}/dashboard/metrics"
        logger.info("Fetching dashboard metrics", filters=filters, endpoint=endpoint)

        try:
            return await self._post(endpoint, body)
        except httpx.HTTPError as exc:
            logger.error("Dashboard metrics request failed", error=str(exc))
            return {}

    async def get_dashboard_sla(
        self,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve dashboard-level SLA breach report.

        Spec: POST /dashboard/sla
        Request schema: DashboardRequest
          - serviceType (string, optional) e.g. "L3VPN" or "L2VPN"

        Args:
            filters: Optional dict.  Recognised key:
                     ``service_type`` (str) — maps to ``serviceType``.

        Returns:
            Parsed response dict.  On success ``data[0]["serviceBreach"]`` lists
            per-service breach counts for delay, variance, and loss metrics.
        """
        body: Dict[str, Any] = {}
        if filters:
            if "service_type" in filters:
                body["service_type"] = filters["service_type"]

        endpoint = f"{self._historical_url}/dashboard/sla"
        logger.info("Fetching dashboard SLA report", filters=filters, endpoint=endpoint)

        try:
            return await self._post(endpoint, body)
        except httpx.HTTPError as exc:
            logger.error("Dashboard SLA request failed", error=str(exc))
            return {}

    async def check_historical_data_exists(self, service_id: str) -> Dict[str, Any]:
        """
        Check whether historical archive data exists for a service.

        Spec: POST /historicaldatacheck
        Request schema: HistoricalServiceRequest
          - serviceId  (string)  Service identifier
          - numOfDays  (integer) Look-back window in days (default: 1)

        Args:
            service_id: Full CNC service identifier string.

        Returns:
            Parsed response dict.  On success ``data[0]["archive_data_exists"]``
            is a boolean indicating whether historical data is available.
        """
        body: Dict[str, Any] = {
            "service_id": service_id,
            "num_of_days": 1,
        }

        endpoint = f"{self._historical_url}/historicaldatacheck"
        logger.info(
            "Checking historical data existence",
            service_id=service_id,
            endpoint=endpoint,
        )

        try:
            return await self._post(endpoint, body)
        except httpx.HTTPError as exc:
            logger.error(
                "Historical data check failed",
                service_id=service_id,
                error=str(exc),
            )
            return {}

    # ==================================================================
    # Assurance Graph API  (/crosswork/aa/agmgr/v1/)
    # Spec: api_specs/sh_assurance_graph.json  — version 7.1.0
    # ==================================================================

    async def get_impacted_services(
        self,
        transport_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Determine which VPN services are impacted by one or more failed transport links.

        This is the primary method used by the restoration_monitor agent to map
        a set of failed transport link subservice IDs to the parent VPN services
        that traverse them.

        Spec: POST /impactedServices
        Request schema: RequestImpactedServices
          - subservice_id (string) Subservice UUID — the subservice node in the
                          assurance graph that represents the transport link or
                          its monitoring probe session.

        The method calls the endpoint once per transport_id and aggregates the
        results, deduplicating by ``serviceId``.

        Args:
            transport_ids: List of subservice IDs (UUIDs prefixed with "ss-").
                           Typically obtained from the assurance graph after a
                           transport-link failure event.  Example:
                           ["ss-418316d7-fea9-4249-a476-333a658e6cb6"]

        Returns:
            Deduplicated list of service detail dicts, each containing:
              - ``serviceId``   (str)  Full CNC service identifier
              - ``serviceType`` (str)  e.g. "L3VPN", "L2VPN"
              - ``serviceName`` (str)  Human-readable service name

            Returns an empty list on error or when no services are found.

        Example::

            services = await client.get_impacted_services(
                ["ss-418316d7-fea9-4249-a476-333a658e6cb6"]
            )
            for svc in services:
                print(svc["serviceId"], svc["serviceType"])
        """
        endpoint = f"{self._assurance_url}/impactedServices"
        seen_ids: set = set()
        all_services: List[Dict[str, Any]] = []

        for subservice_id in transport_ids:
            body: Dict[str, Any] = {"subservice_id": subservice_id}
            logger.info(
                "Querying impacted services",
                subservice_id=subservice_id,
                endpoint=endpoint,
            )

            try:
                response = await self._post(endpoint, body)

                # Response schema: ResponseImpactedServices
                # { "status": ..., "services": [ {serviceId, serviceType, serviceName}, ... ], "error": "" }
                services = response.get("services", [])
                error_msg = response.get("error", "")

                if error_msg:
                    logger.warning(
                        "Impacted services response contains error",
                        subservice_id=subservice_id,
                        api_error=error_msg,
                    )

                for svc in services:
                    svc_id = svc.get("serviceId", "")
                    if svc_id and svc_id not in seen_ids:
                        seen_ids.add(svc_id)
                        all_services.append(svc)

                logger.info(
                    "Impacted services retrieved",
                    subservice_id=subservice_id,
                    count=len(services),
                )

            except httpx.HTTPError as exc:
                logger.error(
                    "Impacted services request failed",
                    subservice_id=subservice_id,
                    error=str(exc),
                )
                # Continue processing remaining transport IDs.

        logger.info(
            "Impacted services aggregation complete",
            transport_count=len(transport_ids),
            total_impacted_services=len(all_services),
        )
        return all_services

    async def get_matching_subservices(self, service_id: str) -> Dict[str, Any]:
        """
        Retrieve subservices matching a given service, optionally filtered by type or tags.

        Spec: POST /matchingSubservices
        Request schema: RequestSubservices
          - service_id (string)  Parent service identifier
          - type       (string)  Subservice type, e.g. "TAGGED_SUBSERVICES"
          - tags       (list)    Tag filter, e.g. ["PROBE_SESSION"]

        This method defaults to requesting ``TAGGED_SUBSERVICES`` with the
        ``PROBE_SESSION`` tag — the most relevant set for the restoration_monitor
        which needs to identify which probe sessions to check or reactivate.

        Args:
            service_id: Full CNC service identifier string.

        Returns:
            Parsed response dict.  On success ``subservices`` is a list of
            subservice node detail dicts.
        """
        body: Dict[str, Any] = {
            "service_id": service_id,
            "type": "TAGGED_SUBSERVICES",
            "tags": ["PROBE_SESSION"],
        }

        endpoint = f"{self._assurance_url}/matchingSubservices"
        logger.info(
            "Fetching matching subservices",
            service_id=service_id,
            endpoint=endpoint,
        )

        try:
            return await self._post(endpoint, body)
        except httpx.HTTPError as exc:
            logger.error(
                "Matching subservices request failed",
                service_id=service_id,
                error=str(exc),
            )
            return {}

    async def get_service_details(self, service_id: str) -> Dict[str, Any]:
        """
        Retrieve the full assurance graph and health report for a service.

        Spec: POST /serviceDetails
        Request schema: AssuranceReportRequest
          - service_id          (string)  Service identifier
          - degraded_paths_only (boolean) When True, only degraded/down paths returned
          - vpn_node_ids        (list)    Optional device-ID filter

        Args:
            service_id: Full CNC service identifier string.

        Returns:
            Parsed response dict (``assuranceReportResponse`` schema) containing:
              - ``serviceId``
              - ``status``           (health status enum)
              - ``assuranceGraph``   (subservice dependency graph)
              - ``healthReport``     (live metric feeds and health scores)
              - ``rootSubservices``  (list of root subservice IDs)
        """
        body: Dict[str, Any] = {
            "service_id": service_id,
            "degraded_paths_only": False,
            "vpn_node_ids": [],
        }

        endpoint = f"{self._assurance_url}/serviceDetails"
        logger.info(
            "Fetching service assurance details",
            service_id=service_id,
            endpoint=endpoint,
        )

        try:
            return await self._post(endpoint, body)
        except httpx.HTTPError as exc:
            logger.error(
                "Service details request failed",
                service_id=service_id,
                error=str(exc),
            )
            return {}

    # ==================================================================
    # Probe Manager API  (/crosswork/probemgr/v1/)
    # Spec: api_specs/sh_probe_manager.json  — version 7.1.0
    # ==================================================================

    async def get_probe_status(
        self,
        service_id: Optional[str] = None,
        probe_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve detailed probe status for a service.

        Spec: POST /probeStatusReport
        Request schema: ProbeStatusRequest
          - serviceId (string) Service identifier

        At least one of ``service_id`` or ``probe_id`` must be provided.
        The API accepts a ``serviceId`` — when only ``probe_id`` is given it is
        passed as the service identifier for look-up compatibility.

        Args:
            service_id: Full CNC service identifier string, e.g.
                        "ietf-l3vpn-ntw:l3vpn-ntw/vpn-services/vpn-service=L3VPN_5EP_10"
            probe_id:   Probe identifier.  Used as ``serviceId`` fallback when
                        ``service_id`` is not provided.

        Returns:
            Parsed response dict.  On success ``data`` is a list of
            ``ProbeStatusResponse`` objects, each with:
              - ``serviceId``        (str)
              - ``enableReactivate`` (bool) True when probe needs reactivation
              - ``status``           (ProbeStatus enum string)
              - ``endpointStatus``   (list of endpoint probe statuses)
              - ``sessionStatus``    (list of session statuses)

        Raises:
            ValueError: if neither ``service_id`` nor ``probe_id`` is provided.
        """
        lookup_id = service_id or probe_id
        if not lookup_id:
            raise ValueError("At least one of service_id or probe_id must be provided")

        body: Dict[str, Any] = {"serviceId": lookup_id}

        endpoint = f"{self._probe_url}/probeStatusReport"
        logger.info(
            "Fetching probe status",
            service_id=lookup_id,
            endpoint=endpoint,
        )

        try:
            return await self._post(endpoint, body)
        except httpx.HTTPError as exc:
            logger.error(
                "Probe status request failed",
                service_id=lookup_id,
                error=str(exc),
            )
            return {}

    async def reactivate_probe(self, probe_id: str, service_id: str) -> Dict[str, Any]:
        """
        Reactivate a probe that is in an error state.

        Spec: POST /reactivateProbe
        Request schema: ProbeReactivateRequest
          - serviceId (string) Service identifier whose probe should be reactivated

        After a network restoration event, probes may enter an error state.
        This method reactivates them so that SLA monitoring resumes.

        Args:
            probe_id:   Probe identifier (for logging context).
            service_id: Full CNC service identifier string.  This is the field
                        the API actually uses; ``probe_id`` is retained in the
                        method signature to match the restoration_monitor calling
                        convention.

        Returns:
            Parsed response dict.  On success ``data[0]["status"]`` is one of:
              - ``"RESP_STATUS_SUCCESS"``
              - ``"RESP_STATUS_ERROR"``
              - ``"RESP_STATUS_UNKNOWN"``

        Example::

            result = await client.reactivate_probe(
                probe_id="probe-abc123",
                service_id="ietf-l3vpn-ntw:l3vpn-ntw/vpn-services/vpn-service=L3VPN_5EP_10",
            )
            if result.get("data", [{}])[0].get("status") == "RESP_STATUS_SUCCESS":
                print("Probe reactivated")
        """
        body: Dict[str, Any] = {"serviceId": service_id}

        endpoint = f"{self._probe_url}/reactivateProbe"
        logger.info(
            "Reactivating probe",
            probe_id=probe_id,
            service_id=service_id,
            endpoint=endpoint,
        )

        try:
            response = await self._post(endpoint, body)
            status = response.get("data", [{}])[0].get("status", "RESP_STATUS_UNKNOWN") \
                if isinstance(response.get("data"), list) else response.get("status", "RESP_STATUS_UNKNOWN")
            logger.info(
                "Probe reactivation response received",
                probe_id=probe_id,
                service_id=service_id,
                reactivation_status=status,
            )
            return response
        except httpx.HTTPError as exc:
            logger.error(
                "Probe reactivation request failed",
                probe_id=probe_id,
                service_id=service_id,
                error=str(exc),
            )
            return {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client and clear the cached JWT token."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
        self._jwt_token = None
        self._jwt_expires_at = None
        logger.debug("ServiceHealthClient closed")


# ----------------------------------------------------------------------
# Module-level singleton factory
# ----------------------------------------------------------------------

_service_health_client: Optional[ServiceHealthClient] = None


def get_service_health_client(
    sh_base_url: Optional[str] = None,
    auth_url: Optional[str] = None,
    jwt_url: Optional[str] = None,
) -> ServiceHealthClient:
    """
    Return the module-level singleton ``ServiceHealthClient``.

    The client is created on first call using environment variables
    (``CNC_SH_URL``, ``CNC_AUTH_URL``, ``CNC_JWT_URL``, ``CNC_USERNAME``,
    ``CNC_PASSWORD``) or the provided keyword arguments.  Subsequent calls
    return the cached instance regardless of the arguments passed.

    Args:
        sh_base_url: Override for the Service Health base URL.
        auth_url:    Override for the CNC SSO auth URL.
        jwt_url:     Override for the CNC JWT exchange URL.

    Returns:
        Singleton ``ServiceHealthClient`` instance.
    """
    global _service_health_client
    if _service_health_client is None:
        _service_health_client = ServiceHealthClient(
            sh_base_url=sh_base_url,
            auth_url=auth_url,
            jwt_url=jwt_url,
        )
    return _service_health_client
