"""Minimal Redis-backed checkpointer for Phase 3."""

from __future__ import annotations

import json

from src.db.redis_client import get_redis


class RedisCheckpointer:
    def _key(self, config: dict) -> str:
        thread_id = (config or {}).get("configurable", {}).get("thread_id", "default")
        return f"graph:checkpoint:{thread_id}"

    async def aget_tuple(self, config: dict):
        raw = await get_redis().get(self._key(config))
        if raw is None:
            return None
        return json.loads(raw)

    async def aput(self, config: dict, checkpoint, metadata, _new_versions):
        payload = {"checkpoint": checkpoint, "metadata": metadata}
        await get_redis().set(self._key(config), json.dumps(payload, default=str))
        return config
