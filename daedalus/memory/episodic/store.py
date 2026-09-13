from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..embedding import HashingEmbedder, InMemoryVectorIndex


@dataclass(slots=True)
class Episode:
    id: str
    tick: int
    intention_id: str
    intention_kind: str
    intention_source: str
    goal_id: str | None
    tool: str
    args: dict[str, Any]
    success: bool
    expected_success: float
    reward: float
    information_gain: float
    cost: float
    damage: float
    surprise: float
    note: str
    context: dict[str, Any] = field(default_factory=dict)
    consolidated: bool = False

    @property
    def signature(self) -> str:
        return f"{self.intention_kind}:{self.tool}"

    def describe(self) -> str:
        outcome = "succeeded" if self.success else "failed"
        return f"{self.intention_kind} {self.tool} {' '.join(map(str, self.args.values()))} {outcome} {self.note}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("reward", "information_gain", "cost", "damage", "surprise", "expected_success"):
            d[k] = round(d[k], 4)
        return d


class EpisodicMemory:
    def __init__(self, capacity: int = 4000) -> None:
        self.capacity = capacity
        self.episodes: dict[str, Episode] = {}
        self.order: list[str] = []
        self.embedder = HashingEmbedder()
        self.index = InMemoryVectorIndex()
        self._seq = 0
        self.pruned = 0

    def record(self, **kwargs: Any) -> Episode:
        self._seq += 1
        ep = Episode(id=f"ep{self._seq}", **kwargs)
        self.episodes[ep.id] = ep
        self.order.append(ep.id)
        self.index.add(ep.id, self.embedder.embed(ep.describe()))
        return ep

    def recent(self, n: int = 20) -> list[Episode]:
        return [self.episodes[i] for i in self.order[-n:]]

    def unconsolidated(self) -> list[Episode]:
        return [e for e in self.episodes.values() if not e.consolidated]

    def recall(self, text: str, k: int = 5) -> list[tuple[Episode, float]]:
        hits = self.index.search(self.embedder.embed(text), k)
        return [(self.episodes[i], s) for i, s in hits if i in self.episodes]

    def prune(self) -> int:
        """Forget consolidated, unsurprising episodes beyond capacity (salience-based forgetting)."""
        overflow = len(self.order) - self.capacity
        if overflow <= 0:
            return 0
        removed = 0
        keep: list[str] = []
        for eid in self.order:
            ep = self.episodes[eid]
            if removed < overflow and ep.consolidated and ep.surprise < 0.5:
                del self.episodes[eid]
                self.index.remove(eid)
                removed += 1
            else:
                keep.append(eid)
        self.order = keep
        self.pruned += removed
        return removed
