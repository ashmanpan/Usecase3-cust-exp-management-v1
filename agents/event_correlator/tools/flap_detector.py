"""
Flap Detector

Based on DESIGN.md - FlapDetector class with exponential backoff.
"""

import os
from typing import Tuple, Optional
from datetime import datetime, timedelta

import structlog
import redis.asyncio as redis

logger = structlog.get_logger(__name__)


class FlapDetector:
    """
    Exponential backoff for flapping links.

    From DESIGN.md:
    - State transitions within FLAP_WINDOW trigger damping.
    - Damping time doubles each occurrence, up to MAX_DAMPEN.
    """

    FLAP_WINDOW = 300        # 5 minutes
    FLAP_THRESHOLD = 3       # 3 state changes = flapping
    INITIAL_DAMPEN = 60      # 1 minute initial suppression
    MAX_DAMPEN = 3600        # 1 hour max suppression

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "event_correlator:flap:",
    ):
        """
        Initialize flap detector.

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

    async def check_flapping(self, link_id: str) -> Tuple[bool, int]:
        """
        Check if link is flapping.

        From DESIGN.md:
        - Returns (is_flapping, dampen_seconds)

        Args:
            link_id: Link identifier

        Returns:
            Tuple of (is_flapping, dampen_seconds)
        """
        client = await self._get_client()
        history_key = f"{self.key_prefix}history:{link_id}"
        count_key = f"{self.key_prefix}count:{link_id}"

        # Get flap history
        history = await client.lrange(history_key, 0, -1)

        # Filter to recent events within window
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.FLAP_WINDOW)
        recent = []
        for h in history:
            try:
                event_time = datetime.fromisoformat(h)
                if event_time >= window_start:
                    recent.append(h)
            except Exception:
                pass

        logger.debug(
            "Checking flap history",
            link_id=link_id,
            total_history=len(history),
            recent_count=len(recent),
        )

        if len(recent) >= self.FLAP_THRESHOLD:
            # Link is flapping - calculate exponential backoff
            flap_count = await client.incr(count_key)
            await client.expire(count_key, self.MAX_DAMPEN * 2)

            dampen_time = min(
                self.INITIAL_DAMPEN * (2 ** (flap_count - 1)),
                self.MAX_DAMPEN,
            )

            logger.warning(
                "Link flapping detected",
                link_id=link_id,
                flap_count=flap_count,
                dampen_seconds=dampen_time,
            )

            return True, int(dampen_time)

        return False, 0

    async def record_event(self, link_id: str) -> None:
        """
        Record a state change event for a link.

        Args:
            link_id: Link identifier
        """
        client = await self._get_client()
        history_key = f"{self.key_prefix}history:{link_id}"

        # Add current timestamp to history
        now = datetime.utcnow().isoformat()
        await client.lpush(history_key, now)

        # Trim to keep only recent history
        await client.ltrim(history_key, 0, 99)  # Keep last 100 events

        # Set expiry on history key
        await client.expire(history_key, self.FLAP_WINDOW * 2)

        logger.debug("Recorded flap event", link_id=link_id)

    async def reset_flap_count(self, link_id: str) -> None:
        """
        Reset flap counter for a link.

        Called when link stabilizes.

        Args:
            link_id: Link identifier
        """
        client = await self._get_client()
        count_key = f"{self.key_prefix}count:{link_id}"
        await client.delete(count_key)
        logger.info("Reset flap count", link_id=link_id)

    async def get_dampen_until(self, link_id: str) -> Optional[str]:
        """
        Get dampen expiry time for a link.

        Args:
            link_id: Link identifier

        Returns:
            ISO timestamp when dampen expires, or None
        """
        client = await self._get_client()
        dampen_key = f"{self.key_prefix}dampen:{link_id}"
        return await client.get(dampen_key)

    async def set_dampen(self, link_id: str, seconds: int) -> str:
        """
        Set dampen period for a link.

        Args:
            link_id: Link identifier
            seconds: Dampen duration

        Returns:
            ISO timestamp when dampen expires
        """
        client = await self._get_client()
        dampen_key = f"{self.key_prefix}dampen:{link_id}"

        dampen_until = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()
        await client.setex(dampen_key, seconds, dampen_until)

        logger.info(
            "Set dampen period",
            link_id=link_id,
            seconds=seconds,
            until=dampen_until,
        )

        return dampen_until

    async def close(self) -> None:
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None


# Singleton instance
_flap_detector: Optional[FlapDetector] = None


def get_flap_detector() -> FlapDetector:
    """Get singleton flap detector instance"""
    global _flap_detector
    if _flap_detector is None:
        _flap_detector = FlapDetector()
    return _flap_detector


# Convenience function
async def check_flapping(link_id: str) -> Tuple[bool, int]:
    """Check if link is flapping (convenience function)"""
    detector = get_flap_detector()
    return await detector.check_flapping(link_id)
