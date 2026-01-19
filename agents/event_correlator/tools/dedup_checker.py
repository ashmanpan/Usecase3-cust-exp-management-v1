"""
Deduplication Checker

Checks for duplicate alerts within a time window.
"""

import os
import hashlib
import json
from typing import Tuple, Optional, List
from datetime import datetime, timedelta

import structlog
import redis.asyncio as redis

logger = structlog.get_logger(__name__)


class DedupChecker:
    """
    Alert deduplication checker.

    Maintains a Redis-based sliding window of recent alerts.
    Duplicates are identified by hashing key fields.
    """

    DEDUP_WINDOW = 300  # 5 minutes default
    HASH_FIELDS = ["link_id", "severity", "violated_thresholds"]

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "event_correlator:dedup:",
        window_seconds: int = None,
        hash_fields: List[str] = None,
    ):
        """
        Initialize dedup checker.

        Args:
            redis_url: Redis connection URL
            key_prefix: Prefix for Redis keys
            window_seconds: Dedup window in seconds
            hash_fields: Fields to use for dedup hash
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379")
        self.key_prefix = key_prefix
        self.window_seconds = window_seconds or self.DEDUP_WINDOW
        self.hash_fields = hash_fields or self.HASH_FIELDS
        self._client: Optional[redis.Redis] = None

    async def _get_client(self) -> redis.Redis:
        """Get or create Redis client"""
        if self._client is None:
            self._client = redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def _compute_hash(self, alert: dict) -> str:
        """
        Compute dedup hash for an alert.

        Args:
            alert: Alert dict

        Returns:
            Hash string
        """
        # Extract fields for hashing
        hash_data = {}
        for field in self.hash_fields:
            value = alert.get(field)
            if isinstance(value, list):
                value = sorted(value)
            hash_data[field] = value

        # Create deterministic hash
        hash_str = json.dumps(hash_data, sort_keys=True)
        return hashlib.sha256(hash_str.encode()).hexdigest()[:16]

    async def check_duplicate(self, alert: dict) -> Tuple[bool, Optional[str]]:
        """
        Check if alert is a duplicate.

        Args:
            alert: Alert dict

        Returns:
            Tuple of (is_duplicate, original_alert_id)
        """
        client = await self._get_client()
        alert_hash = self._compute_hash(alert)
        hash_key = f"{self.key_prefix}hash:{alert_hash}"

        # Check if hash exists
        existing = await client.get(hash_key)

        if existing:
            logger.debug(
                "Duplicate alert detected",
                alert_id=alert.get("alert_id"),
                duplicate_of=existing,
                hash=alert_hash,
            )
            return True, existing

        return False, None

    async def record_alert(self, alert: dict) -> str:
        """
        Record an alert for dedup tracking.

        Args:
            alert: Alert dict

        Returns:
            Dedup hash
        """
        client = await self._get_client()
        alert_hash = self._compute_hash(alert)
        hash_key = f"{self.key_prefix}hash:{alert_hash}"
        alert_id = alert.get("alert_id", "unknown")

        # Store alert ID with TTL
        await client.setex(hash_key, self.window_seconds, alert_id)

        logger.debug(
            "Recorded alert for dedup",
            alert_id=alert_id,
            hash=alert_hash,
            window_seconds=self.window_seconds,
        )

        return alert_hash

    async def close(self) -> None:
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None


# Singleton instance
_dedup_checker: Optional[DedupChecker] = None


def get_dedup_checker() -> DedupChecker:
    """Get singleton dedup checker instance"""
    global _dedup_checker
    if _dedup_checker is None:
        _dedup_checker = DedupChecker()
    return _dedup_checker


# Convenience function
async def check_duplicate(alert: dict) -> Tuple[bool, Optional[str]]:
    """Check if alert is duplicate (convenience function)"""
    checker = get_dedup_checker()
    return await checker.check_duplicate(alert)
