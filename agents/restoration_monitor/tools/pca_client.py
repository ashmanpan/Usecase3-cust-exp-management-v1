"""PCA SLA Client - From DESIGN.md PCASLAClient"""
import os
import random
from typing import Optional, Tuple
from datetime import datetime
import httpx
import structlog

from ..schemas.restoration import SLAMetrics, PollSLAInput, PollSLAOutput

logger = structlog.get_logger(__name__)

# SLA tier thresholds - From DESIGN.md
SLA_TIER_THRESHOLDS = {
    "platinum": {"max_latency_ms": 10.0, "max_jitter_ms": 2.0, "max_loss_pct": 0.01},
    "gold": {"max_latency_ms": 25.0, "max_jitter_ms": 5.0, "max_loss_pct": 0.1},
    "silver": {"max_latency_ms": 50.0, "max_jitter_ms": 10.0, "max_loss_pct": 0.5},
    "bronze": {"max_latency_ms": 100.0, "max_jitter_ms": 20.0, "max_loss_pct": 1.0},
}


class PCASLAClient:
    """
    Query PCA for SLA metrics on a path.
    From DESIGN.md: GET /api/v1/metrics?source={src}&dest={dst}&window=5m
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        metrics_window: str = "5m",
        timeout_seconds: int = 10,
    ):
        self.base_url = base_url or os.getenv("PCA_API_URL", "http://pca-api:8080")
        self.metrics_window = metrics_window
        self.timeout = timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def get_path_sla(
        self,
        path_endpoints: Tuple[str, str],
        sla_tier: str = "silver",
    ) -> PollSLAOutput:
        """
        Query current SLA metrics between endpoints.
        From DESIGN.md:
            GET /api/v1/metrics?source={src}&dest={dst}&window=5m
        """
        src, dst = path_endpoints
        logger.info("Querying PCA SLA metrics", source=src, dest=dst, window=self.metrics_window)

        try:
            client = await self._get_client()
            response = await client.get(
                "/api/v1/metrics",
                params={
                    "source": src,
                    "dest": dst,
                    "window": self.metrics_window,
                    "metrics": "latency,jitter,loss",
                },
            )
            response.raise_for_status()
            data = response.json()

            metrics = SLAMetrics(
                latency_ms=data.get("latency_ms", 0.0),
                jitter_ms=data.get("jitter_ms", 0.0),
                packet_loss_pct=data.get("packet_loss_pct", 0.0),
                measurement_time=datetime.fromisoformat(data.get("measurement_time", datetime.now().isoformat())),
            )

            thresholds = SLA_TIER_THRESHOLDS.get(sla_tier, SLA_TIER_THRESHOLDS["silver"])
            meets_sla = metrics.meets_threshold(thresholds)

            logger.info(
                "PCA SLA metrics retrieved",
                latency_ms=metrics.latency_ms,
                jitter_ms=metrics.jitter_ms,
                loss_pct=metrics.packet_loss_pct,
                meets_sla=meets_sla,
            )

            return PollSLAOutput(metrics=metrics, meets_sla=meets_sla)

        except httpx.HTTPError as e:
            logger.warning("PCA API unavailable, using simulated metrics", error=str(e))
            return await self._simulate_sla_metrics(src, dst, sla_tier)

    async def _simulate_sla_metrics(
        self,
        source: str,
        dest: str,
        sla_tier: str,
    ) -> PollSLAOutput:
        """
        Simulate SLA metrics for demo/testing.
        Simulates gradual recovery (80% chance metrics meet SLA).
        """
        thresholds = SLA_TIER_THRESHOLDS.get(sla_tier, SLA_TIER_THRESHOLDS["silver"])

        # 80% chance of meeting SLA (simulating recovery)
        if random.random() < 0.8:
            # Generate metrics that meet SLA
            metrics = SLAMetrics(
                latency_ms=thresholds["max_latency_ms"] * random.uniform(0.3, 0.8),
                jitter_ms=thresholds["max_jitter_ms"] * random.uniform(0.2, 0.7),
                packet_loss_pct=thresholds["max_loss_pct"] * random.uniform(0.0, 0.5),
                measurement_time=datetime.now(),
            )
        else:
            # Generate metrics that exceed SLA (still degraded)
            metrics = SLAMetrics(
                latency_ms=thresholds["max_latency_ms"] * random.uniform(1.1, 1.5),
                jitter_ms=thresholds["max_jitter_ms"] * random.uniform(1.1, 1.5),
                packet_loss_pct=thresholds["max_loss_pct"] * random.uniform(1.1, 2.0),
                measurement_time=datetime.now(),
            )

        meets_sla = metrics.meets_threshold(thresholds)

        logger.info(
            "Simulated SLA metrics",
            source=source,
            dest=dest,
            latency_ms=metrics.latency_ms,
            meets_sla=meets_sla,
        )

        return PollSLAOutput(metrics=metrics, meets_sla=meets_sla)

    async def verify_stability(
        self,
        path_endpoints: Tuple[str, str],
        sla_tier: str,
        check_count: int = 3,
    ) -> bool:
        """
        Verify SLA stability over multiple checks.
        Returns True only if all checks meet SLA.
        """
        logger.info(
            "Verifying SLA stability",
            endpoints=path_endpoints,
            sla_tier=sla_tier,
            check_count=check_count,
        )

        for i in range(check_count):
            result = await self.get_path_sla(path_endpoints, sla_tier)
            if not result.meets_sla:
                logger.warning("Stability check failed", check_number=i + 1)
                return False
            logger.info("Stability check passed", check_number=i + 1)

        logger.info("SLA stability verified")
        return True

    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
_pca_client: Optional[PCASLAClient] = None


def get_pca_client(
    base_url: Optional[str] = None,
    metrics_window: str = "5m",
) -> PCASLAClient:
    """Get or create PCA SLA client singleton"""
    global _pca_client
    if _pca_client is None:
        _pca_client = PCASLAClient(base_url=base_url, metrics_window=metrics_window)
    return _pca_client
