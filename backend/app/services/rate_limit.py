from __future__ import annotations

import time

from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.core.config import settings

TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_ms = tonumber(ARGV[2])
local now_ms = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local ttl_ms = tonumber(ARGV[5])

local state = redis.call('HMGET', key, 'tokens', 'updated_at')
local tokens = tonumber(state[1]) or capacity
local updated_at = tonumber(state[2]) or now_ms
local elapsed = math.max(0, now_ms - updated_at)
tokens = math.min(capacity, tokens + elapsed * refill_per_ms)

local allowed = 0
if tokens >= cost then
    tokens = tokens - cost
    allowed = 1
end

redis.call('HSET', key, 'tokens', tokens, 'updated_at', now_ms)
redis.call('PEXPIRE', key, ttl_ms)
return allowed
"""


async def enforce_ai_rate_limit(redis: Redis, bucket: str = "global") -> None:
    """Redis token bucket guard for accidental loops in the single-user deployment."""
    capacity = max(1, settings.ai_requests_per_minute)
    allowed = await redis.eval(
        TOKEN_BUCKET_SCRIPT,
        1,
        f"vidagt:rate:ai:{bucket}",
        capacity,
        capacity / 60_000,
        int(time.time() * 1000),
        1,
        120_000,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI 请求过于频繁，请稍后再试。",
        )
