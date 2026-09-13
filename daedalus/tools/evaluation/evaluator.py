"""Outcome evaluation: every action becomes an episode with reward, information gain and surprise."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.events import EventType
from ...memory.episodic import Episode

if TYPE_CHECKING:
    from ...cognition.perception import IngestReport
    from ...core.cognition.context import CognitiveContext
    from ...intentions import Intention
    from ..execution import ToolResult

REWARD = {"progress": 1.0, "banked": 0.15, "info": 0.08, "energy": -0.02, "damage": -0.03,
          "failure": -0.15, "collapse": -1.5}


class OutcomeEvaluator:
    def evaluate(self, ctx: "CognitiveContext", intention: "Intention", tool: str, args: dict[str, Any],
                 result: "ToolResult", report: "IngestReport", before: dict[str, float]) -> Episode:
        q = ctx.world.quantities
        progress = ctx.goals.achieved_value() - before["achieved_value"]
        banked = q.get("banked_value", 0.0) - before["banked_value"]
        info = report.entropy_reduction + 0.1 * report.new_beliefs
        collapse = bool(result.info.get("collapse"))
        parts = {
            "progress": REWARD["progress"] * max(0.0, progress),
            "banked": REWARD["banked"] * banked,
            "info": REWARD["info"] * min(info, 5.0),
            "energy": REWARD["energy"] * result.energy_spent,
            "damage": REWARD["damage"] * result.damage,
            "failure": REWARD["failure"] if not result.success else 0.0,
            "collapse": REWARD["collapse"] if collapse else 0.0,
        }
        reward = sum(parts.values())
        expected = intention.features.confidence
        surprise = abs((1.0 if result.success else 0.0) - expected) + 0.3 * len(report.contradictions) + \
            (1.0 if collapse else 0.0)
        belief_source = ""
        if tool == "take" and not result.success:
            here = ctx.world.query(None, "contains", args.get("item"))
            evidence = [e for b in here for e in b.evidence if e.positive and not e.source.startswith("inference")]
            belief_source = evidence[-1].source if evidence else "unknown"
        episode = ctx.memory.episodic.record(
            tick=ctx.clock.tick, intention_id=intention.id, intention_kind=intention.kind.value,
            intention_source=intention.origin, goal_id=intention.goal_id, tool=tool, args=args,
            success=result.success, expected_success=expected, reward=reward, information_gain=info,
            cost=result.energy_spent, damage=result.damage, surprise=surprise,
            note=result.reason or "ok",
            context={"energy": q.get("energy"), "integrity": q.get("integrity"), "belief_source": belief_source,
                     "reward_parts": {k: round(v, 4) for k, v in parts.items() if v}})
        ctx.memory.record_outcome(f"tool:{tool}", result.success)
        if not result.success:
            ctx.memory.failure.record(ctx.clock.tick, tool, args, result.reason or "failed", intention.kind.value,
                                      belief_source=belief_source, intention=intention.key)
        elif ctx.memory.failure.records and ctx.memory.failure.records[-1].tool == tool:
            ctx.memory.failure.mark_recovered(tool, ctx.clock.tick)
        if surprise >= 0.5 or not result.success:
            ctx.blackboard.setdefault("unreflected", []).append(episode.id)
        if collapse:
            ctx.metrics.inc("collapses")
        ctx.bus.publish(EventType.OUTCOME, "evaluator",
                        {"episode": episode.id, "intention": intention.key, "tool": tool, "success": result.success,
                         "reward": round(reward, 4), "info_gain": round(info, 3), "surprise": round(surprise, 3),
                         "contradictions": report.contradictions, "resolved": report.resolved})
        return episode
