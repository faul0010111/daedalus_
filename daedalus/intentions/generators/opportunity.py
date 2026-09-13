"""Opportunity Engine: potentially valuable actions no goal asked for."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ...goals import GoalKind
from ..model import IntentionFeatures, IntentionKind
from .base import IntentionGenerator

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


def item_value(ctx: "CognitiveContext", item: str) -> float:
    values = ctx.world.query(item, "value", None, min_conf=0.6)
    return float(values[0].object) if values else 0.0


class OpportunityEngine(IntentionGenerator):
    name = "opportunity_engine"
    period = 2

    @staticmethod
    def _restorers(ctx: "CognitiveContext") -> dict[str, tuple[str, float, float]]:
        """type -> (quantity, normalised return, how badly the quantity is wanted).

        Everything here is read from declarations: which tools restore what, and
        which maintain goals care. Nothing knows that fuel is called "oil".
        """
        out: dict[str, tuple[str, float, float]] = {}
        for goal in ctx.goals.open_goals([GoalKind.MAINTAIN]):
            if not goal.quantity or goal.comfort <= 0:
                continue
            level = ctx.world.quantities.get(goal.quantity)
            want = 0.0 if level is None else max(0.0, min(1.0, (goal.comfort - level) / goal.comfort))
            for type_name, tool in ctx.tools.restorer_types(goal.quantity).items():
                gain = min(1.0, tool.restores[goal.quantity] / goal.comfort)
                out[type_name] = (goal.quantity, gain, want)
        return out

    def step(self, ctx: "CognitiveContext") -> None:
        world = ctx.world
        min_conf = float(ctx.strategies.value("opportunity.min_confidence"))
        variant = ctx.strategies.active_variant("opportunity.min_confidence")
        energy = max(10.0, world.quantities.get("energy", 50.0))
        holding = set(world.objects(world.schema.agent_id, "holding", 0.7))
        restorers = self._restorers(ctx)
        pressure = 0.0

        def type_of(item: str) -> str | None:
            types = world.objects(item, "is_a", 0.5)
            return types[0] if types else None

        # value lying on the floor
        for belief in world.query(None, "contains", None, min_conf=min_conf):
            room, item = belief.subject, belief.object
            if room not in ctx.distances or item in holding:
                continue
            distance = ctx.distances[room]
            kind = type_of(item)
            worth = item_value(ctx, item) / 5.0
            restorer = restorers.get(kind) if kind else None
            if restorer is not None:
                _, gain, want = restorer
                value = gain * want
                resource_return = gain
                urgency = min(0.7, want)
                if value < 0.08:
                    continue
            elif worth > 0:
                value, resource_return, urgency = worth, 0.0, 0.1
            else:
                continue
            it = self.propose(
                ctx, f"exploit:{item}", IntentionKind.EXPLOIT_OPPORTUNITY, f"Collect {item} in {room}",
                {"type": "fact", "pattern": [world.schema.agent_id, "holding", item]},
                IntentionFeatures(goal_alignment=0.2 + 0.5 * urgency, expected_value=value * belief.confidence,
                                  confidence=belief.confidence, resource_cost=min(1.0, (distance + 1) / energy),
                                  resource_return=resource_return, novelty=0.2, urgency=urgency,
                                  risk=world.confidence(room, "hazard", "high", 0.0) * 0.5,
                                  historical_success_rate=ctx.memory.success_rate("exploit_opportunity")),
                max_steps=distance * 2 + 6)
            it.strategies["opportunity.min_confidence"] = variant
            pressure += value

        # value in hand is value at risk
        carried = sorted(i for i in holding if item_value(ctx, i) > 0 and type_of(i) not in restorers)
        if carried:
            home = world.subjects("is_a", "atrium", 0.9)
            distance = ctx.distances.get(home[0], 8) if home else 8
            for item in carried:
                value = item_value(ctx, item) / 5.0
                self.propose(
                    ctx, f"bank:{item}", IntentionKind.EXPLOIT_OPPORTUNITY, f"Bank {item} in the Atrium",
                    {"type": "fact", "pattern": [item, "deposited", "yes"]},
                    IntentionFeatures(goal_alignment=0.25, expected_value=value + 0.1,
                                      urgency=min(0.6, 0.08 * len(carried) + 0.3 * ctx.drives.get("fragility", 0.0)),
                                      confidence=0.9, resource_cost=min(1.0, (distance + 1) / energy),
                                      historical_success_rate=ctx.memory.success_rate("exploit_opportunity")),
                    max_steps=distance * 2 + 8)
                pressure += value
        self.last_pressure = pressure
