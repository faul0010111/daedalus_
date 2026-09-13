"""Deliberation: turning the currently attended intention into its next concrete step."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ...core.events import EventType
from ...intentions.generators.curiosity import rank_frontier
from ...intentions.model import Intention
from ..reasoning import neighbors, position
from .planner import PlanResult, Target

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


@dataclass
class StepDecision:
    kind: str  # external | internal | complete | fail
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    plan: PlanResult | None = None


class Deliberator:
    def __init__(self) -> None:
        self.replans = 0

    # -------------------------------------------------------------- completion
    def is_complete(self, ctx: "CognitiveContext", it: Intention) -> bool:
        t, world = it.target, ctx.world
        typ = t["type"]
        since = it.activated_tick or it.created_tick
        if typ == "fact":
            return bool(world.match(tuple(t["pattern"]), 0.8))
        if typ == "know":
            return bool(world.match(tuple(t["pattern"]), 0.65))
        if typ == "explore":
            return all(world.coverage.get((t["entity"], p), (0, -1))[1] >= since for p in world.schema.epistemic)
        if typ == "verify":
            return bool(t.get("verified"))
        if typ == "restore":
            return world.quantities.get(t["quantity"], 0.0) >= t["level"]
        if typ in ("tool", "cognitive"):
            return bool(t.get("done"))
        return False

    # ---------------------------------------------------------------- stepping
    def next_step(self, ctx: "CognitiveContext", it: Intention) -> StepDecision:
        if self.is_complete(ctx, it):
            return StepDecision("complete", reason="target satisfied")
        if it.steps >= it.max_steps:
            return StepDecision("fail", reason=f"step budget exhausted ({it.max_steps})")
        if it.consecutive_failures >= 3:
            return StepDecision("fail", reason="three consecutive action failures")
        typ = it.target["type"]
        if typ == "cognitive":
            return StepDecision("internal", reason=it.target["op"])
        if typ == "tool":
            return StepDecision("external", it.target["tool"], dict(it.target.get("args", {})), "direct capability")
        if typ == "fact":
            return self._plan_step(ctx, it, Target.fact(tuple(it.target["pattern"])))
        if typ == "explore":
            return self._explore_step(ctx, it, it.target["entity"])
        if typ == "know":
            policy = it.strategies.get("exploration.frontier_policy") or \
                ctx.strategies.active_variant("exploration.frontier_policy")
            current = it.target.get("frontier")
            if current and not self._covered_since(ctx, current, it):
                return self._explore_step(ctx, it, current)
            ranked = rank_frontier(ctx, policy)
            if not ranked:
                return StepDecision("fail", reason="no frontier left")
            it.target["frontier"] = ranked[0][0]
            return self._explore_step(ctx, it, ranked[0][0])
        if typ == "verify":
            return self._verify_step(ctx, it)
        if typ == "restore":
            return self._restore_step(ctx, it)
        return StepDecision("fail", reason=f"unknown target type {typ}")

    def _covered_since(self, ctx: "CognitiveContext", room: str, it: Intention) -> bool:
        since = it.activated_tick or it.created_tick
        return all(ctx.world.coverage.get((room, p), (0, -1))[1] >= since for p in ctx.world.schema.epistemic)

    def _plan_step(self, ctx: "CognitiveContext", it: Intention, target: Target,
                   threshold: float | None = None) -> StepDecision:
        here = position(ctx)
        cached = it.plan
        if cached and it.plan_revision >= ctx.clock.tick - 6:
            tool, args = cached[0]
            valid = (tool != "move" or args.get("from") == here) and (tool != "take" or args.get("room") == here)
            if valid:
                it.plan = cached[1:]
                self._publish_focus(ctx, it, cached)
                return StepDecision("external", tool, args, "cached plan")
        plan = ctx.planner.plan(ctx, target, threshold=threshold)
        self.replans += 1
        if not plan.executable:
            ctx.bus.publish(EventType.NO_PLAN, "deliberation",
                            {"intention": it.key, "target": target.description, "reason": plan.reason,
                             "violations": [[list(f), p] for f, p in plan.violations][:4]})
            return StepDecision("fail", reason="blocked" if plan.found else "no_plan", plan=plan)
        if not plan.steps:
            return StepDecision("complete", reason="already satisfied by plan state")
        ctx.world.mark_critical(plan.support)
        ctx.bus.publish(EventType.PLAN, "deliberation",
                        {"intention": it.key, "steps": len(plan.steps), "cost": round(plan.cost, 2),
                         "success": round(plan.success, 3), "expansions": plan.expansions,
                         "first": [plan.steps[0][0], plan.steps[0][1]]})
        it.plan = plan.steps[1:]
        it.plan_revision = ctx.clock.tick
        self._publish_focus(ctx, it, plan.steps, plan.cost)
        tool, args = plan.steps[0]
        return StepDecision("external", tool, args, "fresh plan", plan)

    def _publish_focus(self, ctx: "CognitiveContext", it: Intention, steps, cost: float | None = None) -> None:
        ctx.blackboard["focal_plan_cost"] = cost if cost is not None else float(len(steps))
        nxt = next((a["to"] for t, a in steps if t == "move"), None)
        ctx.blackboard["focal_next_room"] = nxt
        ctx.blackboard["focal_path"] = [a["to"] for t, a in steps if t == "move"]

    def _explore_step(self, ctx: "CognitiveContext", it: Intention, room: str) -> StepDecision:
        here = position(ctx)
        if here == room:
            it.plan = []
            return StepDecision("external", "scan", {}, f"observe from {room}")
        schema = ctx.world.schema
        return self._plan_step(ctx, it, Target.position(schema.agent_id, schema.position_predicate, {room}))

    def _verify_step(self, ctx: "CognitiveContext", it: Intention) -> StepDecision:
        entity = it.target["entity"]
        here = position(ctx)
        if here == entity or (here and entity in neighbors(ctx, here, passable_only=False)):
            return StepDecision("external", "probe", {"room": entity}, "within reach")
        spots = {entity} | set(neighbors(ctx, entity, passable_only=True))  # membership only
        schema = ctx.world.schema
        return self._plan_step(ctx, it, Target.position(schema.agent_id, schema.position_predicate, spots))

    def _restore_step(self, ctx: "CognitiveContext", it: Intention) -> StepDecision:
        quantity = it.target["quantity"]
        restorers = ctx.tools.restorers(quantity)
        world = ctx.world
        schema_agent = world.schema.agent_id
        holding = world.objects(schema_agent, "holding", 0.7)

        def is_a(item: str, type_name: str | None) -> bool:
            return type_name is not None and world.holds(item, "is_a", type_name, 0.5)
        best: tuple[float, StepDecision] | None = None
        for tool in restorers:
            amount = tool.restores[quantity]
            if tool.name == "rest":
                score = 1.0 - 0.5 * amount
                decision = StepDecision("external", "rest", {}, "rest in place")
            elif tool.consumes_type:
                held = [i for i in holding if is_a(i, tool.consumes_type)]
                if held:
                    score = -0.5 * amount
                    decision = StepDecision("external", tool.name, {"item": held[0]},
                                            f"spend a carried {tool.consumes_type}")
                else:
                    known = sorted({b.object for b in world.query(None, "contains", None, min_conf=0.55)
                                    if is_a(b.object, tool.consumes_type) and b.subject in ctx.distances})
                    if not known:
                        continue
                    nearest = min(known, key=lambda o: min(ctx.distances.get(b.subject, 99)
                                                           for b in world.query(None, "contains", o, min_conf=0.55)))
                    probe = ctx.planner.plan(ctx, Target.fact((schema_agent, "holding", nearest)))
                    if not probe.executable:
                        continue
                    score = probe.cost - 0.5 * amount
                    it.target["restorer"] = nearest
                    decision = StepDecision("plan_oil", reason=f"fetch {nearest}")
            else:
                continue
            if best is None or score < best[0]:
                best = (score, decision)
        if best is None:
            return StepDecision("fail", reason="no restorer available")
        if best[1].kind == "plan_oil":
            return self._plan_step(ctx, it, Target.fact((schema_agent, "holding", it.target["restorer"])))
        return best[1]
