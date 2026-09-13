from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StrategyStats:
    point: str
    variant: str
    n: int = 0
    mean: float = 0.0
    _m2: float = 0.0

    def add(self, reward: float) -> None:
        self.n += 1
        d = reward - self.mean
        self.mean += d / self.n
        self._m2 += d * (reward - self.mean)

    @property
    def stderr(self) -> float:
        if self.n < 2:
            return 1.0
        return math.sqrt(max(self._m2 / (self.n - 1), 1e-9) / self.n)

    def to_dict(self) -> dict[str, Any]:
        return {"point": self.point, "variant": self.variant, "n": self.n,
                "mean": round(self.mean, 4), "stderr": round(self.stderr, 4)}


@dataclass(slots=True)
class StrategyAudit:
    tick: int
    point: str
    incumbent: str
    candidate: str
    decision: str  # trial | adopted | rejected
    incumbent_score: float | None = None
    candidate_score: float | None = None
    rationale: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"tick": self.tick, "point": self.point, "incumbent": self.incumbent,
                "candidate": self.candidate, "decision": self.decision,
                "incumbent_score": None if self.incumbent_score is None else round(self.incumbent_score, 4),
                "candidate_score": None if self.candidate_score is None else round(self.candidate_score, 4),
                "rationale": self.rationale, "evidence": self.evidence}


class StrategicMemory:
    def __init__(self) -> None:
        self.stats: dict[tuple[str, str], StrategyStats] = {}
        self.audit: list[StrategyAudit] = []

    def record(self, point: str, variant: str, reward: float) -> None:
        key = (point, variant)
        if key not in self.stats:
            self.stats[key] = StrategyStats(point, variant)
        self.stats[key].add(reward)

    def get(self, point: str, variant: str) -> StrategyStats | None:
        return self.stats.get((point, variant))
