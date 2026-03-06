"""
CNC DPM (Device Performance Monitoring) Client

Consumes interface counter TCAs (Threshold Crossing Alerts) from CNC DPM.
DPM Kafka is available in CNC today (unlike Service Health Kafka which is v8.1 roadmap).

Krishnan Thirukonda (CNC product team, 2026-03-05):
"All interface counters are constantly collected and streamed via Kafka.
 You can set thresholds and get TCAs. Use this to find which P-to-P link is dropping."
"""

import json
import os
from typing import Any, Callable, Coroutine, Dict, Optional
from datetime import datetime, timedelta, timezone

import structlog
import httpx

logger = structlog.get_logger(__name__)


class DPMKafkaConsumer:
    """
    Consumes DPM TCA (Threshold Crossing Alert) events from CNC Kafka.

    CNC DPM streams interface counters continuously. When a counter crosses
    a configured threshold, DPM publishes a TCA event to Kafka. This consumer
    listens for those events and invokes a callback with a normalized dict.

    Kafka topic schema (per message JSON):
        {
            "device_id": str,
            "interface": str,
            "metric": str,          # e.g. "packet_loss_pct", "error_rate"
            "value": float,
            "threshold": float,
            "timestamp": str,       # ISO-8601
            "link_id": str          # optional, CNC topology link_id if available
        }
    """

    def __init__(self) -> None:
        self.brokers: str = os.getenv("DPM_KAFKA_BROKERS", "kafka:9092")
        self.topic: str = os.getenv("DPM_KAFKA_TOPIC", "cnc.dpm.tca.alerts")
        self.group_id: str = os.getenv("DPM_KAFKA_GROUP_ID", "cx-ai-agent-dpm")
        self.packet_loss_threshold_pct: float = float(
            os.getenv("DPM_PACKET_LOSS_THRESHOLD_PCT", "0.1")
        )
        self._consumer = None
        self._running: bool = False

    async def start_consuming(
        self,
        callback: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        """
        Start consuming TCA events from the DPM Kafka topic.

        For each message received:
        - Parses JSON payload.
        - Filters for metrics "packet_loss_pct" or "error_rate" where value > threshold.
        - Calls callback(tca_event) with a normalized dict.

        Args:
            callback: Async callable invoked with each qualifying TCA event dict.

        Raises:
            ImportError: If aiokafka is not installed.
        """
        try:
            from aiokafka import AIOKafkaConsumer  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "aiokafka not installed. Install with: pip install aiokafka"
            ) from exc

        logger.info(
            "Starting DPM Kafka consumer",
            brokers=self.brokers,
            topic=self.topic,
            group_id=self.group_id,
        )

        self._consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self.brokers,
            group_id=self.group_id,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )

        await self._consumer.start()
        self._running = True

        try:
            async for message in self._consumer:
                if not self._running:
                    break

                msg: Dict[str, Any] = message.value

                metric: str = msg.get("metric", "")
                value: float = float(msg.get("value", 0.0))
                threshold: float = float(msg.get("threshold", 0.0))

                if metric not in ("packet_loss_pct", "error_rate"):
                    continue

                if value <= threshold:
                    continue

                link_id: str = msg.get("link_id") or (
                    f"{msg.get('device_id', 'unknown')}:{msg.get('interface', 'unknown')}"
                )

                tca_event: Dict[str, Any] = {
                    "source": "dpm_tca",
                    "link_id": link_id,
                    "device_id": msg.get("device_id"),
                    "interface": msg.get("interface"),
                    "metric": metric,
                    "value": value,
                    "threshold": threshold,
                    "timestamp": msg.get("timestamp"),
                }

                logger.info(
                    "DPM TCA received",
                    link_id=link_id,
                    metric=metric,
                    value=value,
                    threshold=threshold,
                )

                await callback(tca_event)

        finally:
            await self._consumer.stop()
            self._running = False
            logger.info("DPM Kafka consumer stopped")

    async def stop(self) -> None:
        """Stop the Kafka consumer gracefully."""
        self._running = False
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
            logger.info("DPM Kafka consumer stop requested")


