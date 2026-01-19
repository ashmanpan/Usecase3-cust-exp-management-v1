"""Return Analytics Node - Return final analytics response"""
from typing import Any
from datetime import datetime
import structlog

from ..schemas.analytics import AnalyticsResponse

logger = structlog.get_logger(__name__)


async def return_analytics_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Return final analytics response.
    """
    task_id = state.get("task_id", "")
    error = state.get("error")

    # Build response
    response = AnalyticsResponse(
        task_id=task_id,
        analysis_timestamp=datetime.now(),
        pe_count=state.get("pe_count", 0),
        total_demand_gbps=state.get("total_demand_gbps", 0.0),
        high_risk_count=state.get("high_risk_count", 0),
        medium_risk_count=state.get("medium_risk_count", 0),
        max_utilization=state.get("max_utilization", 0.0),
        overall_risk_level=state.get("risk_level", "low"),
        at_risk_links=state.get("at_risk_links", []),
        at_risk_services=state.get("at_risk_services", []),
        proactive_alert_emitted=state.get("proactive_alert_emitted", False),
        alert_id=state.get("alert_id"),
        error=error,
    )

    logger.info(
        "Traffic analytics complete",
        task_id=task_id,
        risk_level=response.overall_risk_level,
        proactive_alert_emitted=response.proactive_alert_emitted,
    )

    return {
        "result": response.model_dump(),
        "stage": "return_analytics",
        "status": "completed" if not error else "failed",
    }
