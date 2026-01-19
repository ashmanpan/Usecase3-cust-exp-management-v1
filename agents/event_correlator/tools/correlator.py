"""
Alert Correlator

Based on DESIGN.md - Correlation Rules for grouping related alerts.
"""

import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from uuid import uuid4

import structlog
import redis.asyncio as redis

logger = structlog.get_logger(__name__)

# Correlation rules from DESIGN.md
CORRELATION_RULES = [
    {
        "name": "same_link_multiple_metrics",
        "description": "Multiple SLA violations on same link within 60s",
        "window_seconds": 60,
        "group_by": ["link_id"],
        "action": "merge_into_single_incident",
    },
    {
        "name": "adjacent_link_failures",
        "description": "Alerts on links sharing a node within 30s",
        "window_seconds": 30,
        "group_by": ["shared_node"],
        "action": "flag_potential_node_issue",
    },
    {
        "name": "path_correlation",
        "description": "Multiple links on same SR policy path",
        "window_seconds": 120,
        "group_by": ["policy_path"],
        "action": "identify_root_cause_link",
    },
]


class AlertCorrelator:
    """
    Alert correlator for grouping related alerts.

    From DESIGN.md correlation rules.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "event_correlator:correlation:",
    ):
        """
        Initialize correlator.

        Args:
            redis_url: Redis connection URL
            key_prefix: Prefix for Redis keys
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379")
        self.key_prefix = key_prefix
        self._client: Optional[redis.Redis] = None

    async def _get_client(self) -> redis.Redis:
        """Get or create Redis client"""
        if self._client is None:
            self._client = redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    async def correlate(self, alert: dict) -> Dict[str, Any]:
        """
        Correlate an alert with existing alerts.

        Args:
            alert: Normalized alert dict

        Returns:
            Correlation result with incident_id, correlated_alerts, etc.
        """
        client = await self._get_client()
        link_id = alert.get("link_id")
        alert_id = alert.get("alert_id")

        # Check each correlation rule
        for rule in CORRELATION_RULES:
            result = await self._apply_rule(client, alert, rule)
            if result.get("matched"):
                logger.info(
                    "Correlation rule matched",
                    rule=rule["name"],
                    alert_id=alert_id,
                    link_id=link_id,
                )
                return result

        # No correlation found - create new incident
        incident_id = f"INC-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"

        # Store alert for future correlation
        await self._store_alert(client, alert, incident_id)

        return {
            "matched": False,
            "incident_id": incident_id,
            "is_new_incident": True,
            "correlated_alerts": [alert_id],
            "correlation_rule": None,
            "degraded_links": [link_id] if link_id else [],
            "alert_count": 1,
        }

    async def _apply_rule(
        self,
        client: redis.Redis,
        alert: dict,
        rule: dict,
    ) -> Dict[str, Any]:
        """
        Apply a single correlation rule.

        Args:
            client: Redis client
            alert: Alert to correlate
            rule: Correlation rule

        Returns:
            Correlation result
        """
        rule_name = rule["name"]
        window_seconds = rule["window_seconds"]
        group_by = rule["group_by"]

        # Build key based on group_by fields
        group_values = []
        for field in group_by:
            value = alert.get(field)
            if value:
                group_values.append(str(value))

        if not group_values:
            return {"matched": False}

        group_key = ":".join(group_values)
        correlation_key = f"{self.key_prefix}{rule_name}:{group_key}"

        # Get existing alerts in window
        now = datetime.utcnow()
        window_start = (now - timedelta(seconds=window_seconds)).timestamp()

        # Get alerts in time window using sorted set
        existing = await client.zrangebyscore(
            correlation_key,
            window_start,
            "+inf",
            withscores=True,
        )

        if existing:
            # Found correlated alerts
            correlated_alerts = [alert.get("alert_id")]
            incident_id = None
            degraded_links = set()

            if alert.get("link_id"):
                degraded_links.add(alert.get("link_id"))

            for item, score in existing:
                try:
                    import json
                    stored = json.loads(item)
                    correlated_alerts.append(stored.get("alert_id"))
                    if stored.get("incident_id"):
                        incident_id = stored.get("incident_id")
                    if stored.get("link_id"):
                        degraded_links.add(stored.get("link_id"))
                except Exception:
                    pass

            if not incident_id:
                incident_id = f"INC-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"

            # Store current alert
            await self._store_alert(client, alert, incident_id, rule_name)

            return {
                "matched": True,
                "incident_id": incident_id,
                "is_new_incident": False,
                "correlated_alerts": correlated_alerts,
                "correlation_rule": rule_name,
                "correlation_reason": rule["description"],
                "degraded_links": list(degraded_links),
                "alert_count": len(correlated_alerts),
            }

        return {"matched": False}

    async def _store_alert(
        self,
        client: redis.Redis,
        alert: dict,
        incident_id: str,
        rule_name: str = None,
    ) -> None:
        """
        Store alert for future correlation.

        Args:
            client: Redis client
            alert: Alert to store
            incident_id: Associated incident ID
            rule_name: Correlation rule (if any)
        """
        import json

        link_id = alert.get("link_id")
        now = datetime.utcnow()
        score = now.timestamp()

        # Store under each correlation rule key
        for rule in CORRELATION_RULES:
            group_by = rule["group_by"]
            group_values = []

            for field in group_by:
                value = alert.get(field)
                if value:
                    group_values.append(str(value))

            if group_values:
                group_key = ":".join(group_values)
                correlation_key = f"{self.key_prefix}{rule['name']}:{group_key}"

                stored_data = json.dumps({
                    "alert_id": alert.get("alert_id"),
                    "incident_id": incident_id,
                    "link_id": link_id,
                    "timestamp": now.isoformat(),
                })

                await client.zadd(correlation_key, {stored_data: score})
                await client.expire(correlation_key, rule["window_seconds"] * 2)

    async def close(self) -> None:
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None


# Singleton instance
_correlator: Optional[AlertCorrelator] = None


def get_correlator() -> AlertCorrelator:
    """Get singleton correlator instance"""
    global _correlator
    if _correlator is None:
        _correlator = AlertCorrelator()
    return _correlator


# Convenience function
async def correlate_alerts(alert: dict) -> Dict[str, Any]:
    """Correlate alert (convenience function)"""
    correlator = get_correlator()
    return await correlator.correlate(alert)
