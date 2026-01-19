"""
State Manager Tool

Tool for Redis-based incident state management.
Based on DESIGN.md - Tool 2: Redis State Management
"""

import os
import json
from typing import Any, Optional
from datetime import datetime

import structlog
import redis.asyncio as redis

logger = structlog.get_logger(__name__)


class StateManagerTool:
    """
    Tool for managing incident state in Redis.

    From DESIGN.md:
    - UpdateIncidentInput: incident_id, updates
    - GetIncidentInput: incident_id
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "orchestrator:incident:",
    ):
        """
        Initialize state manager.

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

    def _make_key(self, incident_id: str) -> str:
        """Create Redis key for incident"""
        return f"{self.key_prefix}{incident_id}"

    async def get_incident(self, incident_id: str) -> Optional[dict[str, Any]]:
        """
        Get incident state from Redis.

        Args:
            incident_id: Incident identifier

        Returns:
            Incident state dict or None if not found
        """
        client = await self._get_client()
        key = self._make_key(incident_id)

        try:
            data = await client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error("Failed to get incident", incident_id=incident_id, error=str(e))
            raise

    async def update_incident(
        self,
        incident_id: str,
        updates: dict[str, Any],
        ttl_seconds: int = 86400,  # 24 hours default
    ) -> dict[str, Any]:
        """
        Update incident state in Redis.

        Args:
            incident_id: Incident identifier
            updates: Fields to update
            ttl_seconds: Time-to-live for the key

        Returns:
            Updated incident state
        """
        client = await self._get_client()
        key = self._make_key(incident_id)

        try:
            # Get existing state
            existing = await self.get_incident(incident_id)
            if existing is None:
                existing = {"incident_id": incident_id, "created_at": datetime.utcnow().isoformat()}

            # Merge updates
            existing.update(updates)
            existing["updated_at"] = datetime.utcnow().isoformat()

            # Save back
            await client.setex(key, ttl_seconds, json.dumps(existing))

            logger.info(
                "Updated incident state",
                incident_id=incident_id,
                updated_fields=list(updates.keys()),
            )

            return existing

        except Exception as e:
            logger.error("Failed to update incident", incident_id=incident_id, error=str(e))
            raise

    async def create_incident(
        self,
        incident_id: str,
        initial_state: dict[str, Any],
        ttl_seconds: int = 86400,
    ) -> dict[str, Any]:
        """
        Create new incident state in Redis.

        Args:
            incident_id: Incident identifier
            initial_state: Initial state dict
            ttl_seconds: Time-to-live for the key

        Returns:
            Created incident state
        """
        client = await self._get_client()
        key = self._make_key(incident_id)

        state = {
            "incident_id": incident_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            **initial_state,
        }

        await client.setex(key, ttl_seconds, json.dumps(state))

        logger.info("Created incident state", incident_id=incident_id)

        return state

    async def delete_incident(self, incident_id: str) -> bool:
        """
        Delete incident state from Redis.

        Args:
            incident_id: Incident identifier

        Returns:
            True if deleted, False if not found
        """
        client = await self._get_client()
        key = self._make_key(incident_id)

        deleted = await client.delete(key)
        logger.info("Deleted incident state", incident_id=incident_id, deleted=bool(deleted))

        return bool(deleted)

    async def close(self) -> None:
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None


# Singleton instance
_state_manager: Optional[StateManagerTool] = None


def get_state_manager() -> StateManagerTool:
    """Get singleton state manager instance"""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManagerTool()
    return _state_manager


# Convenience functions
async def get_incident(incident_id: str) -> Optional[dict[str, Any]]:
    """Get incident state (convenience function)"""
    manager = get_state_manager()
    return await manager.get_incident(incident_id)


async def update_incident(
    incident_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Update incident state (convenience function)"""
    manager = get_state_manager()
    return await manager.update_incident(incident_id, updates)