class DPMRestClient:
    """
    REST polling client for CNC DPM interface counters.

    Used as a fallback when Kafka is not available or for on-demand counter
    queries. Authenticates via the same TGT -> JWT exchange pattern used by
    other CNC clients in this project.
    """

    def __init__(self) -> None:
        self.base_url: str = os.getenv(
            "CNC_DPM_URL",
            "https://cnc.example.com:30603/crosswork/dpm/v1",
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
        Obtain a JWT token via TGT exchange (same pattern as CNCTopologyClient).

        Token is cached for 8 hours with a 5-minute safety margin on renewal.
        """
        if self._jwt_token and self._jwt_expires_at:
            if datetime.now(timezone.utc) < self._jwt_expires_at - timedelta(minutes=5):
                return self._jwt_token

        client = await self._get_client()

        # Step 1: Get TGT
        logger.debug("DPMRestClient: getting TGT from CNC SSO")
        tgt_response = await client.post(
            self.auth_url,
            data={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        tgt_response.raise_for_status()
        tgt = tgt_response.text.strip()

        # Step 2: Exchange TGT for JWT
        logger.debug("DPMRestClient: exchanging TGT for JWT")
        jwt_response = await client.post(
            self.jwt_url,
            data={"tgt": tgt, "service": f"{self.base_url}/app-dashboard"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        jwt_response.raise_for_status()
        self._jwt_token = jwt_response.text.strip()
        self._jwt_expires_at = datetime.now(timezone.utc) + timedelta(hours=8)

        logger.info("DPMRestClient: JWT token obtained successfully")
        return self._jwt_token

    async def get_interface_counters(
        self,
        device_id: str,
        interface: str,
        window_minutes: int = 5,
    ) -> Dict[str, Any]:
        """
        Fetch interface counters for a specific device/interface from DPM.

        Calls GET {CNC_DPM_URL}/devices/{device_id}/interfaces/{interface}/counters
                  ?window={window_minutes}m

        Args:
            device_id: Device node ID (e.g. router hostname or loopback).
            interface: Interface name (e.g. "GigabitEthernet0/0/0/1").
            window_minutes: Aggregation window in minutes.

        Returns:
            Dict with keys: packet_loss_pct, error_rate, utilization_pct, timestamp.
            Returns {} on error.
        """
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            logger.info(
                "Fetching DPM interface counters",
                device_id=device_id,
                interface=interface,
                window_minutes=window_minutes,
            )

            response = await client.get(
                f"{self.base_url}/devices/{device_id}/interfaces/{interface}/counters",
                params={"window": f"{window_minutes}m"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            data: Dict[str, Any] = response.json()

            logger.info(
                "DPM interface counters fetched",
                device_id=device_id,
                interface=interface,
                packet_loss_pct=data.get("packet_loss_pct"),
            )
            return data

        except Exception as e:
            logger.error(
                "Failed to fetch DPM interface counters",
                device_id=device_id,
                interface=interface,
                error=str(e),
            )
            return {}

    async def get_link_counters(
        self,
        link_id: str,
        window_minutes: int = 5,
    ) -> Dict[str, Any]:
        """
        Fetch aggregated counters for a CNC topology link from DPM.

        Calls GET {CNC_DPM_URL}/links/{link_id}/counters?window={window_minutes}m

        Args:
            link_id: CNC topology link ID.
            window_minutes: Aggregation window in minutes.

        Returns:
            Dict with keys: packet_loss_pct, error_rate, utilization_pct, timestamp.
            Returns {} on error.
        """
        try:
            client = await self._get_client()
            token = await self._get_jwt_token()

            logger.info(
                "Fetching DPM link counters",
                link_id=link_id,
                window_minutes=window_minutes,
            )

            response = await client.get(
                f"{self.base_url}/links/{link_id}/counters",
                params={"window": f"{window_minutes}m"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/yang-data+json",
                },
            )
            response.raise_for_status()
            data: Dict[str, Any] = response.json()

            logger.info(
                "DPM link counters fetched",
                link_id=link_id,
                packet_loss_pct=data.get("packet_loss_pct"),
            )
            return data

        except Exception as e:
            logger.error(
                "Failed to fetch DPM link counters",
                link_id=link_id,
                error=str(e),
            )
            return {}

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Module-level singleton
_dpm_rest_client: Optional[DPMRestClient] = None


def get_dpm_rest_client() -> DPMRestClient:
    """Get singleton DPMRestClient instance."""
    global _dpm_rest_client
    if _dpm_rest_client is None:
        _dpm_rest_client = DPMRestClient()
    return _dpm_rest_client
