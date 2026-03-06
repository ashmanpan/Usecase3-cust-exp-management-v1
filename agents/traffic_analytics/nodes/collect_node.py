"""Collect Telemetry Node - From DESIGN.md collect_telemetry"""
from typing import Any
import structlog

from ..tools.telemetry_collector import get_telemetry_collector
from ..tools.coe_metrics_client import get_coe_metrics_client

logger = structlog.get_logger(__name__)


async def collect_telemetry_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Gather data from SR-PM, MDT, NetFlow, and COE metrics.
    From DESIGN.md: collect_telemetry gathers data from all sources.
    """
    task_id = state.get("task_id")
    sources = state.get("telemetry_sources", ["sr-pm", "mdt", "netflow", "coe-metrics"])
    window_minutes = state.get("telemetry_window_minutes", 5)

    logger.info(
        "Collecting telemetry",
        task_id=task_id,
        sources=sources,
        window_minutes=window_minutes,
    )

    try:
        collector = get_telemetry_collector(window_minutes=window_minutes)
        telemetry = await collector.collect_all(sources=sources)

        logger.info(
            "Telemetry collected",
            total_records=telemetry.total_records(),
            sr_pm_count=telemetry.sr_pm_count,
            mdt_count=telemetry.mdt_count,
            netflow_count=telemetry.netflow_count,
            collection_time_ms=telemetry.collection_time_ms,
        )

        coe_metrics: dict[str, Any] = {}
        if "coe-metrics" in sources:
            try:
                coe_client = get_coe_metrics_client()
                igp = await coe_client.get_igp_links_metrics()
                sr_pol = await coe_client.get_sr_policies_metrics()
                rsvp = await coe_client.get_rsvp_policies_metrics()
                coe_metrics = {
                    "igp_links": igp,
                    "sr_policies": sr_pol,
                    "rsvp_tunnels": rsvp,
                }
                logger.info(
                    "COE metrics collected",
                    igp_links=len(igp.get("data", [])),
                    sr_policies=len(sr_pol.get("data", [])),
                    rsvp_tunnels=len(rsvp.get("data", [])),
                )
            except Exception as e:
                logger.warning(
                    "COE metrics collection failed, continuing",
                    error=str(e),
                )
                coe_metrics = {"error": str(e)}

        return {
            "telemetry_collected": True,
            "raw_telemetry": telemetry.model_dump(),
            "collection_time_ms": telemetry.collection_time_ms,
            "stage": "collect_telemetry",
            "status": "collecting",
            "coe_metrics": coe_metrics,
            "coe_metrics_collected": bool(coe_metrics and "error" not in coe_metrics),
        }

    except Exception as e:
        logger.error("Failed to collect telemetry", error=str(e), task_id=task_id)
        return {
            "telemetry_collected": False,
            "stage": "collect_telemetry",
            "error": f"Telemetry collection failed: {str(e)}",
        }
