"""Reflection: compare what was expected with what happened, and turn the difference into knowledge.

Reflection only *happens* when a REFLECT intention wins attention (or, in the
fixed-pipeline baseline, on a schedule). The engine continuously accumulates
the pressure that makes reflection worthwhile.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import TYPE_CHECKING, Any

from ...core.events import EventType
from ...intentions.generators.base import IntentionGenerator
from ...intentions.model import Intention, IntentionFeatures, IntentionKind

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


class ReflectionEngine(IntentionGenerator):
    name = "reflection_engine"
    period = 3
    phase = 2

    def __init__(self) -> None:
        super().__init__()
        self.ledger_cursor = 0
        self.insights: list[dict[str, Any]] = []
        self.accuracy_windows: dict[str, list[bool]] = defaultdict(list)

    # ------------------------------------------------------------------ pressure
    def pressure(self, ctx: "CognitiveContext") -> tuple[float, int, int]:
        pending = ctx.blackboard.setdefault("unreflected", [])
        failures = sum(1 for eid in pending if (ep := ctx.memory.episodic.episodes.get(eid)) and not ep.success)
        surprise = sum(ep.surprise for eid in pending if (ep := ctx.memory.episodic.episodes.get(eid)))
        new_ledger = max(0, len(ctx.world.verification_ledger) - self.ledger_cursor) \
            if len(ctx.world.verification_ledger) >= self.ledger_cursor else len(ctx.world.verification_ledger)
        return surprise + 0.35 * new_ledger + 0.5 * failures, failures, new_ledger

    def step(self, ctx: "CognitiveContext") -> None:
        pressure, failures, ledger = self.pressure(ctx)
        self.last_pressure = pressure
        if pressure >= 1.5:
            self.propose(ctx, "reflect", IntentionKind.REFLECT, "Reflect on recent surprises and failures",
                         {"type": "cognitive", "op": "reflect"},
                         IntentionFeatures(goal_alignment=0.3, expected_value=min(1.0, pressure / 8) * 0.8,
                                           uncertainty_reduction=min(1.0, ledger / 8) * 0.7,
                                           urgency=min(0.6, failures * 0.12), confidence=0.85, resource_cost=0.03,
                                           historical_success_rate=ctx.memory.success_rate("reflect")))
        used = ctx.blackboard.setdefault("maintenance_last_used", {})
        for tool, gain in list(ctx.blackboard.get("maintenance_candidates", {}).items()):
            if ctx.clock.tick - used.get(tool, -999) < 60:
                ctx.blackboard["maintenance_candidates"].pop(tool, None)
                continue
            self.propose(ctx, f"maintain:{tool}", IntentionKind.EXPLOIT_OPPORTUNITY,
                         f"Use {tool} to restore a degraded source (hypothesis)",
                         {"type": "tool", "tool": tool, "args": {}},
                         IntentionFeatures(goal_alignment=0.35, expected_value=min(1.0, gain), confidence=0.6,
                                           uncertainty_reduction=0.4, resource_cost=0.08, urgency=min(0.5, gain * 0.5),
                                           historical_success_rate=ctx.memory.success_rate("exploit_opportunity")),
                         max_steps=2)

    # ------------------------------------------------------------------ execution
    def execute(self, ctx: "CognitiveContext", intention: Intention | None) -> list[dict[str, Any]]:
        insights: list[dict[str, Any]] = []
        insights += self._learn_source_reliability(ctx)
        insights += self._diagnose_failures(ctx)
        insights += self._evaluate_strategies(ctx)
        insights += self._test_maintenance_hypotheses(ctx)
        ctx.blackboard["unreflected"] = []
        ctx.metrics.inc("reflection_events")
        tick = ctx.clock.tick
        for ins in insights:
            ins["tick"] = tick
        self.insights.extend(insights)
        del self.insights[:-150]
        ctx.bus.publish(EventType.REFLECTION, self.name,
                        {"insights": insights[:6], "count": len(insights),
                         "trigger": intention.origin if intention else "schedule"})
        return insights

    def _learn_source_reliability(self, ctx: "CognitiveContext") -> list[dict[str, Any]]:
        ledger = list(ctx.world.verification_ledger)
        start = self.ledger_cursor if self.ledger_cursor <= len(ledger) else 0
        entries = ledger[start:]
        self.ledger_cursor = len(ledger)
        if not entries:
            return []
        insights = []
        by_source: dict[str, list[bool]] = defaultdict(list)
        for e in entries:
            by_source[e["source"]].append(e["claimed"] == e["truth"])
        for source, outcomes in by_source.items():
            src = ctx.world.sources.get(source)
            if src is None:
                continue
            before = src.estimate
            for ok in outcomes:
                src.record(ok)
            window = self.accuracy_windows[source]
            window.extend(outcomes)
            del window[:-40]
            ctx.memory.semantic.upsert(
                f"source:{source}", "source_model",
                f"Claims from '{source}' survive verification {src.estimate:.0%} of the time "
                f"(nominal {src.nominal:.0%}).", src.estimate, src.verified + src.refuted, ctx.clock.tick,
                accuracy_recent=round(sum(window) / len(window), 3))
            if abs(src.estimate - before) >= 0.02:
                insights.append({"type": "source_reliability", "source": source, "before": round(before, 3),
                                 "after": round(src.estimate, 3), "evidence": len(outcomes)})
            # a source that claims more than it delivers, and a tool that maintains it, form a hypothesis
            maintainers = [t for t in ctx.tools.all() if t.maintains == source]
            if maintainers and len(window) >= 8:
                recent = sum(window[-8:]) / 8
                last_used = ctx.blackboard.get("maintenance_last_used", {}).get(
                    maintainers[0].name, -999)
                if recent < src.nominal - 0.12 and ctx.clock.tick - last_used >= 60:
                    tool = maintainers[0].name
                    ctx.world.hypothesize(source, "degrades_with", "use", 0.6,
                                          f"'{source}' accuracy has fallen to {recent:.0%}; '{tool}' may restore it",
                                          self.name, test=f"accuracy of {source} after {tool} > before")
                    gain = (src.nominal - recent) * 3
                    ctx.blackboard.setdefault("maintenance_candidates", {})[tool] = gain
                    ctx.blackboard.setdefault("maintenance_baseline", {})[tool] = recent
                    insights.append({"type": "hypothesis", "statement": f"{source} degrades with use; try {tool}",
                                     "recent_accuracy": round(recent, 3)})
        return insights

    def _diagnose_failures(self, ctx: "CognitiveContext") -> list[dict[str, Any]]:
        since = ctx.clock.tick - 60
        patterns = ctx.memory.failure.patterns(since)
        insights = []
        for (tool, reason), count in patterns.items():
            if count < 3:
                continue
            recent = [r for r in ctx.memory.failure.records if r.tick >= since and r.tool == tool and r.reason == reason]
            sources = Counter(r.context.get("belief_source", "unknown") for r in recent)
            cause = sources.most_common(1)[0][0]
            for r in recent:
                r.diagnosed_cause = f"acted on belief from '{cause}'" if cause != "unknown" else reason
            statement = f"'{tool}' failed {count}× with '{reason}' in the last 60 ticks; beliefs mostly came from '{cause}'."
            ctx.memory.semantic.upsert(f"failure:{tool}:{reason}", "lesson", statement,
                                       min(0.95, 0.5 + 0.1 * count), count, ctx.clock.tick,
                                       [r.id for r in recent])
            insights.append({"type": "failure_pattern", "tool": tool, "reason": reason, "count": count,
                             "cause": cause})
            if tool in ("take", "move") and cause in ("scan",):
                ctx.blackboard.setdefault("adapt_requests", {})["opportunity.min_confidence"] = \
                    f"repeated {tool} failures on beliefs from {cause}"
            if reason in ("blocked", "no_plan"):
                ctx.blackboard.setdefault("adapt_requests", {})["planning.support_threshold"] = \
                    f"repeated planning failures ({count})"
        return insights

    def _evaluate_strategies(self, ctx: "CognitiveContext") -> list[dict[str, Any]]:
        insights = []
        archive = [i for i in ctx.pool.archive if i.strategies][-60:]
        if len(archive) < 10:
            return insights
        overall = sum(i.reward / max(1, i.steps) for i in archive) / len(archive)
        by_point: dict[tuple[str, str], list[float]] = defaultdict(list)
        for i in archive:
            for point, variant in i.strategies.items():
                by_point[(point, variant)].append(i.reward / max(1, i.steps))
        for (point, variant), rewards in by_point.items():
            if len(rewards) < 6 or point not in ctx.strategies.points:
                continue
            mean = sum(rewards) / len(rewards)
            if mean < overall - 0.03 and variant == ctx.strategies.points[point].incumbent:
                ctx.blackboard.setdefault("adapt_requests", {})[point] = \
                    f"incumbent '{variant}' underperforms ({mean:+.3f} vs {overall:+.3f} per step)"
                insights.append({"type": "strategy_underperformance", "point": point, "variant": variant,
                                 "mean": round(mean, 4), "overall": round(overall, 4)})
        return insights

    def _test_maintenance_hypotheses(self, ctx: "CognitiveContext") -> list[dict[str, Any]]:
        insights = []
        for h in ctx.world.hypotheses.open():
            source = h.key[0]
            tool_calls = [e for e in ctx.memory.episodic.recent(200) if e.tool != source and
                          any(t.maintains == source and t.name == e.tool for t in ctx.tools.all())]
            if not tool_calls:
                continue
            last_call = tool_calls[-1].tick
            window = self.accuracy_windows.get(source, [])
            baseline = ctx.blackboard.get("maintenance_baseline", {}).get(tool_calls[-1].tool)
            verified_since = [e for e in ctx.world.verification_ledger
                              if e["source"] == source and e["tick"] > last_call and e["age"] <= e["tick"] - last_call]
            if baseline is None or len(verified_since) < 4:
                continue
            accuracy = sum(e["claimed"] == e["truth"] for e in verified_since) / len(verified_since)
            supports = accuracy > baseline + 0.05
            ctx.world.hypotheses.record(h.id, supports)
            insights.append({"type": "hypothesis_test", "hypothesis": h.statement, "accuracy_after": round(accuracy, 3),
                             "baseline": round(baseline, 3), "supports": supports, "status": h.status})
            ctx.blackboard.setdefault("maintenance_baseline", {})[tool_calls[-1].tool] = accuracy
            if h.status == "supported":
                ctx.memory.semantic.upsert(f"hypothesis:{h.id}", "lesson",
                                           f"Supported: {h.statement}", 0.8, h.support, ctx.clock.tick)
            del window[:]
        return insights
