from __future__ import annotations

import asyncio
import importlib
import time
from typing import Iterable

try:
    _redis_asyncio = importlib.import_module("redis.asyncio")
except ModuleNotFoundError as exc:
    raise ImportError(
        "Missing dependency 'redis.asyncio'. Install redis-py (>=4.2), e.g. "
        "`pip install -U redis`, and select that interpreter in VS Code."
    ) from exc

Redis = _redis_asyncio.Redis
ConnectionPool = _redis_asyncio.ConnectionPool


class WhatsAppSessionStateManager:
    """Manage WhatsApp booking session state and temporary slot holds in Redis.

    Design notes:
    - A slot is considered available when it is present in the available-slot set.
    - Locking a slot removes it from the available-slot set and creates a lock key with TTL.
    - If the lock expires before confirmation, a background reaper restores the slot.
    """

    def __init__(
        self,
        redis_url: str,
        *,
        booking_ttl_seconds: int = 300,
        key_prefix: str = "wa_booking",
        max_connections: int = 50,
    ) -> None:
        self.booking_ttl_seconds = booking_ttl_seconds
        self.key_prefix = key_prefix

        self._pool = ConnectionPool.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=max_connections,
        )
        self._redis = Redis(connection_pool=self._pool)

        self._available_slots_key = f"{self.key_prefix}:slots:available"
        self._expiry_index_key = f"{self.key_prefix}:slots:expiries"

        self._reaper_task: asyncio.Task[None] | None = None
        self._stop_reaper = asyncio.Event()

        # Atomic lock script:
        # 1) Ensure slot is in available pool
        # 2) Remove it from pool
        # 3) Create lock key with TTL
        # 4) Store expiry timestamp in ZSET for automatic restoration tracking
        self._lock_script = self._redis.register_script(
            """
            local available_key = KEYS[1]
            local lock_key = KEYS[2]
            local expiry_index_key = KEYS[3]

            local slot_id = ARGV[1]
            local holder_id = ARGV[2]
            local ttl_seconds = tonumber(ARGV[3])

            if redis.call('SISMEMBER', available_key, slot_id) == 0 then
                return 0
            end

            redis.call('SREM', available_key, slot_id)

            local set_ok = redis.call('SET', lock_key, holder_id, 'EX', ttl_seconds, 'NX')
            if not set_ok then
                redis.call('SADD', available_key, slot_id)
                return 0
            end

            local now = redis.call('TIME')
            local now_seconds = tonumber(now[1])
            local expiry_at = now_seconds + ttl_seconds
            redis.call('ZADD', expiry_index_key, expiry_at, slot_id)

            return 1
            """
        )

    def _user_step_key(self, user_id: str) -> str:
        return f"{self.key_prefix}:user:{user_id}:step"

    def _slot_lock_key(self, slot_id: str) -> str:
        return f"{self.key_prefix}:slot:{slot_id}:lock"

    async def close(self) -> None:
        await self.stop_auto_release_worker()
        await self._redis.aclose()
        await self._pool.disconnect()

    async def add_slots_to_pool(self, slot_ids: Iterable[str]) -> int:
        slot_ids = [str(sid) for sid in slot_ids]
        if not slot_ids:
            return 0
        return await self._redis.sadd(self._available_slots_key, *slot_ids)

    async def set_user_current_step(self, user_id: str, step: str) -> None:
        """Set the user's current booking step with booking-window TTL."""
        await self._redis.set(
            self._user_step_key(user_id),
            step,
            ex=self.booking_ttl_seconds,
        )

    async def get_user_current_step(self, user_id: str) -> str | None:
        return await self._redis.get(self._user_step_key(user_id))

    async def lock_appointment_slot(self, *, slot_id: str, user_id: str) -> bool:
        """Lock a slot for up to booking_ttl_seconds.

        Returns True if lock acquired, False if slot is unavailable.
        """
        result = await self._lock_script(
            keys=[
                self._available_slots_key,
                self._slot_lock_key(slot_id),
                self._expiry_index_key,
            ],
            args=[str(slot_id), str(user_id), self.booking_ttl_seconds],
        )
        return bool(result)

    async def confirm_appointment_slot(self, *, slot_id: str, user_id: str) -> bool:
        """Confirm a lock so it is not returned to the pool.

        Returns False if the lock is missing or held by another user.
        """
        lock_key = self._slot_lock_key(slot_id)
        holder = await self._redis.get(lock_key)
        if holder is None or holder != str(user_id):
            return False

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.delete(lock_key)
            pipe.zrem(self._expiry_index_key, str(slot_id))
            await pipe.execute()
        return True

    async def release_appointment_slot(self, *, slot_id: str, user_id: str | None = None) -> bool:
        """Release a held slot back to the available pool.

        If user_id is provided, release only when held by that user.
        """
        lock_key = self._slot_lock_key(slot_id)
        holder = await self._redis.get(lock_key)
        if holder is None:
            # Already expired or already released. Keep idempotent behavior.
            await self._redis.zrem(self._expiry_index_key, str(slot_id))
            return False

        if user_id is not None and holder != str(user_id):
            return False

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.delete(lock_key)
            pipe.zrem(self._expiry_index_key, str(slot_id))
            pipe.sadd(self._available_slots_key, str(slot_id))
            await pipe.execute()
        return True

    async def reconcile_expired_locks(self, *, batch_size: int = 200) -> int:
        """Restore expired locks back into the available pool.

        Uses the expiry ZSET index to efficiently discover candidates,
        then verifies the lock key is truly absent before restoration.
        """
        now_ts = int(time.time())
        slot_ids = await self._redis.zrangebyscore(
            self._expiry_index_key,
            min="-inf",
            max=now_ts,
            start=0,
            num=batch_size,
        )
        if not slot_ids:
            return 0

        released = 0
        for slot_id in slot_ids:
            lock_exists = await self._redis.exists(self._slot_lock_key(slot_id))
            if lock_exists:
                continue

            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.sadd(self._available_slots_key, slot_id)
                pipe.zrem(self._expiry_index_key, slot_id)
                await pipe.execute()
            released += 1

        return released

    async def start_auto_release_worker(self, *, interval_seconds: float = 1.0) -> None:
        """Start background task that continuously reclaims expired slot holds."""
        if self._reaper_task and not self._reaper_task.done():
            return

        self._stop_reaper.clear()

        async def _worker() -> None:
            while not self._stop_reaper.is_set():
                try:
                    await self.reconcile_expired_locks()
                except Exception:
                    # Keep worker alive; production systems should route this to logging.
                    pass
                await asyncio.sleep(interval_seconds)

        self._reaper_task = asyncio.create_task(_worker())

    async def stop_auto_release_worker(self) -> None:
        """Stop background lock-reaper task gracefully."""
        if not self._reaper_task:
            return
        self._stop_reaper.set()
        await self._reaper_task
        self._reaper_task = None
