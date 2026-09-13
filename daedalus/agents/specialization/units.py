"""Temporary cognitive units. Each is a specialized process scoped to one purpose goal.

Units do not command anything: they add focused proposals to the same economy,
so a team changes behaviour only by changing the pressure landscape.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...cognition.planning import Target
from ...cognition.reasoning import knowledge_gaps
from ...goals import GoalKind, GoalStatus
from ...intentions.generators.base import IntentionGenerator
from ...intentions.generators.curiosity import rank_frontier
from ...intentions.model import IntentionFeatures, IntentionKind

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


class CognitiveUnit(IntentionGenerator):
    role = "unit"

    def __init__(self, unit_id: str, purpose_goal: str, created_tick: int) -> None:
        super().__init__()
        self.id = unit_id
        self.name = f"agent:{unit_id}"
        self.purpose_goal = purpose_goal
        self.created_tick = created_tick
        self.contributions = 0
        self.last_contribution_tick = created_tick
        self.proposals = 0
        self.notes: list[str] = []

    def describe(self) -> dict[str, Any]:
        return super().describe() | {"id": self.id, "role": self.role, "purpose": self.purpose_goal,
                                     "created": self.created_tick, "contributions": self.contributions,
                                     "proposals": self.proposals, "notes": self.notes[-5:]}

    def subtree(self, ctx: "CognitiveContext"):
        return [g for g in ctx.goals.descendants(self.purpose_goal) if g.status.open]


class InvestigationAgent(CognitiveUnit):
    role = "investigation"
    period = 2

    def step(self, ctx: "CognitiveContext") -> None:
        know = [g for g in self.subtree(ctx) if g.kind is GoalKind.KNOW]
        if not know:
            return
        goal = max(know, key=lambda g: ctx.goals.value(g.id))
        value = ctx.goals.value(goal.id)
        energy = max(10.0, ctx.world.quantities.get("energy", 50.0))
        for room, v, d in rank_frontier(ctx, "gain_per_cost", min_value=0.4)[:2]:
            self.propose(ctx, f"explore:{room}", IntentionKind.EXPLORE, f"Search {room} for: {goal.description}",
                         {"type": "explore", "entity": room},
                         IntentionFeatures(goal_alignment=value * v, expected_value=value * v, expected_information_gain=v,
                                           uncertainty_reduction=v * 0.8, novelty=0.6, confidence=0.85,
                                           resource_cost=min(1.0, (d + 2) / energy),
                                           risk=ctx.world.confidence(room, "hazard", "high", 0.0) * 0.6,
                                           historical_success_rate=ctx.memory.success_rate("explore")),
                         goal_id=goal.id, max_steps=d * 2 + 8)
            self.proposals += 1


class ValidationAgent(CognitiveUnit):
    role = "validation"
    period = 3

    def step(self, ctx: "CognitiveContext") -> None:
        world = ctx.world
        achieve = [g for g in self.subtree(ctx) if g.kind is GoalKind.ACHIEVE and g.pattern] + \
                  [ctx.goals.goals[self.purpose_goal]]
        for goal in achieve[:2]:
            if not goal.status.open or not goal.pattern:
                continue
            plan = ctx.planner.plan(ctx, Target.fact(goal.pattern), threshold=0.4, max_expansions=1500)
            if not plan.found:
                continue
            for fact in plan.support:
                conf = world.confidence(*fact)
                if 0.4 <= conf < 0.85 and fact[0] in ctx.distances:
                    s, p, o = fact
                    self.propose(ctx, f"validate:{s}|{p}|{o}", IntentionKind.VALIDATE,
                                 f"Confirm {s} {p} {o} before relying on it",
                                 {"type": "verify", "entity": s, "key": [s, p, o]},
                                 IntentionFeatures(goal_alignment=ctx.goals.value(goal.id), expected_value=0.5,
                                                   uncertainty_reduction=1 - abs(conf - 0.5) * 2 + 0.3,
                                                   expected_information_gain=0.5, urgency=0.3, confidence=0.9,
                                                   resource_cost=min(1.0, (ctx.distances[s] + 3) / 40)),
                                 goal_id=goal.id, max_steps=ctx.distances[s] * 2 + 6)
                    self.proposals += 1
                    break


class AnalysisAgent(CognitiveUnit):
    role = "analysis"
    period = 4

    def step(self, ctx: "CognitiveContext") -> None:
        blocked = [g for g in self.subtree(ctx) if g.kind is GoalKind.ACHIEVE and g.pattern
                   and g.status in (GoalStatus.BLOCKED, GoalStatus.SUSPENDED)]
        purpose = ctx.goals.goals[self.purpose_goal]
        if purpose.status in (GoalStatus.BLOCKED, GoalStatus.SUSPENDED):
            blocked.append(purpose)
        for goal in blocked[:2]:
            # deeper, more permissive search than the goal engine affords itself
            plan = ctx.planner.plan(ctx, Target.fact(goal.pattern), threshold=0.35,
                                    max_expansions=ctx.config.limits.planner_expansions * 3)
            if plan.executable:
                ctx.blackboard.setdefault("plan_hints", {})[goal.id] = plan
                self.notes.append(f"t{ctx.clock.tick}: permissive plan for {goal.id} ({len(plan.steps)} steps)")
                self.proposals += 1
            gaps = knowledge_gaps(ctx, goal.pattern, know_threshold=0.35, max_depth=5)
            if gaps:
                created = ctx.emergence.spawn(ctx, [goal], GoalKind.KNOW, gaps, reason="deep regression",
                                              engine=self.name)
                if created:
                    self.notes.append(f"t{ctx.clock.tick}: gaps {len(gaps)} for {goal.id}")
                    self.proposals += 1


class SynthesisAgent(CognitiveUnit):
    role = "synthesis"
    period = 10

    def step(self, ctx: "CognitiveContext") -> None:
        subtree = ctx.goals.descendants(self.purpose_goal)
        achieved = [g for g in subtree if g.status is GoalStatus.ACHIEVED and (g.achieved_tick or 0) >= self.created_tick]
        if achieved:
            ctx.memory.semantic.upsert(
                f"team:{self.purpose_goal}:{self.created_tick}", "team_outcome",
                f"Team for {self.purpose_goal} has closed {len(achieved)} subgoals since t{self.created_tick}.",
                0.7, len(achieved), ctx.clock.tick, subgoals=[g.id for g in achieved])
            self.proposals += 1


ROLES: dict[str, type[CognitiveUnit]] = {
    "investigation": InvestigationAgent,
    "validation": ValidationAgent,
    "analysis": AnalysisAgent,
    "synthesis": SynthesisAgent,
}
