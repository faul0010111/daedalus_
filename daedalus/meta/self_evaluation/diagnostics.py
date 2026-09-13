"""Meta-cognitive diagnostics. They describe the system's condition; they do not act."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ...core.events import EventType
from ...goals import GoalKind
from ...intentions.generators.base import IntentionGenerator
from ...intentions.model import IntentionFeatures, IntentionKind

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


@dataclass
class Diagnosis:
    code: str
    message: str
    severity: float
    evidence: dict[str, Any] = field(default_factory=dict)
    tick: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "severity": round(self.severity, 3),
                "evidence": self.evidence, "tick": self.tick}


def diagnose(ctx: "CognitiveContext") -> list[Diagnosis]:
    m = ctx.monitor.summary()
    out: list[Diagnosis] = []
    if m["window"] < 30:
        return out
    stagnation = ctx.monitor.stagnation()
    if stagnation > 0.5:
        out.append(Diagnosis("STAGNATION", "Current strategy causing stagnation.", stagnation,
                             {"progress": m["progress"], "info_gain_per_tick": m["info_gain_per_tick"]}))
    if m["advance_samples"] >= 4 and m["advance_failure_rate"] > 0.5:
        out.append(Diagnosis("PLANNING_INEFFECTIVE", "Planning strategy ineffective.", m["advance_failure_rate"],
                             {"advance_failure_rate": m["advance_failure_rate"]}))
    if m["epistemic_share"] > 0.55 and m["info_gain_per_tick"] < 0.08:
        out.append(Diagnosis("EXCESSIVE_TOOL_USE", "Excessive tool usage detected.", m["epistemic_share"],
                             {"epistemic_share": m["epistemic_share"], "info_gain_per_tick": m["info_gain_per_tick"]}))
    patterns = ctx.memory.failure.patterns(ctx.clock.tick - ctx.monitor.window)
    repeated = [(k, v) for k, v in patterns.items() if v >= 4]
    if repeated:
        (tool, reason), count = max(repeated, key=lambda x: x[1])
        out.append(Diagnosis("REPEATED_FAILURE", "Repeated failure pattern identified.", min(1.0, count / 8),
                             {"tool": tool, "reason": reason, "count": count}))
    explore_share = m["kind_share"].get("explore", 0.0) + m["kind_share"].get("advance_goal", 0.0) * 0.3
    if ctx.goals.open_goals([GoalKind.KNOW]) and ctx.blackboard.get("frontier_size", 0) > 3 and explore_share < 0.15:
        out.append(Diagnosis("INSUFFICIENT_EXPLORATION", "Insufficient exploration.", 1 - explore_share,
                             {"explore_share": round(explore_share, 3),
                              "frontier": ctx.blackboard.get("frontier_size", 0)}))
    critical = ctx.world.critical_uncertain(0.35, 0.75)
    if len(critical) >= 2:
        out.append(Diagnosis("HIGH_CRITICAL_UNCERTAINTY", "High uncertainty in critical beliefs.",
                             min(1.0, len(critical) / 4), {"beliefs": [list(b.key) for b in critical[:4]]}))
    tick = ctx.clock.tick
    for d in out:
        d.tick = tick
    return out


REMEDIES = {
    "STAGNATION": ["exploration.frontier_policy", "attention.temperature", "risk.energy_reserve"],
    "PLANNING_INEFFECTIVE": ["planning.support_threshold"],
    "EXCESSIVE_TOOL_USE": ["exploration.frontier_policy"],
    "INSUFFICIENT_EXPLORATION": ["exploration.frontier_policy", "attention.commitment"],
    "REPEATED_FAILURE": ["opportunity.min_confidence"],
}


class MetaCognitiveLayer(IntentionGenerator):
    name = "metacognition"
    period = 10
    phase = 5

    def __init__(self) -> None:
        super().__init__()
        self.active: dict[str, Diagnosis] = {}
        self.history: list[dict[str, Any]] = []

    def step(self, ctx: "CognitiveContext") -> None:
        diagnoses = diagnose(ctx)
        current = {d.code: d for d in diagnoses}
        for code, d in current.items():
            if code not in self.active:
                ctx.bus.publish(EventType.DIAGNOSIS, self.name, d.to_dict())
                self.history.append(d.to_dict())
                del self.history[:-200]
                ctx.metrics.inc("diagnoses")
        self.active = current
        ctx.blackboard["diagnoses"] = [d.to_dict() for d in diagnoses]
        self.last_pressure = sum(d.severity for d in diagnoses)
        requests = ctx.blackboard.setdefault("adapt_requests", {})
        for d in diagnoses:
            for point in REMEDIES.get(d.code, []):
                requests.setdefault(point, f"diagnosis {d.code}: {d.message}")
            if d.code == "REPEATED_FAILURE":
                self.propose(ctx, "reflect", IntentionKind.REFLECT, "Reflect on a repeated failure pattern",
                             {"type": "cognitive", "op": "reflect"},
                             IntentionFeatures(goal_alignment=0.4, expected_value=0.5, urgency=0.4 * d.severity,
                                               confidence=0.8, resource_cost=0.03,
                                               historical_success_rate=ctx.memory.success_rate("reflect")))
            if d.code == "HIGH_CRITICAL_UNCERTAINTY":
                for key in d.evidence["beliefs"][:2]:
                    s, p, o = key
                    if s in ctx.distances:
                        self.propose(ctx, f"validate:{s}|{p}|{o}", IntentionKind.VALIDATE,
                                     f"Validate critical belief {s} {p} {o}",
                                     {"type": "verify", "entity": s, "key": key},
                                     IntentionFeatures(goal_alignment=0.5, expected_value=0.4, urgency=0.35,
                                                       uncertainty_reduction=0.8, confidence=0.9,
                                                       resource_cost=min(1.0, (ctx.distances[s] + 3) / 40)),
                                     max_steps=ctx.distances[s] * 2 + 6)
