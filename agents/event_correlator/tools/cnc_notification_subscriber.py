"""
CNC Notification Event Stream Subscriber

Subscribes to CNC Service Health notification stream and forwards
degradation alerts to the Event Correlator workflow via A2A.

Based on Krishnan Thirukonda's (CNC product team) guidance:
- Authenticate via JWT (TGT → JWT exchange)
- Subscribe to notification event stream endpoint
- Parse symptom_list from service health notifications
- Forward to event_correlator A2A for processing

CNC v8.0: GRPC notification (not yet implemented here)
CNC v8.1: Kafka for Service Health (roadmap)
"""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class CNCNotificationSubscriber:
    """
    Subscriber for CNC Service Health notification event stream (SSE).

    Connects to CNC's SSE endpoint, authenticates via JWT (TGT→JWT exchange),
    and forwards degradation events to the Event Correlator A2A endpoint.

    Environment variables:
        CNC_NOTIFICATION_URL: SSE stream endpoint URL
        CNC_AUTH_URL: CNC SSO TGT endpoint
        CNC_JWT_URL: CNC JWT exchange endpoint
        CNC_USERNAME: CNC login username
        CNC_PASSWORD: CNC login password
        EVENT_CORRELATOR_URL: Base URL of this agent's A2A server
        NOTIFICATION_RECONNECT_DELAY: Seconds to wait between reconnect attempts
    """

    def __init__(self) -> None:
        # CNC notification stream endpoint
        self.notification_url: str = os.getenv(
            "CNC_NOTIFICATION_URL",
            "https://cnc.example.com:30603/crosswork/nbi/servicehealth/v1/notifications/stream",
        )

        # CNC authentication endpoints (same as CNCServiceHealthClient)
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

        # Event Correlator A2A endpoint to forward alerts to
        self.event_correlator_url: str = os.getenv(
            "EVENT_CORRELATOR_URL",
            "http://event-correlator:8001",
        )

        # Seconds to sleep between reconnect attempts on error or disconnect
        self.reconnect_delay: int = int(os.getenv("NOTIFICATION_RECONNECT_DELAY", "30"))

        # JWT token cache
        self._jwt_token: Optional[str] = None
        self._jwt_expires_at: Optional[datetime] = None

        # Shared httpx client (no timeout for the streaming connection)
        ca_cert = os.getenv("CA_CERT_PATH")
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            timeout=httpx.Timeout(None),
            verify=ca_cert if ca_cert else True,
        )

    async def _get_jwt_token(self) -> str:
        """
        Obtain a JWT token via TGT→JWT exchange, reusing a cached token when
        it still has more than 5 minutes of remaining validity.

        Mirrors the same authentication flow used by CNCServiceHealthClient.
        """
        if self._jwt_token and self._jwt_expires_at:
            if datetime.now(timezone.utc) < self._jwt_expires_at - timedelta(minutes=5):
                return self._jwt_token

        logger.debug("Getting TGT from CNC SSO", auth_url=self.auth_url)
        tgt_response = await self._client.post(
            self.auth_url,
            data={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        tgt_response.raise_for_status()
        tgt = tgt_response.text.strip()

        logger.debug("Exchanging TGT for JWT", jwt_url=self.jwt_url)
        jwt_response = await self._client.post(
            self.jwt_url,
            data={
                "tgt": tgt,
                "service": f"{self.notification_url}/app-dashboard",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        jwt_response.raise_for_status()
        self._jwt_token = jwt_response.text.strip()
        self._jwt_expires_at = datetime.now(timezone.utc) + timedelta(hours=8)

        logger.info("CNC JWT token obtained")
        return self._jwt_token

    @staticmethod
    def _infer_severity(symptom_list: list) -> str:
        """
        Infer alert severity from the CNC symptom list.

        Rules (first match wins):
            - Any symptom string containing "critical" → "critical"
            - Any symptom string containing "major"    → "major"
            - Otherwise                                → "minor"

        Args:
            symptom_list: List of symptom strings from the CNC notification.

        Returns:
            One of "critical", "major", or "minor".
        """
        lowered = [str(s).lower() for s in symptom_list]
        for symptom in lowered:
            if "critical" in symptom:
                return "critical"
        for symptom in lowered:
            if "major" in symptom:
                return "major"
        return "minor"

    async def _forward_alert(self, event: dict) -> None:
        """
        Build an A2A payload from a CNC notification event and POST it to
        the Event Correlator's /a2a/tasks endpoint.

        Args:
            event: Parsed JSON dict from a CNC SSE data line.
        """
        service_id: str = event.get("service_id", "unknown")
        name: str = event.get("name", "unknown")
        symptom_list: list = event.get("symptom_list", [])
        alert_type: str = event.get("type", "unknown")
        severity: str = self._infer_severity(symptom_list)

        a2a_payload = {
            "task_type": "correlate_alert",
            "payload": {
                "alert_source": "cnc",
                "raw_alert": {
                    "resource_id": service_id,
                    "service_name": name,
                    "symptom_list": symptom_list,
                    "alert_type": alert_type,
                    "severity": severity,
                },
            },
        }

        target_url = f"{self.event_correlator_url}/a2a/tasks"
        try:
            # Use a short-timeout client for the forwarding POST so it does
            # not block the SSE read loop indefinitely.
            async with httpx.AsyncClient(timeout=10.0) as post_client:
                response = await post_client.post(target_url, json=a2a_payload)
                response.raise_for_status()
                logger.info(
                    "CNC alert forwarded to Event Correlator",
                    service_id=service_id,
                    service_name=name,
                    severity=severity,
                    alert_type=alert_type,
                    status_code=response.status_code,
                )
        except Exception as exc:
            logger.warning(
                "Failed to forward CNC alert to Event Correlator",
                service_id=service_id,
                error=str(exc),
                target_url=target_url,
            )

    async def subscribe_and_forward(self) -> None:
        """
        Open the CNC SSE notification stream and forward qualifying events.

        Loop steps:
        1. Obtain a JWT token.
        2. Issue a streaming GET to CNC_NOTIFICATION_URL.
        3. Iterate over response lines; lines beginning with "data:" carry a
           JSON payload.
        4. For each event whose type contains "degraded", or whose
           symptom_list contains "violation", build an A2A payload and POST
           it to the Event Correlator.
        5. On any connection error or disconnect, log a warning and re-raise
           so that `start()` can apply the reconnect delay.
        """
        token = await self._get_jwt_token()

        logger.info(
            "Opening CNC notification stream",
            url=self.notification_url,
        )

        async with self._client.stream(
            "GET",
            self.notification_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "text/event-stream",
            },
        ) as response:
            response.raise_for_status()
            logger.info(
                "Connected to CNC notification stream",
                url=self.notification_url,
                status_code=response.status_code,
            )

            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    # SSE lines that do not carry data (comments, event:,
                    # retry:, blank keep-alive lines) are silently skipped.
                    continue

                raw_json = line[len("data:"):].strip()
                if not raw_json:
                    continue

                try:
                    event = json.loads(raw_json)
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "Failed to parse CNC SSE data line",
                        raw=raw_json[:200],
                        error=str(exc),
                    )
                    continue

                event_type: str = event.get("type", "")
                symptom_list: list = event.get("symptom_list", [])
                symptoms_lower = [str(s).lower() for s in symptom_list]

                is_degraded = "degraded" in event_type.lower()
                has_violation = any("violation" in s for s in symptoms_lower)

                if is_degraded or has_violation:
                    logger.debug(
                        "Qualifying CNC notification received",
                        event_type=event_type,
                        service_id=event.get("service_id"),
                        symptom_count=len(symptom_list),
                    )
                    await self._forward_alert(event)
                else:
                    logger.debug(
                        "Skipping non-degradation CNC notification",
                        event_type=event_type,
                        service_id=event.get("service_id"),
                    )

    async def start(self) -> None:
        """
        Run subscribe_and_forward() in a perpetual reconnect loop.

        On any exception (connection error, HTTP error, disconnect, or
        unexpected error) the subscriber waits NOTIFICATION_RECONNECT_DELAY
        seconds before retrying, so the pipeline is self-healing.
        """
        logger.info(
            "CNC notification subscriber starting",
            notification_url=self.notification_url,
            event_correlator_url=self.event_correlator_url,
            reconnect_delay=self.reconnect_delay,
        )

        while True:
            try:
                await self.subscribe_and_forward()
                # subscribe_and_forward() only returns when the stream ends
                # gracefully — treat it as a disconnect and reconnect.
                logger.warning(
                    "CNC notification stream ended gracefully; reconnecting",
                    delay=self.reconnect_delay,
                )
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "CNC notification stream HTTP error; reconnecting",
                    status_code=exc.response.status_code,
                    delay=self.reconnect_delay,
                    error=str(exc),
                )
            except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError) as exc:
                logger.warning(
                    "CNC notification stream connection error; reconnecting",
                    delay=self.reconnect_delay,
                    error=str(exc),
                )
            except Exception as exc:
                logger.warning(
                    "Unexpected error in CNC notification subscriber; reconnecting",
                    delay=self.reconnect_delay,
                    error=str(exc),
                )

            await asyncio.sleep(self.reconnect_delay)

    async def close(self) -> None:
        """
        Close the shared httpx client, releasing any open connections.

        Call this when the application is shutting down.
        """
        await self._client.aclose()
        logger.info("CNC notification subscriber closed")


async def run_subscriber() -> None:
    """
    Module-level convenience coroutine.

    Creates a CNCNotificationSubscriber and runs it until cancelled.
    Ensures the client is closed on exit.

    Usage::

        asyncio.run(run_subscriber())
    """
    subscriber = CNCNotificationSubscriber()
    try:
        await subscriber.start()
    finally:
        await subscriber.close()
