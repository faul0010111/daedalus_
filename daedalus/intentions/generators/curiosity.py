"""Curiosity Engine: what don't I know that might matter?"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ...cognition.reasoning import exploration_value
from ...goals import GoalKind
from ..model import IntentionFeatures, IntentionKind
from .base import IntentionGenerator

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


def rank_frontier(ctx: "CognitiveContext", policy: str, min_value: float = 0.15) -> list[tuple[str, float, int]]:
    ranked: list[tuple[float, str, float, int]] = []
    for room, d in ctx.distances.items():
        v = ctx.blackboard.setdefault("_explore_value", {}).get(room)
        if v is None:
            v = exploration_value(ctx, room)
            ctx.blackboard["_explore_value"][room] = v
        if v < min_value:
            continue
        if policy == "nearest":
            key = -d + v * 0.5
        elif policy == "max_gain":
            key = v * 4 - d * 0.05
        else:  # gain_per_cost
            key = v / (1.0 + 0.3 * d)
        ranked.append((key, room, v, d))
    ranked.sort(reverse=True)
    return [(room, v, d) for _, room, v, d in ranked]


class CuriosityEngine(IntentionGenerator):
    name = "curiosity_engine"
    period = 2
    phase = 1

    def step(self, ctx: "CognitiveContext") -> None:
        policy = ctx.strategies.active_variant("exploration.frontier_policy")
        frontier = rank_frontier(ctx, policy)
        know_goals = ctx.goals.open_goals([GoalKind.KNOW])
        alignment = max((ctx.goals.value(g.id) for g in know_goals), default=0.0) * 0.7
        energy = max(10.0, ctx.world.quantities.get("energy", 50.0))
        total = 0.0
        for room, value, d in frontier[:3]:
            never_seen = (room, "hazard") not in ctx.world.coverage
            # a place only serves a KNOW goal to the extent it could still hold the answer
            serves = alignment * value
            risk = ctx.world.confidence(room, "hazard", "high", 0.0) * 0.6
            it = self.propose(
                ctx, f"explore:{room}", IntentionKind.EXPLORE, f"Explore {room}",
                {"type": "explore", "entity": room},
                IntentionFeatures(goal_alignment=serves + 0.05, expected_value=value * (0.25 + serves),
                                  expected_information_gain=value, uncertainty_reduction=value * 0.8,
                                  novelty=1.0 if never_seen else 0.15, confidence=0.85,
                                  resource_cost=min(1.0, (d + 2) / energy), risk=risk,
                                  historical_success_rate=ctx.memory.success_rate("explore")),
                max_steps=d * 2 + 8)
            it.strategies["exploration.frontier_policy"] = policy
            total += value
        self.last_pressure = total
