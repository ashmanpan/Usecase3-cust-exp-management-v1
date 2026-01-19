"""Telemetry Collector - From DESIGN.md TelemetryCollector"""
import os
import asyncio
import random
import time
from typing import Optional, List
from datetime import datetime
import httpx
import structlog

from ..schemas.telemetry import (
    SRPMMetric,
    InterfaceCounter,
    FlowRecord,
    TelemetryData,
)

logger = structlog.get_logger(__name__)


class TelemetryCollector:
    """
    Unified telemetry collection for all TE types.
    From DESIGN.md: Collects SR-PM, MDT, NetFlow data in parallel.
    """

    def __init__(
        self,
        cnc_base_url: Optional[str] = None,
        mdt_endpoint: Optional[str] = None,
        netflow_url: Optional[str] = None,
        window_minutes: int = 5,
    ):
        self.cnc_base_url = cnc_base_url or os.getenv("CNC_API_URL", "https://cnc.example.com")
        self.mdt_endpoint = mdt_endpoint or os.getenv("MDT_GRPC_ENDPOINT", "mdt-collector:57400")
        self.netflow_url = netflow_url or os.getenv("NETFLOW_COLLECTOR_URL", "http://netflow-collector:8080")
        self.window_minutes = window_minutes
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    async def collect_all(self, sources: List[str] = None) -> TelemetryData:
        """
        Collect from all sources in parallel.
        From DESIGN.md TelemetryCollector.collect_all()
        """
        sources = sources or ["sr-pm", "mdt", "netflow"]
        start_time = time.time()

        logger.info("Collecting telemetry", sources=sources, window_minutes=self.window_minutes)

        # Collect from all enabled sources in parallel
        tasks = []
        if "sr-pm" in sources:
            tasks.append(("sr_pm", self.collect_sr_pm()))
        if "mdt" in sources:
            tasks.append(("mdt", self.collect_mdt()))
        if "netflow" in sources:
            tasks.append(("netflow", self.collect_netflow()))

        results = {}
        for name, coro in tasks:
            try:
                results[name] = await coro
            except Exception as e:
                logger.warning(f"Failed to collect {name}", error=str(e))
                results[name] = []

        collection_time_ms = int((time.time() - start_time) * 1000)

        telemetry = TelemetryData(
            collection_timestamp=datetime.now(),
            window_minutes=self.window_minutes,
            sr_pm=results.get("sr_pm", []),
            mdt=results.get("mdt", []),
            netflow=results.get("netflow", []),
            sr_pm_count=len(results.get("sr_pm", [])),
            mdt_count=len(results.get("mdt", [])),
            netflow_count=len(results.get("netflow", [])),
            collection_time_ms=collection_time_ms,
        )

        logger.info(
            "Telemetry collected",
            total_records=telemetry.total_records(),
            collection_time_ms=collection_time_ms,
        )

        return telemetry

    async def collect_sr_pm(self) -> List[SRPMMetric]:
        """
        Collect SR Performance Measurement data.
        From DESIGN.md: Provides per-path delay, loss, jitter.
        """
        logger.debug("Collecting SR-PM telemetry")

        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.cnc_base_url}/crosswork/telemetry/v1/sr-pm/metrics",
                params={"window": f"{self.window_minutes}m"},
            )
            response.raise_for_status()

            data = response.json()
            return [SRPMMetric(**m) for m in data.get("metrics", [])]

        except httpx.HTTPError as e:
            logger.warning("SR-PM API unavailable, using simulated data", error=str(e))
            return self._simulate_sr_pm()

    async def collect_mdt(self) -> List[InterfaceCounter]:
        """
        Collect Model-Driven Telemetry (interface counters).
        From DESIGN.md: Provides bytes/packets per interface.
        """
        logger.debug("Collecting MDT telemetry")

        # In production, this would use gRPC streaming
        # For now, simulate interface counters
        return self._simulate_mdt()

    async def collect_netflow(self) -> List[FlowRecord]:
        """
        Collect NetFlow/IPFIX records.
        From DESIGN.md: Provides per-flow traffic volumes with SRv6 SIDs.
        """
        logger.debug("Collecting NetFlow telemetry")

        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.netflow_url}/api/v1/flows",
                params={
                    "window": f"{self.window_minutes}m",
                    "include_srv6": True,
                },
            )
            response.raise_for_status()

            data = response.json()
            return [FlowRecord(**f) for f in data.get("flows", [])]

        except httpx.HTTPError as e:
            logger.warning("NetFlow API unavailable, using simulated data", error=str(e))
            return self._simulate_netflow()

    def _simulate_sr_pm(self) -> List[SRPMMetric]:
        """Simulate SR-PM metrics for demo"""
        pe_pairs = [
            ("PE1", "PE2"), ("PE1", "PE3"), ("PE2", "PE3"),
            ("PE2", "PE4"), ("PE3", "PE4"), ("PE1", "PE4"),
        ]

        metrics = []
        for src, dst in pe_pairs:
            # Simulate both SR-MPLS and SRv6 paths
            metrics.append(SRPMMetric(
                metric_id=f"srpm-{src}-{dst}-mpls",
                headend=src,
                endpoint=dst,
                sr_policy_bsid=24000 + hash(f"{src}{dst}") % 1000,
                sr_policy_name=f"policy-{src}-{dst}",
                traffic_gbps=random.uniform(1.0, 8.0),
                latency_ms=random.uniform(2.0, 15.0),
                jitter_ms=random.uniform(0.1, 2.0),
                packet_loss_pct=random.uniform(0.0, 0.1),
            ))

            # SRv6 path
            metrics.append(SRPMMetric(
                metric_id=f"srpm-{src}-{dst}-srv6",
                headend=src,
                endpoint=dst,
                srv6_locator=f"fc00:{src.lower()}::{dst.lower()}",
                source_locator=f"fc00:{src.lower()}::1",
                dest_locator=f"fc00:{dst.lower()}::1",
                traffic_gbps=random.uniform(0.5, 5.0),
                latency_ms=random.uniform(2.0, 12.0),
                jitter_ms=random.uniform(0.1, 1.5),
                packet_loss_pct=random.uniform(0.0, 0.05),
            ))

        return metrics

    def _simulate_mdt(self) -> List[InterfaceCounter]:
        """Simulate MDT interface counters for demo"""
        interfaces = [
            ("PE1", "GigabitEthernet0/0/0"),
            ("PE1", "GigabitEthernet0/0/1"),
            ("PE2", "GigabitEthernet0/0/0"),
            ("PE2", "TenGigabitEthernet0/0/0"),
            ("PE3", "TenGigabitEthernet0/0/0"),
            ("PE4", "TenGigabitEthernet0/0/0"),
        ]

        counters = []
        for device, interface in interfaces:
            capacity = 10.0 if "TenGigabit" in interface else 1.0
            utilization = random.uniform(0.3, 0.9)
            traffic_gbps = capacity * utilization

            counters.append(InterfaceCounter(
                device_name=device,
                interface_name=interface,
                bytes_in=int(traffic_gbps * 1e9 * 300 / 8),  # 5 min
                bytes_out=int(traffic_gbps * 0.8 * 1e9 * 300 / 8),
                bps_in=traffic_gbps * 1e9,
                bps_out=traffic_gbps * 0.8 * 1e9,
                utilization_pct=utilization * 100,
                capacity_gbps=capacity,
            ))

        return counters

    def _simulate_netflow(self) -> List[FlowRecord]:
        """Simulate NetFlow records for demo"""
        flows = []
        for i in range(50):
            src_pe = random.choice(["PE1", "PE2", "PE3", "PE4"])
            dst_pe = random.choice([p for p in ["PE1", "PE2", "PE3", "PE4"] if p != src_pe])

            flows.append(FlowRecord(
                flow_id=f"flow-{i:04d}",
                src_ip=f"10.{hash(src_pe) % 255}.{i % 255}.1",
                dst_ip=f"10.{hash(dst_pe) % 255}.{i % 255}.2",
                src_port=random.randint(1024, 65535),
                dst_port=random.choice([80, 443, 8080, 22, 3389]),
                protocol=6,  # TCP
                bytes=random.randint(1000000, 100000000),
                packets=random.randint(1000, 100000),
                srv6_sid=f"fc00:{dst_pe.lower()}::end" if random.random() > 0.5 else None,
                src_pe=src_pe,
                dst_pe=dst_pe,
            ))

        return flows

    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
_telemetry_collector: Optional[TelemetryCollector] = None


def get_telemetry_collector(
    cnc_base_url: Optional[str] = None,
    window_minutes: int = 5,
) -> TelemetryCollector:
    """Get or create telemetry collector singleton"""
    global _telemetry_collector
    if _telemetry_collector is None:
        _telemetry_collector = TelemetryCollector(
            cnc_base_url=cnc_base_url,
            window_minutes=window_minutes,
        )
    return _telemetry_collector
