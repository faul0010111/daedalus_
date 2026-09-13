"""Risk Engine: states that deserve validation or protection before they become failures."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ...cognition.reasoning import neighbors, position
from ..model import IntentionFeatures, IntentionKind
from .base import IntentionGenerator

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


class RiskEngine(IntentionGenerator):
    name = "risk_engine"
    period = 1

    def step(self, ctx: "CognitiveContext") -> None:
        world = ctx.world
        pressure = 0.0
        energy = world.quantities.get("energy", 100.0)
        integrity = world.quantities.get("integrity", 100.0)
        plan_cost = ctx.blackboard.get("focal_plan_cost", 0.0)
        home = world.subjects("is_a", "atrium", 0.9)
        return_cost = ctx.distances.get(home[0], 0) if home else 0
        # predictive: the committed plan plus the way back would exhaust energy
        reserve = float(ctx.strategies.value("risk.energy_reserve"))
        projected = energy - plan_cost - return_cost * 0.5
        if projected < reserve and energy < 70:
            urgency = min(1.0, (reserve - projected) / max(reserve, 1.0) + 0.2)
            intention = self.propose(ctx, "restore:energy", IntentionKind.MITIGATE_RISK,
                         "Projected energy shortfall: restore before continuing",
                         {"type": "restore", "quantity": "energy", "level": 80.0},
                         IntentionFeatures(goal_alignment=0.6, expected_value=0.5, urgency=urgency, confidence=0.8,
                                           resource_cost=0.05, resource_return=1.0, risk=0.0,
                                           historical_success_rate=ctx.memory.success_rate("mitigate_risk")),
                         max_steps=40)
            intention.strategies["risk.energy_reserve"] = ctx.strategies.active_variant("risk.energy_reserve")
            pressure += urgency
        # structural fragility: stop and recover before walking through hazards again
        if integrity < 55:
            urgency = min(1.0, (55 - integrity) / 40 + 0.15)
            self.propose(ctx, "restore:integrity", IntentionKind.MITIGATE_RISK, "Recover structural integrity",
                         {"type": "restore", "quantity": "integrity", "level": 75.0},
                         IntentionFeatures(goal_alignment=0.5, expected_value=0.4, urgency=urgency, confidence=0.9,
                                           resource_cost=0.02),
                         max_steps=20)
            pressure += urgency
        # validation: uncertain beliefs the current plan depends on
        here = position(ctx)
        for belief in world.critical_uncertain(0.3, 0.8)[:2]:
            s, p, o = belief.key
            if s not in ctx.distances:
                continue
            d = ctx.distances[s]
            self.propose(ctx, f"validate:{s}|{p}|{o}", IntentionKind.VALIDATE,
                         f"Validate before relying on it: {s} {p} {o}",
                         {"type": "verify", "entity": s, "key": [s, p, o]},
                         IntentionFeatures(goal_alignment=0.6, expected_value=0.4, urgency=0.4,
                                           uncertainty_reduction=belief.entropy, expected_information_gain=0.5,
                                           confidence=0.9, resource_cost=min(1.0, (d + 3) / max(10, energy)),
                                           historical_success_rate=ctx.memory.success_rate("validate")),
                         max_steps=d * 2 + 6)
            pressure += 0.4
        # the next step leads into a chamber whose hazard level is genuinely unknown
        next_room = ctx.blackboard.get("focal_next_room")
        if here and next_room and next_room in neighbors(ctx, here, passable_only=False):
            p_high = world.confidence(next_room, "hazard", "high", 0.0)
            if 0.2 <= p_high <= 0.65 and integrity < 85:
                self.propose(ctx, f"validate:{next_room}|hazard|high", IntentionKind.VALIDATE,
                             f"Probe {next_room} before entering (hazard uncertain)",
                             {"type": "verify", "entity": next_room, "key": [next_room, "hazard", "high"]},
                             IntentionFeatures(goal_alignment=0.5, expected_value=p_high * (1 - integrity / 100) + 0.2,
                                               urgency=0.5, uncertainty_reduction=0.8, confidence=0.95,
                                               resource_cost=3 / max(10, energy), risk=0.0,
                                               historical_success_rate=ctx.memory.success_rate("validate")),
                             max_steps=4)
                pressure += p_high
        self.last_pressure = pressure
