"""Async circuit breaker for exchange-facing operations."""

from __future__ import annotations

import time

from src.utils.logger import get_logger

logger = get_logger(__name__)

FAILURE_THRESHOLD = 5
FAILURE_WINDOW_S = 60
OPEN_TIMEOUT_S = 60

_KEY_STATE = "cb:state:{exchange}"
_KEY_FAILURES = "cb:failures:{exchange}"
_KEY_OPENED_AT = "cb:opened_at:{exchange}"


def get_redis():
    from src.db.redis_client import get_redis as _get_redis

    return _get_redis()


class CircuitOpenError(Exception):
    def __init__(self, exchange: str):
        super().__init__(
            f"Circuit breaker is OPEN for exchange '{exchange}'. "
            "Exchange may be unreachable. Trading is temporarily blocked."
        )
        self.exchange = exchange


class CircuitBreaker:
    STATE_CLOSED = "CLOSED"
    STATE_OPEN = "OPEN"
    STATE_HALF_OPEN = "HALF_OPEN"

    def __init__(self, exchange: str):
        self.exchange = exchange
        self._key_state = _KEY_STATE.format(exchange=exchange)
        self._key_failures = _KEY_FAILURES.format(exchange=exchange)
        self._key_opened_at = _KEY_OPENED_AT.format(exchange=exchange)

    async def __aenter__(self) -> "CircuitBreaker":
        state = await self.get_state()
        if state == self.STATE_OPEN:
            if await self._should_try_half_open():
                await self._set_state(self.STATE_HALF_OPEN)
                logger.info(f"[CB] {self.exchange} -> HALF_OPEN")
            else:
                raise CircuitOpenError(self.exchange)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None:
            await self.record_success()
        elif not isinstance(exc_val, CircuitOpenError):
            await self.record_failure()
        return False

    async def get_state(self) -> str:
        try:
            state = await get_redis().get(self._key_state)
            return state or self.STATE_CLOSED
        except Exception:
            return self.STATE_CLOSED

    async def record_failure(self) -> None:
        try:
            redis = get_redis()
            failures = await redis.incr(self._key_failures)
            await redis.expire(self._key_failures, FAILURE_WINDOW_S)
            current_state = await self.get_state()
            if current_state == self.STATE_HALF_OPEN or failures >= FAILURE_THRESHOLD:
                await self._open()
        except Exception as exc:
            logger.warning(f"[CB] failure accounting skipped: {exc}")

    async def record_success(self) -> None:
        try:
            redis = get_redis()
            current_state = await self.get_state()
            await redis.delete(self._key_failures)
            await self._set_state(self.STATE_CLOSED)
            if current_state == self.STATE_HALF_OPEN:
                await self._notify_recovery()
        except Exception as exc:
            logger.warning(f"[CB] success accounting skipped: {exc}")

    async def _open(self) -> None:
        redis = get_redis()
        await self._set_state(self.STATE_OPEN)
        await redis.set(self._key_opened_at, str(time.time()), ex=OPEN_TIMEOUT_S * 10)
        await self._notify_open()

    async def _set_state(self, state: str) -> None:
        await get_redis().set(self._key_state, state, ex=3600)

    async def _should_try_half_open(self) -> bool:
        try:
            opened_at = await get_redis().get(self._key_opened_at)
            if opened_at is None:
                return True
            return (time.time() - float(opened_at)) >= OPEN_TIMEOUT_S
        except Exception:
            return True

    async def _notify_open(self) -> None:
        try:
            from src.notifications.ntfy import notify_circuit_open

            await notify_circuit_open(self.exchange)
        except Exception:
            return

    async def _notify_recovery(self) -> None:
        try:
            from src.notifications.ntfy import notify_circuit_closed

            await notify_circuit_closed(self.exchange)
        except Exception:
            return

    @classmethod
    async def is_open(cls, exchange: str) -> bool:
        return await cls(exchange).get_state() == cls.STATE_OPEN

    @classmethod
    async def get_all_states(cls, exchanges: list[str]) -> dict[str, str]:
        result = {}
        for exchange in exchanges:
            result[exchange] = await cls(exchange).get_state()
        return result

    @classmethod
    async def force_open(cls, exchange: str) -> None:
        await cls(exchange)._open()

    @classmethod
    async def force_close(cls, exchange: str) -> None:
        breaker = cls(exchange)
        await breaker.record_success()
        logger.info(f"[CB] {exchange} force-closed")
