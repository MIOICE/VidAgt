from __future__ import annotations

import asyncio
import uuid

from redis.asyncio import Redis


class LeaseUnavailable(RuntimeError):
    pass


class RedisLease:
    def __init__(self, redis: Redis, key: str, ttl_seconds: int = 120) -> None:
        self.redis = redis
        self.key = key
        self.ttl_seconds = ttl_seconds
        self.token = str(uuid.uuid4())
        self._watchdog: asyncio.Task[None] | None = None

    async def __aenter__(self) -> RedisLease:
        acquired = await self.redis.set(
            self.key, self.token, nx=True, px=self.ttl_seconds * 1000
        )
        if not acquired:
            raise LeaseUnavailable(self.key)
        self._watchdog = asyncio.create_task(self._renew())
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._watchdog:
            self._watchdog.cancel()
            try:
                await self._watchdog
            except asyncio.CancelledError:
                pass
        await self.redis.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            self.key,
            self.token,
        )

    async def _renew(self) -> None:
        while True:
            await asyncio.sleep(self.ttl_seconds / 3)
            result = await self.redis.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then "
                "return redis.call('pexpire', KEYS[1], ARGV[2]) else return 0 end",
                1,
                self.key,
                self.token,
                self.ttl_seconds * 1000,
            )
            if not result:
                raise LeaseUnavailable(f"lease lost: {self.key}")

