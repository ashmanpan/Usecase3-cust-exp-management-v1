"""Hold Timer Manager - From DESIGN.md HoldTimerManager"""
import os
from typing import Optional
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)

# SLA tier hold timer configuration - From DESIGN.md
SLA_TIER_CONFIG = {
    "platinum": {"hold_timer_seconds": 60, "stability_check_seconds": 30},
    "gold": {"hold_timer_seconds": 120, "stability_check_seconds": 60},
    "silver": {"hold_timer_seconds": 180, "stability_check_seconds": 90},
    "bronze": {"hold_timer_seconds": 300, "stability_check_seconds": 120},
}


class HoldTimerManager:
    """
    Manage hold timers per incident/service.
    From DESIGN.md: Hold timer prevents premature cutover after SLA recovery.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._redis = None
        # In-memory timer storage for demo when Redis unavailable
        self._timers: dict[str, dict] = {}

    async def _get_redis(self):
        """Get Redis connection (lazy init)"""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(self.redis_url)
                await self._redis.ping()
            except Exception as e:
                logger.warning("Redis unavailable, using in-memory storage", error=str(e))
                self._redis = None
        return self._redis

    async def start_timer(
        self,
        incident_id: str,
        sla_tier: str,
        recovery_time: Optional[datetime] = None,
    ) -> str:
        """
        Start hold timer, return timer ID.
        From DESIGN.md HoldTimerManager.start_timer()
        """
        recovery_time = recovery_time or datetime.now()
        hold_seconds = SLA_TIER_CONFIG.get(sla_tier, SLA_TIER_CONFIG["silver"])["hold_timer_seconds"]
        expiry = recovery_time + timedelta(seconds=hold_seconds)

        timer_id = f"timer:{incident_id}"

        timer_data = {
            "incident_id": incident_id,
            "sla_tier": sla_tier,
            "recovery_time": recovery_time.isoformat(),
            "expiry_time": expiry.isoformat(),
            "hold_seconds": hold_seconds,
            "status": "waiting",
        }

        redis = await self._get_redis()
        if redis:
            # Store in Redis
            await redis.zadd("restoration:timers", {timer_id: expiry.timestamp()})
            await redis.hset(timer_id, mapping=timer_data)
        else:
            # Store in memory
            self._timers[timer_id] = timer_data

        logger.info(
            "Hold timer started",
            timer_id=timer_id,
            incident_id=incident_id,
            sla_tier=sla_tier,
            hold_seconds=hold_seconds,
            expiry_time=expiry.isoformat(),
        )

        return timer_id

    async def check_timer(self, timer_id: str) -> dict:
        """
        Check if hold timer has expired.
        From DESIGN.md HoldTimerManager.check_timer()
        """
        redis = await self._get_redis()

        if redis:
            expiry_str = await redis.hget(timer_id, "expiry_time")
            status = await redis.hget(timer_id, "status")
            if expiry_str:
                expiry_str = expiry_str.decode() if isinstance(expiry_str, bytes) else expiry_str
                status = status.decode() if isinstance(status, bytes) else status
        else:
            timer_data = self._timers.get(timer_id, {})
            expiry_str = timer_data.get("expiry_time")
            status = timer_data.get("status")

        if not expiry_str:
            logger.warning("Timer not found", timer_id=timer_id)
            return {"expired": True, "remaining_seconds": 0, "status": "not_found"}

        expiry = datetime.fromisoformat(expiry_str)
        now = datetime.now()

        if status == "cancelled":
            return {"expired": False, "remaining_seconds": 0, "status": "cancelled"}

        if now >= expiry:
            await self._update_timer_status(timer_id, "expired")
            return {"expired": True, "remaining_seconds": 0, "status": "expired"}

        remaining = int((expiry - now).total_seconds())
        logger.info("Timer check", timer_id=timer_id, remaining_seconds=remaining)
        return {"expired": False, "remaining_seconds": remaining, "status": "waiting"}

    async def cancel_timer(self, timer_id: str) -> bool:
        """
        Cancel timer (SLA degraded again during hold).
        From DESIGN.md HoldTimerManager.cancel_timer()
        """
        redis = await self._get_redis()

        if redis:
            await redis.hset(timer_id, "status", "cancelled")
            await redis.zrem("restoration:timers", timer_id)
        else:
            if timer_id in self._timers:
                self._timers[timer_id]["status"] = "cancelled"

        logger.info("Hold timer cancelled", timer_id=timer_id)
        return True

    async def _update_timer_status(self, timer_id: str, status: str):
        """Update timer status"""
        redis = await self._get_redis()

        if redis:
            await redis.hset(timer_id, "status", status)
        else:
            if timer_id in self._timers:
                self._timers[timer_id]["status"] = status

    async def get_timer_info(self, timer_id: str) -> Optional[dict]:
        """Get full timer information"""
        redis = await self._get_redis()

        if redis:
            data = await redis.hgetall(timer_id)
            if data:
                return {k.decode(): v.decode() for k, v in data.items()}
        else:
            return self._timers.get(timer_id)

        return None

    async def cleanup_expired_timers(self) -> int:
        """Clean up expired timers (maintenance)"""
        redis = await self._get_redis()
        cleaned = 0

        if redis:
            now = datetime.now().timestamp()
            expired = await redis.zrangebyscore("restoration:timers", "-inf", now)
            for timer_id in expired:
                await redis.delete(timer_id)
                await redis.zrem("restoration:timers", timer_id)
                cleaned += 1
        else:
            now = datetime.now()
            expired_keys = []
            for timer_id, data in self._timers.items():
                expiry = datetime.fromisoformat(data["expiry_time"])
                if now >= expiry:
                    expired_keys.append(timer_id)
            for key in expired_keys:
                del self._timers[key]
                cleaned += 1

        if cleaned > 0:
            logger.info("Cleaned up expired timers", count=cleaned)

        return cleaned


# Singleton instance
_timer_manager: Optional[HoldTimerManager] = None


def get_hold_timer_manager(redis_url: Optional[str] = None) -> HoldTimerManager:
    """Get or create hold timer manager singleton"""
    global _timer_manager
    if _timer_manager is None:
        _timer_manager = HoldTimerManager(redis_url=redis_url)
    return _timer_manager
