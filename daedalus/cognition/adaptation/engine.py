"""Adaptation loop: performance analysis → diagnosis → candidate → trial → adopt/reject."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ...intentions.generators.base import IntentionGenerator
from ...intentions.model import Intention, IntentionFeatures, IntentionKind

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


class AdaptationEngine(IntentionGenerator):
    name = "adaptation_engine"
    period = 5
    phase = 3

    def step(self, ctx: "CognitiveContext") -> None:
        requests: dict[str, str] = ctx.blackboard.get("adapt_requests", {})
        pressure = 0.0
        for point, rationale in list(requests.items()):
            if point not in ctx.strategies.points or point in ctx.strategies.trials \
                    or ctx.clock.tick < ctx.strategies.cooldown.get(point, 0):
                requests.pop(point, None)
                continue
            severity = 0.6 if "diagnosis" in rationale else 0.45
            self.propose(ctx, f"adapt:{point}", IntentionKind.ADAPT_STRATEGY,
                         f"Trial an alternative for {point}",
                         {"type": "cognitive", "op": "adapt", "point": point, "rationale": rationale},
                         IntentionFeatures(goal_alignment=0.35, expected_value=severity, urgency=severity * 0.5,
                                           uncertainty_reduction=0.35, confidence=0.5, resource_cost=0.02,
                                           historical_success_rate=ctx.memory.success_rate("adapt_strategy")))
            pressure += severity
        self.last_pressure = pressure

    def execute(self, ctx: "CognitiveContext", intention: Intention) -> bool:
        point = intention.target["point"]
        trial = ctx.strategies.start_trial(ctx, point, intention.target.get("rationale", ""))
        ctx.blackboard.get("adapt_requests", {}).pop(point, None)
        return trial is not None
