"""Collect Telemetry Node - From DESIGN.md collect_telemetry"""
from typing import Any
import structlog

from ..tools.telemetry_collector import get_telemetry_collector

logger = structlog.get_logger(__name__)


async def collect_telemetry_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Gather data from SR-PM, MDT, NetFlow.
    From DESIGN.md: collect_telemetry gathers data from all sources.
    """
    task_id = state.get("task_id")
    sources = state.get("telemetry_sources", ["sr-pm", "mdt", "netflow"])
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

        return {
            "telemetry_collected": True,
            "raw_telemetry": telemetry.model_dump(),
            "collection_time_ms": telemetry.collection_time_ms,
            "stage": "collect_telemetry",
            "status": "collecting",
        }

    except Exception as e:
        logger.error("Failed to collect telemetry", error=str(e), task_id=task_id)
        return {
            "telemetry_collected": False,
            "stage": "collect_telemetry",
            "error": f"Telemetry collection failed: {str(e)}",
        }
