"""Priority strategies. None of them is "the" formula; all are swappable and learnable."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from ..model import FEATURES, Intention, IntentionKind

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext

DEFAULT_WEIGHTS: dict[str, float] = {
    "goal_alignment": 1.0,
    "expected_value": 1.0,
    "urgency": 1.3,
    "uncertainty_reduction": 0.45,
    "novelty": 0.25,
    "confidence": 0.35,
    "expected_information_gain": 0.6,
    "historical_success_rate": 0.3,
    "resource_cost": -0.7,
    "risk": -1.0,
    "resource_return": 0.6,
}


@dataclass(slots=True)
class ScoreBreakdown:
    total: float
    contributions: dict[str, float] = field(default_factory=dict)
    modulation: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"total": round(self.total, 4),
                "contributions": {k: round(v, 4) for k, v in self.contributions.items() if abs(v) > 1e-4},
                "modulation": {k: round(v, 3) for k, v in self.modulation.items() if abs(v - 1) > 1e-3}}


class PriorityStrategy(Protocol):
    name: str

    def score(self, intention: Intention, ctx: "CognitiveContext") -> ScoreBreakdown: ...


class LinearPriority:
    """priority = Σ wᵢ·featureᵢ — the conceptual formula, as a fixed baseline."""

    name = "linear"

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = dict(weights or DEFAULT_WEIGHTS)

    def score(self, intention: Intention, ctx: "CognitiveContext") -> ScoreBreakdown:
        f = intention.features
        contrib = {k: self.weights.get(k, 0.0) * getattr(f, k) for k in FEATURES}
        return ScoreBreakdown(sum(contrib.values()), contrib)


class ContextualPriority(LinearPriority):
    """Weights are modulated by the agent's internal pressures (drives).

    Low energy makes cost and risk heavier; high critical uncertainty makes
    information worth more; stagnation makes novelty attractive; recent
    failures make confidence matter.
    """

    name = "contextual"

    def modulation(self, ctx: "CognitiveContext") -> dict[str, float]:
        d = ctx.drives
        return {
            # Scarcity should change *which* expenditures are acceptable, not suppress
            # expenditure as such: net cost already excuses spending that pays itself
            # back, so amplifying gross cost on top of it charges the same concern
            # twice and leaves the agent timid exactly when it must act.
            "resource_cost": 1.0 + 0.5 * d.get("scarcity", 0.0),
            "resource_return": 1.0 + 2.0 * d.get("scarcity", 0.0),
            "risk": 1.0 + 1.5 * d.get("fragility", 0.0),
            "expected_information_gain": 1.0 + d.get("uncertainty", 0.0),
            "uncertainty_reduction": 1.0 + d.get("uncertainty", 0.0),
            "novelty": 1.0 + 2.0 * d.get("stagnation", 0.0),
            "confidence": 1.0 + d.get("failure", 0.0),
            "urgency": 1.0 + 0.5 * d.get("scarcity", 0.0),
        }

    def score(self, intention: Intention, ctx: "CognitiveContext") -> ScoreBreakdown:
        mod = self.modulation(ctx)
        f = intention.features
        contrib = {k: self.weights.get(k, 0.0) * mod.get(k, 1.0) * getattr(f, k) for k in FEATURES}
        # Spending that pays for itself is not spending. Charging an intention its
        # gross cost under scarcity suppresses exactly the actions that would end
        # the scarcity — the agent starves while refusing to walk to the fuel.
        net = max(0.0, f.resource_cost - f.resource_return)
        contrib["resource_cost"] = self.weights["resource_cost"] * mod["resource_cost"] * net
        return ScoreBreakdown(sum(contrib.values()), contrib, mod)


class LearnedAttentionPolicy:
    """Online learning of per-kind attention biases from intention outcomes.

    bias[kind] ← bias[kind] + lr · (reward − baseline[kind]) with a slowly moving
    global baseline. It learns *where attention has historically paid off*, not
    what to do.
    """

    def __init__(self, lr: float = 0.04, clip: float = 0.6) -> None:
        self.lr = lr
        self.clip = clip
        self.bias: dict[str, float] = {k.value: 0.0 for k in IntentionKind}
        self.baseline = 0.0
        self.updates = 0
        self.history: list[dict] = []

    def update(self, kind: IntentionKind, reward: float, steps: int, tick: int) -> float:
        per_step = reward / max(1, steps) if not kind.internal else reward
        advantage = per_step - self.baseline
        self.baseline += 0.02 * (per_step - self.baseline)
        b = self.bias[kind.value] + self.lr * math.tanh(advantage)
        self.bias[kind.value] = max(-self.clip, min(self.clip, b))
        self.updates += 1
        if self.updates % 5 == 0:
            self.history.append({"tick": tick, **{k: round(v, 3) for k, v in self.bias.items()}})
            del self.history[:-200]
        return advantage


class FixedPipelinePolicy:
    """Baseline for experiments: a hand-written cognitive workflow.

    Strict precedence by kind, ignoring every feature except a tie-break. This is
    the `if risk: mitigate / elif contradiction: resolve / elif goal: plan ...`
    architecture DAEDALUS argues against.
    """

    name = "fixed_pipeline"
    ORDER = [IntentionKind.MITIGATE_RISK, IntentionKind.RESOLVE_CONTRADICTION, IntentionKind.ADVANCE_GOAL,
             IntentionKind.EXPLOIT_OPPORTUNITY, IntentionKind.EXPLORE, IntentionKind.VALIDATE,
             IntentionKind.REFLECT, IntentionKind.CONSOLIDATE_MEMORY, IntentionKind.ADAPT_STRATEGY,
             IntentionKind.REORGANIZE]

    def score(self, intention: Intention, ctx: "CognitiveContext") -> ScoreBreakdown:
        rank = self.ORDER.index(intention.kind)
        tie = intention.features.goal_alignment * 0.5 - intention.features.resource_cost * 0.4
        return ScoreBreakdown(10.0 - rank + tie, {"pipeline_rank": 10.0 - rank, "tie_break": tie})


class RandomPolicy:
    name = "random"

    def score(self, intention: Intention, ctx: "CognitiveContext") -> ScoreBreakdown:
        return ScoreBreakdown(ctx.rng.random(), {"random": 1.0})
