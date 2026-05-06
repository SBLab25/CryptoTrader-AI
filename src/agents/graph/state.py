"""Trading state passed through the Phase 3 graph."""

from typing import Any


def _keep_last(existing: Any, new: Any) -> Any:
    return new if new is not None else existing


def _append_errors(existing: list[str] | None, new: list[str] | None) -> list[str]:
    return (existing or []) + (new or [])


TradingState = dict[str, Any]
