"""Warn Node - From DESIGN.md warn"""
from typing import Any
import structlog

logger = structlog.get_logger(__name__)


async def warn_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Log warning, update dashboards.
    From DESIGN.md: warn logs warning for medium risk level.
    """
    task_id = state.get("task_id")
    risk_level = state.get("risk_level", "medium")
    at_risk_links = state.get("at_risk_links", [])
    at_risk_services = state.get("at_risk_services", [])
    max_utilization = state.get("max_utilization", 0.0)

    logger.warning(
        "Traffic congestion warning",
        task_id=task_id,
        risk_level=risk_level,
        at_risk_links=at_risk_links,
        at_risk_services=at_risk_services,
        max_utilization=f"{max_utilization:.1%}",
    )

    # In production, could:
    # - Update Grafana/Prometheus metrics
    # - Send to logging aggregator
    # - Update dashboard indicators

    return {
        "stage": "warn",
        "status": "completed",
    }
