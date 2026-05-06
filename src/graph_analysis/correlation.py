"""Asset correlation helpers with no hard dependency on NetworkX/SciPy."""

from __future__ import annotations

import asyncio
import math
import pickle
from dataclasses import dataclass, field

from src.core.config import settings

EDGE_THRESHOLD = 0.60
RISK_THRESHOLD = 0.75
MAX_CORRELATED = 2
MIN_PRICE_POINTS = 20
WINDOW_POINTS = 30
GRAPH_CACHE_KEY = "graph:correlation"
GRAPH_CACHE_TTL = 3600


@dataclass
class SimpleGraph:
    adjacency: dict[str, dict[str, dict]] = field(default_factory=dict)

    def add_node(self, node: str) -> None:
        self.adjacency.setdefault(node, {})

    def add_nodes_from(self, nodes: list[str]) -> None:
        for node in nodes:
            self.add_node(node)

    def add_edge(self, left: str, right: str, **attrs) -> None:
        self.add_node(left)
        self.add_node(right)
        self.adjacency[left][right] = dict(attrs)
        self.adjacency[right][left] = dict(attrs)

    def has_node(self, node: str) -> bool:
        return node in self.adjacency

    def has_edge(self, left: str, right: str) -> bool:
        return left in self.adjacency and right in self.adjacency[left]

    def neighbors(self, node: str):
        return iter(self.adjacency.get(node, {}))

    def number_of_nodes(self) -> int:
        return len(self.adjacency)

    def number_of_edges(self) -> int:
        return sum(len(edges) for edges in self.adjacency.values()) // 2

    def nodes(self):
        return list(self.adjacency.keys())

    def edges(self, data: bool = False):
        seen: set[tuple[str, str]] = set()
        items = []
        for left, edges in self.adjacency.items():
            for right, attrs in edges.items():
                key = tuple(sorted((left, right)))
                if key in seen:
                    continue
                seen.add(key)
                items.append((left, right, dict(attrs)) if data else (left, right))
        return items

    def __getitem__(self, node: str):
        return self.adjacency[node]


def _new_graph():
    try:
        import networkx as nx

        return nx.Graph()
    except Exception:
        return SimpleGraph()


def _pearson(series_a: list[float], series_b: list[float]) -> float:
    length = min(len(series_a), len(series_b))
    if length < 2:
        return 0.0
    left = series_a[-length:]
    right = series_b[-length:]
    mean_left = sum(left) / length
    mean_right = sum(right) / length
    num = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    den_left = math.sqrt(sum((a - mean_left) ** 2 for a in left))
    den_right = math.sqrt(sum((b - mean_right) ** 2 for b in right))
    if den_left == 0 or den_right == 0:
        return 0.0
    return num / (den_left * den_right)


async def build_correlation_graph(symbols: list[str] | None = None):
    symbols = symbols or settings.symbol_list
    graph = _new_graph()
    graph.add_nodes_from(symbols)
    series_by_symbol: dict[str, list[float]] = {}
    for symbol in symbols:
        prices = await _fetch_prices(symbol, WINDOW_POINTS)
        if len(prices) >= MIN_PRICE_POINTS:
            series_by_symbol[symbol] = prices
    keys = list(series_by_symbol.keys())
    for index, left in enumerate(keys):
        for right in keys[index + 1 :]:
            corr = _pearson(series_by_symbol[left], series_by_symbol[right])
            if abs(corr) >= EDGE_THRESHOLD:
                graph.add_edge(left, right, weight=round(float(corr), 4))
    return graph


async def save_graph_to_cache(graph) -> None:
    try:
        from src.db.redis_client import get_redis

        await get_redis().set(GRAPH_CACHE_KEY, pickle.dumps(graph), ex=GRAPH_CACHE_TTL)
    except Exception:
        return


async def load_graph_from_cache():
    try:
        from src.db.redis_client import get_redis

        data = await get_redis().get(GRAPH_CACHE_KEY)
        return None if data is None else pickle.loads(data)
    except Exception:
        return None


async def get_graph():
    graph = await load_graph_from_cache()
    if graph is not None:
        return graph
    graph = await build_correlation_graph()
    await save_graph_to_cache(graph)
    return graph


async def check_correlated_exposure(symbol: str, open_positions: list[str], threshold: float = RISK_THRESHOLD, max_correlated: int = MAX_CORRELATED) -> tuple[bool, str]:
    if not open_positions:
        return True, ""
    graph = await get_graph()
    if not graph.has_node(symbol):
        return True, ""
    correlated = [
        neighbor
        for neighbor in graph.neighbors(symbol)
        if neighbor in open_positions and abs(graph[symbol][neighbor].get("weight", 0.0)) >= threshold
    ]
    if len(correlated) >= max_correlated:
        return False, f"{symbol} is too correlated with open positions {correlated}"
    return True, ""


async def rebuild_loop(interval_seconds: int = 3600) -> None:
    while True:
        graph = await build_correlation_graph()
        await save_graph_to_cache(graph)
        await asyncio.sleep(interval_seconds)


async def get_graph_info() -> dict:
    graph = await load_graph_from_cache()
    if graph is None:
        return {"available": False, "reason": "not_built_yet"}
    return {
        "available": True,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "node_list": list(graph.nodes()),
        "top_correlations": [
            {"symbols": [left, right], "correlation": attrs["weight"]}
            for left, right, attrs in sorted(graph.edges(data=True), key=lambda edge: abs(edge[2].get("weight", 0)), reverse=True)[:5]
        ],
    }


async def _fetch_prices(symbol: str, points: int) -> list[float]:
    from src.db.database import get_db_session
    from src.db.timescale import OHLCVStore

    async with get_db_session() as session:
        candles = await OHLCVStore.get_latest(session, symbol=symbol, limit=points)
    return [float(candle["close"]) for candle in candles]
