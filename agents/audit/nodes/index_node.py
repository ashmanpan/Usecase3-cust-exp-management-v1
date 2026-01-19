"""Index Async Node - From DESIGN.md"""
import asyncio
from datetime import datetime
from typing import Any
import structlog

from ..tools.elasticsearch_client import get_elasticsearch_client

logger = structlog.get_logger(__name__)


async def index_async_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    INDEX_ASYNC Node - From DESIGN.md
    Updates search indices in Elasticsearch (async, non-blocking).

    Input: Formatted log and storage confirmation
    Output: Indexing status
    """
    logger.info(
        "Indexing audit event to Elasticsearch",
        task_id=state.get("task_id"),
        event_id=state.get("event_id"),
    )

    task_type = state.get("task_type", "log_event")

    # Skip indexing for query tasks
    if task_type in ["get_timeline", "generate_report"]:
        return {
            "stage": "index_async",
            "indexed": True,
            "es_enabled": False,
        }

    # Check if DB store succeeded
    if not state.get("db_stored"):
        logger.warning(
            "Skipping ES indexing - DB store failed",
            event_id=state.get("event_id"),
        )
        return {
            "stage": "index_async",
            "indexed": False,
            "index_error": "DB store failed, skipping ES index",
        }

    es_client = get_elasticsearch_client()

    # Check if ES is enabled
    if not es_client.enabled:
        logger.info("Elasticsearch indexing disabled")
        return {
            "stage": "index_async",
            "indexed": True,
            "es_enabled": False,
        }

    formatted_log = state.get("formatted_log", {})

    # Parse timestamp
    timestamp_str = formatted_log.get("timestamp", state.get("timestamp"))
    try:
        timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.utcnow()
    except ValueError:
        timestamp = datetime.utcnow()

    # Index asynchronously (fire and forget in production)
    # Here we await for demo purposes
    try:
        indexed = await es_client.index_audit_event(
            event_id=formatted_log.get("event_id", state.get("event_id")),
            timestamp=timestamp,
            incident_id=formatted_log.get("incident_id"),
            agent_name=formatted_log.get("agent_name", "unknown"),
            node_name=formatted_log.get("node_name"),
            event_type=formatted_log.get("event_type", "state_change"),
            payload=formatted_log.get("payload", {}),
            previous_state=formatted_log.get("previous_state"),
            new_state=formatted_log.get("new_state"),
            decision_type=formatted_log.get("decision_type"),
            decision_reasoning=formatted_log.get("decision_reasoning"),
            actor=formatted_log.get("actor", "system"),
        )

        if indexed:
            logger.info(
                "Audit event indexed to Elasticsearch",
                event_id=state.get("event_id"),
            )
            return {
                "stage": "index_async",
                "indexed": True,
                "es_enabled": True,
            }
        else:
            return {
                "stage": "index_async",
                "indexed": False,
                "es_enabled": True,
                "index_error": "Elasticsearch indexing failed",
            }

    except Exception as e:
        logger.error(
            "Elasticsearch indexing error",
            event_id=state.get("event_id"),
            error=str(e),
        )
        return {
            "stage": "index_async",
            "indexed": False,
            "es_enabled": True,
            "index_error": str(e),
        }
