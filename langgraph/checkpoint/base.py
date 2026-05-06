from dataclasses import dataclass, field
from typing import Any


@dataclass
class Checkpoint:
    v: int
    id: str
    ts: str
    channel_values: dict[str, Any] = field(default_factory=dict)
    channel_versions: dict[str, Any] = field(default_factory=dict)
    versions_seen: dict[str, Any] = field(default_factory=dict)
    pending_sends: list[Any] = field(default_factory=list)


@dataclass
class CheckpointMetadata:
    source: str
    step: int = 0
    writes: dict[str, Any] = field(default_factory=dict)
