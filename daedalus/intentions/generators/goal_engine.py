"""Goal Engine: pressure to advance goals; the origin of emergent subgoals."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ...cognition.planning import Target
from ...cognition.reasoning import blocked_frontier, information_deficit, knowledge_gaps
from ...goals import Goal, GoalKind, GoalStatus
from ...goals.prioritization import goal_urgency
from ..model import IntentionFeatures, IntentionKind
from .base import IntentionGenerator

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


def goal_satisfied(ctx: "CognitiveContext", goal: Goal) -> bool:
    if goal.kind is GoalKind.ACHIEVE and goal.pattern:
        return bool(ctx.world.match(goal.pattern, 0.8))
    if goal.kind is GoalKind.KNOW and goal.pattern:
        return bool(ctx.world.match(goal.pattern, 0.65))
    return False


def refresh_goal_satisfaction(ctx: "CognitiveContext") -> None:
    """Cheap bookkeeping run right after perception: close satisfied goals, reopen lost ones."""
    for goal in list(ctx.goals.goals.values()):
        if goal.kind is GoalKind.MAINTAIN:
            continue
        if goal.status.open and goal_satisfied(ctx, goal):
            ctx.goals.transition(goal.id, GoalStatus.ACHIEVED, "condition holds in world model")
            if goal.kind is GoalKind.KNOW:
                ctx.metrics.inc("knowledge_gaps_resolved")
            ctx.metrics.inc("goals_achieved")
        elif goal.status is GoalStatus.ACHIEVED and goal.persistent and not goal_satisfied(ctx, goal):
            ctx.goals.transition(goal.id, GoalStatus.ACTIVE, "condition no longer holds; persistent goal reopened")
            ctx.metrics.inc("goal_reactivations")


def path_risk(ctx: "CognitiveContext", steps: list[tuple[str, dict]]) -> float:
    risk = 0.0
    for tool, args in steps:
        if tool == "move":
            risk += ctx.world.confidence(args["to"], "hazard", "high", 0.0) * 0.5
            risk += ctx.world.confidence(args["to"], "hazard", "low", 0.0) * 0.12
    return min(1.0, risk)


class GoalEngine(IntentionGenerator):
    name = "goal_engine"
    period = 1

    def step(self, ctx: "CognitiveContext") -> None:
        refresh_goal_satisfaction(ctx)
        pressure = 0.0
        for goal in list(ctx.goals.open_goals()):
            if self._obsolete(ctx, goal):
                continue
            if goal.status is GoalStatus.SUSPENDED:
                if ctx.clock.tick - goal.updated_tick >= 20:
                    ctx.goals.transition(goal.id, GoalStatus.ACTIVE, "periodic reconsideration")
                    goal.stalls = 0
                else:
                    continue
            if goal.kind is GoalKind.MAINTAIN:
                pressure += self._maintain(ctx, goal)
            elif goal.kind is GoalKind.KNOW:
                pressure += self._know(ctx, goal)
            else:
                pressure += self._achieve(ctx, goal)
        self.last_pressure = pressure

    @staticmethod
    def _energy_cost(ctx: "CognitiveContext", steps) -> float:
        return sum(ctx.tools.get(tool).energy_cost for tool, _ in steps if ctx.tools.has(tool))

    def _obsolete(self, ctx: "CognitiveContext", goal: Goal) -> bool:
        if not goal.emergent:
            return False
        parents = ctx.goals.parents(goal.id)
        if parents and not any(p.status.open for p in parents):
            ctx.goals.transition(goal.id, GoalStatus.ABANDONED, "obsolete: every parent goal closed")
            return True
        if goal.failures >= 6:
            # a goal its parent still needs is not obsolete just because attempts failed:
            # shelve it and reconsider later, or the graph churns through identical goals
            goal.failures = 0
            goal.stalls = 0
            ctx.goals.transition(goal.id, GoalStatus.SUSPENDED,
                                 "repeated failures; shelved for later reconsideration")
        return False

    # ------------------------------------------------------------------ kinds
    def _maintain(self, ctx: "CognitiveContext", goal: Goal) -> float:
        urgency = goal_urgency(ctx, goal)
        if urgency <= 0.0 or goal.quantity is None:
            return 0.0
        value = ctx.goals.value(goal.id)
        types = set(ctx.tools.restorer_types(goal.quantity))
        holding_restorer = any(t in types for i in ctx.world.objects(ctx.world.schema.agent_id, "holding", 0.7)
                               for t in ctx.world.objects(i, "is_a", 0.5))
        confidence = 0.95 if holding_restorer else 0.7
        target_level = goal.comfort
        self.propose(ctx, f"restore:{goal.quantity}", IntentionKind.ADVANCE_GOAL,
                     f"Restore {goal.quantity} to {target_level:.0f}",
                     {"type": "restore", "quantity": goal.quantity, "level": target_level},
                     IntentionFeatures(goal_alignment=value, expected_value=value * 0.8, urgency=urgency,
                                       confidence=confidence, resource_cost=0.05, resource_return=1.0,
                                       historical_success_rate=ctx.memory.success_rate("advance_goal:restore")),
                     goal_id=goal.id, max_steps=40)
        return urgency

    def _know(self, ctx: "CognitiveContext", goal: Goal) -> float:
        value = ctx.goals.value(goal.id)
        frontier = ctx.blackboard.get("frontier_size", 0)
        if not ctx.blackboard.get("virgin_frontier", []):
            # nothing left to search where the agent can walk: the answer may lie
            # beyond a barrier, which is a dependency rather than an absence
            # a barrier is the reason the search failed, so what matters is passing it —
            # not how thoroughly the far side has already been glimpsed from this side
            beyond = [(place, d) for place, d in blocked_frontier(ctx)
                      if information_deficit(ctx, place) > 0.05][:2]
            if beyond:
                ctx.emergence.spawn(ctx, [goal], GoalKind.ACHIEVE,
                                    [(ctx.world.schema.agent_id, ctx.world.schema.position_predicate, place)
                                     for place, _ in beyond],
                                    reason="search exhausted; unsearched region lies beyond a barrier",
                                    engine=self.name)
                ctx.goals.transition(goal.id, GoalStatus.BLOCKED,
                                     f"reachable frontier exhausted; {beyond[0][0]} is behind a barrier")
                return 0.0
            goal.stalls += 1
            if goal.stalls > 25:
                ctx.goals.transition(goal.id, GoalStatus.SUSPENDED, "no unexplored frontier left to search")
            return 0.0
        policy = ctx.strategies.active_variant("exploration.frontier_policy")
        self.propose(ctx, f"advance:{goal.id}", IntentionKind.ADVANCE_GOAL, goal.description,
                     {"type": "know", "pattern": list(goal.pattern)},
                     IntentionFeatures(goal_alignment=value, expected_value=value * 0.6, urgency=goal_urgency(ctx, goal),
                                       expected_information_gain=0.5, uncertainty_reduction=0.4,
                                       confidence=0.55, resource_cost=min(1.0, 6 / max(10.0, ctx.world.quantities.get("energy", 50))),
                                       historical_success_rate=ctx.memory.success_rate("advance_goal:know")),
                     goal_id=goal.id, max_steps=45).strategies["exploration.frontier_policy"] = policy
        return value

    def _achieve(self, ctx: "CognitiveContext", goal: Goal) -> float:
        assert goal.pattern is not None
        gaps = knowledge_gaps(ctx, goal.pattern)
        if gaps:
            ctx.emergence.spawn(ctx, [goal], GoalKind.KNOW, gaps, reason="knowledge gap in regression", engine=self.name)
            ctx.goals.transition(goal.id, GoalStatus.BLOCKED, "knowledge gap: " + "; ".join(" ".join(g) for g in gaps))
            return 0.0
        hint = ctx.blackboard.get("plan_hints", {}).get(goal.id)
        plan = ctx.planner.plan(ctx, Target.fact(goal.pattern))
        if not plan.found and hint is not None:
            plan = hint
        if plan.executable:
            if goal.status is not GoalStatus.ACTIVE:
                ctx.goals.transition(goal.id, GoalStatus.ACTIVE, "executable plan found")
            goal.stalls = 0
            value = ctx.goals.value(goal.id)
            energy = max(10.0, ctx.world.quantities.get("energy", 50.0))
            intention = self.propose(
                ctx, f"advance:{goal.id}", IntentionKind.ADVANCE_GOAL, goal.description,
                {"type": "fact", "pattern": list(goal.pattern)},
                IntentionFeatures(goal_alignment=value, expected_value=value * plan.success,
                                  urgency=goal_urgency(ctx, goal), confidence=plan.success,
                                  resource_cost=min(1.0, self._energy_cost(ctx, plan.steps) / energy),
                                  risk=path_risk(ctx, plan.steps),
                                  uncertainty_reduction=0.05, expected_information_gain=0.05,
                                  historical_success_rate=ctx.memory.success_rate("advance_goal:fact")),
                goal_id=goal.id, max_steps=int(len(plan.steps) * 2 + 10))
            intention.strategies["planning.support_threshold"] = ctx.strategies.active_variant("planning.support_threshold")
            return value
        if plan.found and plan.violations:
            blockers = [fact for fact, positive in plan.violations if positive]
            if blockers:
                ctx.emergence.spawn(ctx, [goal], GoalKind.ACHIEVE, blockers,
                                    reason="dependency revealed by relaxed plan", engine=self.name)
                ctx.goals.transition(goal.id, GoalStatus.BLOCKED,
                                     "depends on: " + "; ".join(" ".join(b) for b in blockers))
                return 0.0
        goal.stalls += 1
        if goal.stalls >= 15:
            ctx.goals.transition(goal.id, GoalStatus.SUSPENDED, f"no plan under current beliefs ({plan.reason})")
        return 0.0
