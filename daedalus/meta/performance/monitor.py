"""Performance monitor: the system's view of its own functioning."""
from __future__ import annotations

import math
from collections import Counter, deque
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TickRecord:
    tick: int
    focal_kind: str | None
    tool: str | None
    success: bool | None
    reward: float
    info_gain: float
    energy: float
    progress: float
    internal_ops: int


class PerformanceMonitor:
    def __init__(self, window: int = 60) -> None:
        self.window = window
        self.records: deque[TickRecord] = deque(maxlen=window * 5)
        self.intention_outcomes: deque[tuple[int, str, bool]] = deque(maxlen=200)
        self.series: deque[dict[str, Any]] = deque(maxlen=400)

    def record_tick(self, rec: TickRecord) -> None:
        self.records.append(rec)

    def record_intention(self, tick: int, kind: str, success: bool) -> None:
        self.intention_outcomes.append((tick, kind, success))

    def recent(self, n: int | None = None) -> list[TickRecord]:
        n = n or self.window
        return list(self.records)[-n:]

    def summary(self) -> dict[str, Any]:
        recs = self.recent()
        actions = [r for r in recs if r.tool]
        failures = [r for r in actions if r.success is False]
        kinds = Counter(r.focal_kind for r in recs if r.focal_kind)
        total = sum(kinds.values()) or 1
        entropy = -sum((c / total) * math.log2(c / total) for c in kinds.values())
        tools = Counter(r.tool for r in actions)
        epistemic = tools.get("scan", 0) + tools.get("probe", 0)
        advance = [(k, ok) for t, k, ok in self.intention_outcomes if k == "advance_goal"][-12:]
        return {
            "window": len(recs),
            "success_rate": round(1 - len(failures) / len(actions), 3) if actions else None,
            "failure_rate": round(len(failures) / len(actions), 3) if actions else 0.0,
            "reward_per_tick": round(sum(r.reward for r in recs) / max(1, len(recs)), 4),
            "info_gain_per_tick": round(sum(r.info_gain for r in recs) / max(1, len(recs)), 4),
            "energy_per_tick": round(sum(r.energy for r in recs) / max(1, len(recs)), 3),
            "progress": round(sum(r.progress for r in recs), 3),
            "attention_entropy": round(entropy, 3),
            "kind_share": {k: round(v / total, 3) for k, v in kinds.items()},
            "tool_calls": dict(tools),
            "epistemic_share": round(epistemic / max(1, len(actions)), 3),
            "internal_ops": sum(r.internal_ops for r in recs),
            "idle_ticks": sum(1 for r in recs if r.focal_kind is None),
            "advance_failure_rate": round(sum(1 for _, ok in advance if not ok) / len(advance), 3) if advance else 0.0,
            "advance_samples": len(advance),
        }

    def stagnation(self) -> float:
        recs = self.recent()
        if len(recs) < self.window:
            return 0.0
        progress = sum(r.progress for r in recs)
        info = sum(r.info_gain for r in recs)
        if progress > 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - info / 6.0))

    def failure_pressure(self) -> float:
        actions = [r for r in self.recent(30) if r.tool]
        if not actions:
            return 0.0
        return sum(1 for r in actions if r.success is False) / len(actions)
