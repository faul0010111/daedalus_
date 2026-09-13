from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

FEATURES = (
    "goal_alignment", "expected_value", "urgency", "uncertainty_reduction", "novelty",
    "confidence", "resource_cost", "expected_information_gain", "risk", "historical_success_rate",
    "resource_return",
)


class IntentionKind(str, Enum):
    ADVANCE_GOAL = "advance_goal"
    EXPLORE = "explore"
    RESOLVE_CONTRADICTION = "resolve_contradiction"
    VALIDATE = "validate"
    EXPLOIT_OPPORTUNITY = "exploit_opportunity"
    MITIGATE_RISK = "mitigate_risk"
    REFLECT = "reflect"
    ADAPT_STRATEGY = "adapt_strategy"
    CONSOLIDATE_MEMORY = "consolidate_memory"
    REORGANIZE = "reorganize"

    @property
    def internal(self) -> bool:
        return self in (IntentionKind.REFLECT, IntentionKind.ADAPT_STRATEGY,
                        IntentionKind.CONSOLIDATE_MEMORY, IntentionKind.REORGANIZE)


class IntentionStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass(slots=True)
class IntentionFeatures:
    goal_alignment: float = 0.0
    expected_value: float = 0.0
    urgency: float = 0.0
    uncertainty_reduction: float = 0.0
    novelty: float = 0.0
    confidence: float = 0.5
    resource_cost: float = 0.0
    expected_information_gain: float = 0.0
    risk: float = 0.0
    historical_success_rate: float = 0.5
    resource_return: float = 0.0   # how much of the scarce resource this intention gives back

    def clamp(self) -> "IntentionFeatures":
        for name in FEATURES:
            setattr(self, name, max(0.0, min(1.0, float(getattr(self, name)))))
        return self

    def to_dict(self) -> dict[str, float]:
        return {k: round(v, 3) for k, v in asdict(self).items()}


@dataclass
class Intention:
    key: str
    kind: IntentionKind
    description: str
    target: dict[str, Any]
    features: IntentionFeatures
    sources: set[str] = field(default_factory=set)
    goal_id: str | None = None
    id: str = ""
    status: IntentionStatus = IntentionStatus.CANDIDATE
    created_tick: int = 0
    last_proposed_tick: int = 0
    activated_tick: int | None = None
    support: int = 1
    steps: int = 0
    step_failures: int = 0
    consecutive_failures: int = 0
    reward: float = 0.0
    selections: int = 0
    last_score: float = 0.0
    plan: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    plan_revision: int = -1
    strategies: dict[str, str] = field(default_factory=dict)
    outcome: str = ""
    max_steps: int = 60

    @property
    def origin(self) -> str:
        return sorted(self.sources)[0] if self.sources else "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "key": self.key, "kind": self.kind.value, "description": self.description,
                "target": self.target, "features": self.features.to_dict(), "sources": sorted(self.sources),
                "goal": self.goal_id, "status": self.status.value, "created": self.created_tick,
                "last_proposed": self.last_proposed_tick, "activated": self.activated_tick,
                "support": self.support, "steps": self.steps, "step_failures": self.step_failures,
                "reward": round(self.reward, 3), "selections": self.selections,
                "score": round(self.last_score, 4), "plan": [[t, a] for t, a in self.plan[:8]],
                "strategies": self.strategies, "outcome": self.outcome, "internal": self.kind.internal}
