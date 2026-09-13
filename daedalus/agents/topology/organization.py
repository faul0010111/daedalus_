"""Self-organization: complexity pressure proposes (never imposes) a temporary team."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ...goals import GoalKind, GoalStatus
from ...intentions.generators.base import IntentionGenerator
from ...intentions.model import Intention, IntentionFeatures, IntentionKind

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


def complexity_pressure(ctx: "CognitiveContext", goal_id: str) -> tuple[float, dict[str, float]]:
    subtree = ctx.goals.descendants(goal_id)
    open_sub = [g for g in subtree if g.status.open]
    depth = max((ctx.goals.depth(g.id) for g in open_sub), default=0)
    blocked = sum(1 for g in open_sub if g.status in (GoalStatus.BLOCKED, GoalStatus.SUSPENDED))
    know = sum(1 for g in open_sub if g.kind is GoalKind.KNOW)
    failures = sum(g.failures for g in subtree) + ctx.goals.goals[goal_id].failures
    contradictions = len(ctx.world.open_contradictions())
    age = ctx.clock.tick - ctx.goals.goals[goal_id].updated_tick
    parts = {"depth": 0.3 * depth, "blocked": 0.25 * blocked, "knowledge": 0.2 * know,
             "failures": 0.1 * min(failures, 6), "contradictions": 0.05 * min(contradictions, 8),
             "stall": min(0.4, age / 300)}
    return sum(parts.values()), parts


class OrganizationEngine(IntentionGenerator):
    name = "organization"
    period = 5
    phase = 2
    threshold = 1.1

    def step(self, ctx: "CognitiveContext") -> None:
        pressure_total = 0.0
        for goal in ctx.goals.roots():
            if not goal.status.open or goal.kind is GoalKind.MAINTAIN or ctx.agents.team_for(goal.id):
                continue
            pressure, parts = complexity_pressure(ctx, goal.id)
            pressure_total += pressure
            if pressure < self.threshold or len(ctx.agents.units) >= ctx.agents.max_units:
                continue
            roles = []
            if parts["knowledge"] > 0:
                roles.append("investigation")
            if parts["contradictions"] > 0.15 or parts["failures"] > 0.2:
                roles.append("validation")
            if parts["blocked"] > 0 or parts["stall"] > 0.2:
                roles.append("analysis")
            if len(roles) >= 2:
                roles.append("synthesis")
            if not roles:
                continue
            self.propose(ctx, f"reorganize:{goal.id}", IntentionKind.REORGANIZE,
                         f"Form a temporary team ({', '.join(roles)}) for: {goal.description}",
                         {"type": "cognitive", "op": "spawn_team", "goal": goal.id, "roles": roles,
                          "pressure": {k: round(v, 3) for k, v in parts.items()}},
                         IntentionFeatures(goal_alignment=ctx.goals.value(goal.id),
                                           expected_value=min(1.0, pressure / 2.5) * 0.7,
                                           urgency=min(0.5, (pressure - self.threshold) * 0.4), confidence=0.55,
                                           resource_cost=0.1,
                                           historical_success_rate=ctx.memory.success_rate("reorganize")),
                         goal_id=goal.id)
        self.last_pressure = pressure_total

    def execute(self, ctx: "CognitiveContext", intention: Intention) -> bool:
        target = intention.target
        if ctx.agents.team_for(target["goal"]):
            return False
        units = ctx.agents.spawn_team(ctx, target["goal"], target["roles"],
                                      rationale=f"complexity pressure {target.get('pressure')}")
        return bool(units)
