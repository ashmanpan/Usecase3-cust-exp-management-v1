"""Poll SLA Node - From DESIGN.md poll_sla"""
from typing import Any
from datetime import datetime
import structlog

from ..tools.pca_client import get_pca_client

logger = structlog.get_logger(__name__)


async def poll_sla_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Query PCA for current SLA metrics on original path.
    From DESIGN.md: poll_sla node queries PCA for SLA metrics
    """
    incident_id = state.get("incident_id")
    source = state.get("original_path_source")
    dest = state.get("original_path_dest")
    sla_tier = state.get("sla_tier", "silver")
    poll_count = state.get("poll_count", 0)

    logger.info(
        "Polling SLA metrics",
        incident_id=incident_id,
        source=source,
        dest=dest,
        sla_tier=sla_tier,
        poll_count=poll_count + 1,
    )

    try:
        pca_client = get_pca_client()
        result = await pca_client.get_path_sla(
            path_endpoints=(source, dest),
            sla_tier=sla_tier,
        )

        current_metrics = {
            "latency_ms": result.metrics.latency_ms,
            "jitter_ms": result.metrics.jitter_ms,
            "packet_loss_pct": result.metrics.packet_loss_pct,
            "measurement_time": result.metrics.measurement_time.isoformat(),
            "meets_sla": result.meets_sla,
        }

        logger.info(
            "SLA metrics polled",
            incident_id=incident_id,
            meets_sla=result.meets_sla,
            latency_ms=result.metrics.latency_ms,
        )

        return {
            "current_metrics": current_metrics,
            "sla_recovered": result.meets_sla,
            "recovery_time": datetime.now().isoformat() if result.meets_sla else None,
            "poll_count": poll_count + 1,
            "stage": "poll_sla",
            "status": "monitoring",
        }

    except Exception as e:
        logger.error("Failed to poll SLA metrics", error=str(e), incident_id=incident_id)
        return {
            "poll_count": poll_count + 1,
            "stage": "poll_sla",
            "status": "monitoring",
            "error": f"SLA poll failed: {str(e)}",
        }
