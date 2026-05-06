"""Qdrant compatibility layer with an in-memory fallback client."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from src.core.config import settings

COLLECTION_SIGNAL_MEMORY = "signal_memory"
VECTOR_DIM = 1024


@dataclass
class PointStruct:
    id: str
    vector: list[float]
    payload: dict


@dataclass
class _Collection:
    points: dict[str, PointStruct] = field(default_factory=dict)


class _InMemoryQdrantClient:
    def __init__(self):
        self._collections: dict[str, _Collection] = {}

    def get_collections(self):
        return SimpleNamespace(collections=[SimpleNamespace(name=name) for name in self._collections])

    def create_collection(self, collection_name: str, **_kwargs):
        self._collections.setdefault(collection_name, _Collection())

    def create_payload_index(self, **_kwargs):
        return None

    def get_collection(self, collection_name: str):
        collection = self._collections.setdefault(collection_name, _Collection())
        return SimpleNamespace(points_count=len(collection.points), status="green")

    def upsert(self, collection_name: str, points: list[PointStruct], **_kwargs):
        collection = self._collections.setdefault(collection_name, _Collection())
        for point in points:
            collection.points[str(point.id)] = point

    def set_payload(self, collection_name: str, payload: dict, points: list[str], **_kwargs):
        collection = self._collections.setdefault(collection_name, _Collection())
        for point_id in points:
            if str(point_id) in collection.points:
                collection.points[str(point_id)].payload.update(payload)

    def retrieve(self, collection_name: str, ids: list[str], with_vectors: bool = False):
        collection = self._collections.setdefault(collection_name, _Collection())
        results = []
        for point_id in ids:
            point = collection.points.get(str(point_id))
            if point is None:
                continue
            results.append(point if with_vectors else PointStruct(id=point.id, vector=[], payload=dict(point.payload)))
        return results

    def search(self, collection_name: str, query_vector: list[float], limit: int = 5, score_threshold: float = 0.0, with_payload: bool = True, query_filter: Any = None, **_kwargs):
        collection = self._collections.setdefault(collection_name, _Collection())
        hits = []
        for point in collection.points.values():
            if not _payload_matches(point.payload, query_filter):
                continue
            score = _cosine_similarity(query_vector, point.vector)
            if score < score_threshold:
                continue
            payload = dict(point.payload) if with_payload else {}
            hits.append(SimpleNamespace(id=point.id, score=score, payload=payload, vector=point.vector))
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:limit]

    def count(self, collection_name: str, count_filter: Any = None):
        collection = self._collections.setdefault(collection_name, _Collection())
        count = sum(1 for point in collection.points.values() if _payload_matches(point.payload, count_filter))
        return SimpleNamespace(count=count)


def _payload_matches(payload: dict, query_filter: Any) -> bool:
    if query_filter is None:
        return True
    if isinstance(query_filter, dict):
        must = query_filter.get("must", [])
    else:
        must = getattr(query_filter, "must", []) or []
    for condition in must:
        if isinstance(condition, tuple) and len(condition) == 2:
            key, value = condition
        elif isinstance(condition, dict):
            key, value = condition.get("key"), condition.get("value")
        else:
            key = getattr(condition, "key", None)
            value = getattr(getattr(condition, "match", None), "value", None)
        if key is None:
            continue
        if payload.get(key) != value:
            return False
    return True


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


_client = None
_qdrant_available: bool | None = None


def get_qdrant_client():
    global _client
    if _client is None:
        try:
            from qdrant_client import QdrantClient

            _client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, timeout=10, prefer_grpc=False)
        except Exception:
            _client = _InMemoryQdrantClient()
    return _client


def check_qdrant_health() -> bool:
    global _qdrant_available
    try:
        get_qdrant_client().get_collections()
        _qdrant_available = True
    except Exception:
        _qdrant_available = False
    return bool(_qdrant_available)


def is_qdrant_available() -> bool:
    global _qdrant_available
    if _qdrant_available is None:
        return check_qdrant_health()
    return _qdrant_available


def ensure_collections() -> None:
    client = get_qdrant_client()
    client.create_collection(collection_name=COLLECTION_SIGNAL_MEMORY, vectors_config={"size": VECTOR_DIM})
    for field_name in ("symbol", "strategy", "action", "outcome", "mode"):
        client.create_payload_index(collection_name=COLLECTION_SIGNAL_MEMORY, field_name=field_name, field_schema="keyword")


def get_collection_info() -> dict:
    try:
        info = get_qdrant_client().get_collection(COLLECTION_SIGNAL_MEMORY)
        return {"available": True, "points_count": info.points_count, "status": str(info.status), "vector_dim": VECTOR_DIM}
    except Exception as exc:
        return {"available": False, "error": str(exc)}
