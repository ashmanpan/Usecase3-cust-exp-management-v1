"""BSID Allocator - From DESIGN.md BSIDAllocator"""
import os
from typing import Optional
from datetime import datetime
import structlog
import redis.asyncio as redis

logger = structlog.get_logger(__name__)

class BSIDAllocator:
    """Allocate Binding SIDs for SR policies - From DESIGN.md"""
    SR_MPLS_BSID_RANGE = (24000, 24999)
    SRV6_BSID_PREFIX = "fc00:0:ffff::"

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379")
        self._client: Optional[redis.Redis] = None

    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    async def allocate_mpls_bsid(self, head_end: str) -> int:
        """Allocate next available MPLS BSID for head-end"""
        client = await self._get_client()
        key = f"bsid:mpls:{head_end}"

        # Check free list first
        free_key = f"bsid:free:{head_end}"
        free_bsid = await client.spop(free_key)
        if free_bsid:
            return int(free_bsid)

        # Allocate new
        current = await client.get(key)
        current = int(current) if current else self.SR_MPLS_BSID_RANGE[0] - 1
        next_bsid = current + 1

        if next_bsid > self.SR_MPLS_BSID_RANGE[1]:
            raise Exception(f"No more BSIDs available for {head_end}")

        await client.set(key, next_bsid)
        logger.info("Allocated MPLS BSID", head_end=head_end, bsid=next_bsid)
        return next_bsid

    async def allocate_srv6_bsid(self, head_end: str) -> str:
        """Allocate SRv6 BSID"""
        client = await self._get_client()
        key = f"bsid:srv6:{head_end}"
        current = await client.incr(key)
        bsid = f"{self.SRV6_BSID_PREFIX}{current}"
        logger.info("Allocated SRv6 BSID", head_end=head_end, bsid=bsid)
        return bsid

    async def release_bsid(self, head_end: str, bsid: int) -> None:
        """Release BSID back to pool"""
        client = await self._get_client()
        await client.sadd(f"bsid:free:{head_end}", bsid)
        logger.info("Released BSID", head_end=head_end, bsid=bsid)

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

_bsid_allocator: Optional[BSIDAllocator] = None

def get_bsid_allocator() -> BSIDAllocator:
    global _bsid_allocator
    if _bsid_allocator is None:
        _bsid_allocator = BSIDAllocator()
    return _bsid_allocator
