"""Contradiction Engine: credible evidence against a confident belief demands attention."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..model import IntentionFeatures, IntentionKind
from .base import IntentionGenerator

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


def goal_objects(ctx: "CognitiveContext") -> set[str]:
    objs: set[str] = set()
    for g in ctx.goals.open_goals():
        if g.pattern:
            objs |= {t for t in g.pattern if not t.startswith("?")}
    return objs


class ContradictionEngine(IntentionGenerator):
    name = "contradiction_engine"
    period = 1

    def step(self, ctx: "CognitiveContext") -> None:
        world = ctx.world
        relevant_objects = goal_objects(ctx)
        energy = max(10.0, world.quantities.get("energy", 50.0))
        scored = []
        for c in world.open_contradictions():
            s, p, o = c.key
            if s not in ctx.distances:
                continue
            critical = c.key in world.critical
            relevance = 0.8 if (o in relevant_objects or critical) else 0.25
            age = ctx.clock.tick - c.tick
            scored.append((c.severity * relevance / (1 + age / 80), c, relevance, critical))
        scored.sort(key=lambda x: (-x[0], x[1].id))
        pressure = 0.0
        for weight, c, relevance, critical in [(w, c, r, k) for w, c, r, k in scored[:3]]:
            s, p, o = c.key
            d = ctx.distances.get(s, 10)
            self.propose(
                ctx, f"resolve:{s}|{p}|{o}", IntentionKind.RESOLVE_CONTRADICTION,
                f"Resolve contradiction: {s} {p} {o}?",
                {"type": "verify", "entity": s, "key": [s, p, o], "contradiction": c.id},
                IntentionFeatures(goal_alignment=relevance, expected_value=0.2 + 0.4 * relevance,
                                  urgency=0.2 + 0.5 * float(critical), uncertainty_reduction=0.8,
                                  expected_information_gain=0.6, confidence=0.9,
                                  resource_cost=min(1.0, (d + 3) / energy),
                                  risk=world.confidence(s, "hazard", "high", 0.0) * 0.5,
                                  historical_success_rate=ctx.memory.success_rate("resolve_contradiction")),
                max_steps=d * 2 + 6)
            pressure += weight
        self.last_pressure = pressure
