"""Tiny in-repo graph runtime compatible with the Phase 3 workflow needs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

START = "__start__"
END = "__end__"


@dataclass
class CompiledGraph:
    nodes: dict[str, Callable]
    entry_point: str
    edges: dict[str, str]
    conditional_edges: dict[str, tuple[Callable, dict[str, str]]]
    checkpointer: Any = None

    async def ainvoke(self, state: dict, config: dict | None = None) -> dict:
        current = self.entry_point
        merged = dict(state)
        while current != END:
            output = await self.nodes[current](merged)
            merged = _merge_state(merged, output)
            if self.checkpointer is not None and hasattr(self.checkpointer, "aput"):
                await self.checkpointer.aput(config or {}, {"node": current, "state": merged}, {"source": "graph"}, {})
            if current in self.conditional_edges:
                router, mapping = self.conditional_edges[current]
                current = mapping[router(merged)]
            else:
                current = self.edges.get(current, END)
        return merged


def _merge_state(existing: dict, new: dict | None) -> dict:
    if not new:
        return existing
    merged = dict(existing)
    for key, value in new.items():
        if key == "errors":
            merged[key] = (merged.get(key) or []) + (value or [])
        elif key == "node_timings":
            timings = dict(merged.get("node_timings") or {})
            timings.update(value or {})
            merged[key] = timings
        else:
            merged[key] = value
    return merged


class StateGraph:
    def __init__(self, _state_type: Any):
        self.nodes: dict[str, Callable] = {}
        self._entry_point: str | None = None
        self._edges: dict[str, str] = {}
        self._conditional_edges: dict[str, tuple[Callable, dict[str, str]]] = {}

    def add_node(self, name: str, fn: Callable) -> None:
        self.nodes[name] = fn

    def set_entry_point(self, name: str) -> None:
        self._entry_point = name

    def add_edge(self, source: str, dest: str) -> None:
        self._edges[source] = dest

    def add_conditional_edges(self, source: str, router: Callable, mapping: dict[str, str]) -> None:
        self._conditional_edges[source] = (router, mapping)

    def compile(self, checkpointer: Any = None, **_kwargs: Any) -> CompiledGraph:
        if self._entry_point is None:
            raise ValueError("Entry point not set")
        return CompiledGraph(
            nodes=self.nodes,
            entry_point=self._entry_point,
            edges=self._edges,
            conditional_edges=self._conditional_edges,
            checkpointer=checkpointer,
        )
