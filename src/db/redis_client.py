"""Async Redis helpers for Phase 2 market streams and websocket fanout."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

import redis.asyncio as aioredis

from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

STREAM_MARKET_TICKS = "market:ticks"
STREAM_MAX_LEN = 50_000
CONSUMER_GROUP = "orchestrator"
CONSUMER_NAME = "worker-1"
CHANNEL_WS_BROADCAST = "ws:broadcast"

KEY_CIRCUIT_STATE = "cb:state:{exchange}"
KEY_CIRCUIT_FAILURES = "cb:failures:{exchange}"
KEY_LATEST_TICK = "market:latest:{symbol}"

CB_CLOSED = "CLOSED"
CB_OPEN = "OPEN"
CB_HALF_OPEN = "HALF_OPEN"
CB_FAILURE_THRESHOLD = 5
CB_OPEN_TTL_SECONDS = 60
CB_FAILURE_WINDOW = 60

_pool: Optional[aioredis.ConnectionPool] = None


def _get_pool() -> aioredis.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=20,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
    return _pool


def get_redis() -> aioredis.Redis:
    return aioredis.Redis(connection_pool=_get_pool())


async def ping() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.disconnect()
        _pool = None


async def publish_tick(tick: dict) -> str:
    redis = get_redis()
    entry_id = await redis.xadd(
        STREAM_MARKET_TICKS,
        {
            "symbol": tick["symbol"],
            "timestamp": str(tick["timestamp"]),
            "open": str(tick["open"]),
            "high": str(tick["high"]),
            "low": str(tick["low"]),
            "close": str(tick["close"]),
            "volume": str(tick["volume"]),
            "source": tick.get("source", "websocket"),
        },
        maxlen=STREAM_MAX_LEN,
        approximate=True,
    )
    latest_key = KEY_LATEST_TICK.format(symbol=tick["symbol"])
    await redis.hset(latest_key, mapping={"close": str(tick["close"]), "timestamp": str(tick["timestamp"])})
    await redis.expire(latest_key, 120)
    return entry_id


async def get_latest_price(symbol: str) -> Optional[float]:
    data = await get_redis().hgetall(KEY_LATEST_TICK.format(symbol=symbol))
    if data and "close" in data:
        return float(data["close"])
    return None


async def ensure_consumer_group() -> None:
    redis = get_redis()
    try:
        await redis.xgroup_create(STREAM_MARKET_TICKS, CONSUMER_GROUP, id="$", mkstream=True)
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def consume_ticks(callback, block_ms: int = 5000) -> None:
    redis = get_redis()
    await ensure_consumer_group()
    while True:
        try:
            messages = await redis.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {STREAM_MARKET_TICKS: ">"},
                count=1,
                block=block_ms,
            )
            if not messages:
                continue

            for _stream_name, entries in messages:
                for entry_id, fields in entries:
                    tick = {
                        "symbol": fields["symbol"],
                        "timestamp": int(fields["timestamp"]),
                        "open": float(fields["open"]),
                        "high": float(fields["high"]),
                        "low": float(fields["low"]),
                        "close": float(fields["close"]),
                        "volume": float(fields["volume"]),
                        "source": fields.get("source", "websocket"),
                    }
                    try:
                        await callback(tick)
                    finally:
                        await redis.xack(STREAM_MARKET_TICKS, CONSUMER_GROUP, entry_id)
        except aioredis.ConnectionError as exc:
            logger.warning(f"[REDIS] connection lost: {exc}")
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            break


async def broadcast(payload: dict) -> None:
    await get_redis().publish(CHANNEL_WS_BROADCAST, json.dumps(payload, default=str))


@asynccontextmanager
async def subscribe_broadcast() -> AsyncIterator[Any]:
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL_WS_BROADCAST)
    try:
        yield pubsub
    finally:
        await pubsub.unsubscribe(CHANNEL_WS_BROADCAST)
        await pubsub.close()


async def cb_record_failure(exchange: str) -> str:
    redis = get_redis()
    failures = await redis.incr(KEY_CIRCUIT_FAILURES.format(exchange=exchange))
    await redis.expire(KEY_CIRCUIT_FAILURES.format(exchange=exchange), CB_FAILURE_WINDOW)
    if failures >= CB_FAILURE_THRESHOLD:
        await redis.set(KEY_CIRCUIT_STATE.format(exchange=exchange), CB_OPEN, ex=CB_OPEN_TTL_SECONDS)
        return CB_OPEN
    return CB_CLOSED


async def cb_record_success(exchange: str) -> None:
    redis = get_redis()
    await redis.delete(KEY_CIRCUIT_FAILURES.format(exchange=exchange))
    await redis.set(KEY_CIRCUIT_STATE.format(exchange=exchange), CB_CLOSED)


async def cb_get_state(exchange: str) -> str:
    state = await get_redis().get(KEY_CIRCUIT_STATE.format(exchange=exchange))
    return state or CB_CLOSED


async def cb_is_open(exchange: str) -> bool:
    return await cb_get_state(exchange) == CB_OPEN


async def set_with_ttl(key: str, value: Any, ttl_seconds: int) -> None:
    await get_redis().set(key, value, ex=ttl_seconds)


async def get_value(key: str) -> Optional[str]:
    return await get_redis().get(key)


async def delete_key(key: str) -> None:
    await get_redis().delete(key)
