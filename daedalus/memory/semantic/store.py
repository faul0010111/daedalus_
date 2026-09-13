from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Knowledge:
    id: str
    signature: str
    kind: str  # statistic | lesson | team_outcome | source_model
    statement: str
    confidence: float
    support: int
    created_tick: int
    updated_tick: int
    episodes: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["episodes"] = d["episodes"][-8:]
        d["confidence"] = round(self.confidence, 3)
        return d


class SemanticMemory:
    def __init__(self) -> None:
        self.items: dict[str, Knowledge] = {}
        self._seq = 0

    def upsert(self, signature: str, kind: str, statement: str, confidence: float, support: int,
               tick: int, episodes: list[str] | None = None, **data: Any) -> Knowledge:
        existing = self.items.get(signature)
        if existing:
            existing.statement = statement
            existing.confidence = confidence
            existing.support = support
            existing.updated_tick = tick
            existing.episodes.extend(episodes or [])
            del existing.episodes[:-30]
            existing.data.update(data)
            return existing
        self._seq += 1
        k = Knowledge(f"k{self._seq}", signature, kind, statement, confidence, support, tick, tick,
                      list(episodes or [])[-30:], dict(data))
        self.items[signature] = k
        return k

    def get(self, signature: str) -> Knowledge | None:
        return self.items.get(signature)
