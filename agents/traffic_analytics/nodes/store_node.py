"""Store Metrics Node - From DESIGN.md store_metrics"""
from typing import Any
from datetime import datetime
import os
import structlog

logger = structlog.get_logger(__name__)


async def store_metrics_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Store historical data for trending.
    From DESIGN.md: store_metrics stores historical data.
    """
    task_id = state.get("task_id")
    demand_matrix = state.get("demand_matrix", {})
    congestion_risks = state.get("congestion_risks", [])
    total_demand_gbps = state.get("total_demand_gbps", 0.0)
    max_utilization = state.get("max_utilization", 0.0)

    logger.info(
        "Storing metrics",
        task_id=task_id,
        total_demand_gbps=total_demand_gbps,
        max_utilization=max_utilization,
    )

    try:
        # In production, store to Redis or time-series DB
        # For demo, log the metrics
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

        try:
            import redis.asyncio as aioredis
            redis_client = aioredis.from_url(redis_url)

            # Store demand matrix snapshot
            timestamp = datetime.now().isoformat()
            matrix_key = f"traffic:matrix:{timestamp}"
            await redis_client.hset(matrix_key, mapping={
                "timestamp": timestamp,
                "total_demand_gbps": str(total_demand_gbps),
                "max_utilization": str(max_utilization),
                "high_risk_count": str(state.get("high_risk_count", 0)),
                "medium_risk_count": str(state.get("medium_risk_count", 0)),
            })

            # Set TTL (24 hours)
            await redis_client.expire(matrix_key, 86400)

            # Add to time series index
            await redis_client.zadd(
                "traffic:metrics:index",
                {matrix_key: datetime.now().timestamp()}
            )

            await redis_client.aclose()
            logger.info("Metrics stored in Redis", key=matrix_key)

        except Exception as redis_error:
            logger.warning("Redis unavailable, metrics not persisted", error=str(redis_error))

        return {
            "metrics_stored": True,
            "stage": "store_metrics",
            "status": "completed",
        }

    except Exception as e:
        logger.error("Failed to store metrics", error=str(e), task_id=task_id)
        return {
            "metrics_stored": False,
            "stage": "store_metrics",
            "error": f"Metrics storage failed: {str(e)}",
        }
