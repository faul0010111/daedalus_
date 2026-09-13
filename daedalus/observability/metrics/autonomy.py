"""Experimental autonomy metrics. Counters are incremented where the events actually happen."""
from __future__ import annotations

from collections import Counter, deque
from typing import Any

AUTONOMY_KEYS = ("self_initiated_actions", "emergent_goals", "knowledge_gaps_resolved", "strategy_adaptations",
                 "agent_topology_changes", "reflection_events", "uncertainty_reduction", "goal_progress_rate")


class AutonomyMetrics:
    def __init__(self) -> None:
        self.counters: Counter[str] = Counter()
        self.series: deque[dict[str, Any]] = deque(maxlen=600)

    def inc(self, name: str, amount: float = 1) -> None:
        self.counters[name] += amount

    def sample(self, tick: int, extra: dict[str, Any]) -> None:
        self.series.append({"tick": tick, **{k: self.counters.get(k, 0) for k in
                                             ("self_initiated_actions", "actions", "emergent_goals",
                                              "knowledge_gaps_resolved", "strategy_adaptations",
                                              "agent_topology_changes", "reflection_events", "goals_achieved")},
                            **extra})

    def autonomy(self, tick: int, uncertainty_reduction: float) -> dict[str, Any]:
        actions = self.counters.get("actions", 0)
        return {
            "self_initiated_actions": self.counters.get("self_initiated_actions", 0),
            "self_initiated_ratio": round(self.counters.get("self_initiated_actions", 0) / actions, 3) if actions else 0.0,
            "emergent_goals": self.counters.get("emergent_goals", 0),
            "knowledge_gaps_resolved": self.counters.get("knowledge_gaps_resolved", 0),
            "strategy_adaptations": self.counters.get("strategy_adaptations", 0),
            "strategy_trials": self.counters.get("strategy_trials", 0),
            "agent_topology_changes": self.counters.get("agent_topology_changes", 0),
            "reflection_events": self.counters.get("reflection_events", 0),
            "uncertainty_reduction": round(uncertainty_reduction, 2),
            "goal_progress_rate": round(100 * self.counters.get("goals_achieved", 0) / max(1, tick), 3),
            "contradictions_resolved": self.counters.get("contradictions_resolved", 0),
            "diagnoses": self.counters.get("diagnoses", 0),
            "preemptions": self.counters.get("preemptions", 0),
            "internal_operations": self.counters.get("internal_operations", 0),
        }
