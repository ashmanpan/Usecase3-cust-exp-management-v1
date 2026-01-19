"""Elasticsearch Client for Audit Indexing - From DESIGN.md"""
import os
from datetime import datetime
from typing import Optional, Any
import structlog

logger = structlog.get_logger(__name__)

# Singleton instance
_elasticsearch_client: Optional["ElasticsearchClient"] = None


class ElasticsearchClient:
    """
    Elasticsearch Client for Async Audit Indexing - From DESIGN.md
    Provides search capabilities for audit events.
    """

    def __init__(
        self,
        hosts: list[str] = None,
        index_prefix: str = "audit-events",
        username: str = None,
        password: str = None,
        enabled: bool = None,
    ):
        self.hosts = hosts or [os.getenv("ES_HOST", "localhost:9200")]
        self.index_prefix = index_prefix
        self.username = username or os.getenv("ES_USERNAME", "")
        self.password = password or os.getenv("ES_PASSWORD", "")
        self.enabled = enabled if enabled is not None else (
            os.getenv("ES_ENABLED", "false").lower() == "true"
        )
        self._client = None

    async def connect(self) -> None:
        """Initialize Elasticsearch connection"""
        if not self.enabled:
            logger.info("Elasticsearch indexing disabled")
            return

        try:
            # In production, use elasticsearch-py async client:
            # from elasticsearch import AsyncElasticsearch
            # self._client = AsyncElasticsearch(
            #     hosts=self.hosts,
            #     basic_auth=(self.username, self.password) if self.username else None,
            # )
            logger.info(
                "Elasticsearch connection simulated",
                hosts=self.hosts,
                index_prefix=self.index_prefix,
            )
        except Exception as e:
            logger.error("Failed to connect to Elasticsearch", error=str(e))
            # Don't raise - ES is optional

    async def close(self) -> None:
        """Close Elasticsearch connection"""
        if self._client:
            await self._client.close()
            logger.info("Elasticsearch connection closed")

    async def index_audit_event(
        self,
        event_id: str,
        timestamp: datetime,
        incident_id: Optional[str],
        agent_name: str,
        node_name: Optional[str],
        event_type: str,
        payload: dict[str, Any],
        previous_state: Optional[str] = None,
        new_state: Optional[str] = None,
        decision_type: Optional[str] = None,
        decision_reasoning: Optional[str] = None,
        actor: str = "system",
    ) -> bool:
        """
        Index audit event to Elasticsearch - From DESIGN.md
        Called asynchronously after PostgreSQL storage.
        """
        if not self.enabled:
            return True

        try:
            # Build index name with date suffix for time-based indices
            date_suffix = timestamp.strftime("%Y.%m.%d")
            index_name = f"{self.index_prefix}-{date_suffix}"

            document = {
                "event_id": event_id,
                "@timestamp": timestamp.isoformat(),
                "incident_id": incident_id,
                "agent_name": agent_name,
                "node_name": node_name,
                "event_type": event_type,
                "payload": payload,
                "previous_state": previous_state,
                "new_state": new_state,
                "decision_type": decision_type,
                "decision_reasoning": decision_reasoning,
                "actor": actor,
            }

            # In production:
            # await self._client.index(
            #     index=index_name,
            #     id=event_id,
            #     document=document,
            # )

            logger.info(
                "Audit event indexed to Elasticsearch (simulated)",
                event_id=event_id,
                index=index_name,
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to index audit event to Elasticsearch",
                event_id=event_id,
                error=str(e),
            )
            return False

    async def search_events(
        self,
        incident_id: Optional[str] = None,
        event_type: Optional[str] = None,
        agent_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        size: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Search audit events in Elasticsearch
        Provides fast search across all indexed events.
        """
        if not self.enabled:
            return []

        try:
            # Build query
            must_clauses = []

            if incident_id:
                must_clauses.append({"term": {"incident_id": incident_id}})
            if event_type:
                must_clauses.append({"term": {"event_type": event_type}})
            if agent_name:
                must_clauses.append({"term": {"agent_name": agent_name}})
            if start_time or end_time:
                range_clause = {"@timestamp": {}}
                if start_time:
                    range_clause["@timestamp"]["gte"] = start_time.isoformat()
                if end_time:
                    range_clause["@timestamp"]["lte"] = end_time.isoformat()
                must_clauses.append({"range": range_clause})

            query = {"bool": {"must": must_clauses}} if must_clauses else {"match_all": {}}

            # In production:
            # response = await self._client.search(
            #     index=f"{self.index_prefix}-*",
            #     query=query,
            #     size=size,
            #     sort=[{"@timestamp": "asc"}],
            # )
            # return [hit["_source"] for hit in response["hits"]["hits"]]

            logger.info(
                "Elasticsearch search (simulated)",
                incident_id=incident_id,
                event_type=event_type,
            )
            return []

        except Exception as e:
            logger.error(
                "Failed to search Elasticsearch",
                error=str(e),
            )
            return []

    async def get_event_counts_by_type(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, int]:
        """
        Get event counts by type for dashboard/reporting
        Uses Elasticsearch aggregations.
        """
        if not self.enabled:
            return {}

        try:
            # In production, use aggregation query:
            # response = await self._client.search(
            #     index=f"{self.index_prefix}-*",
            #     query={"range": {"@timestamp": {"gte": start_time, "lte": end_time}}},
            #     aggs={"event_types": {"terms": {"field": "event_type", "size": 20}}},
            #     size=0,
            # )

            logger.info(
                "Event counts aggregation (simulated)",
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
            )

            # Simulated response
            return {
                "incident_created": 15,
                "alert_correlated": 45,
                "service_impact_assessed": 15,
                "path_computed": 12,
                "tunnel_provisioned": 10,
                "traffic_steered": 10,
                "sla_recovered": 9,
                "restoration_complete": 8,
                "notification_sent": 30,
                "state_change": 120,
                "error": 3,
            }

        except Exception as e:
            logger.error(
                "Failed to get event counts",
                error=str(e),
            )
            return {}


def get_elasticsearch_client() -> ElasticsearchClient:
    """Get singleton Elasticsearch client instance"""
    global _elasticsearch_client
    if _elasticsearch_client is None:
        _elasticsearch_client = ElasticsearchClient()
    return _elasticsearch_client
