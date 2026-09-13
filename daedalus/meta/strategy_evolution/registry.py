"""Strategy evolution: decision points, variants, trials, and an auditable adoption record."""
from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ...core.events import EventType
from ...memory.strategic import StrategyAudit

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


@dataclass
class DecisionPoint:
    name: str
    description: str
    variants: dict[str, Any]
    incumbent: str
    adaptable: bool = True


@dataclass
class Trial:
    point: str
    candidate: str
    started_tick: int
    rationale: str
    uses: int = 0
    rewards: list[float] = field(default_factory=list)
    incumbent_baseline: float = 0.0
    system_baseline: float = 0.0   # how the whole agent was doing before the trial
    baseline_samples: list[float] = field(default_factory=list)


class StrategyRegistry:
    def __init__(self, trial_length: int = 12, margin: float = 0.01) -> None:
        self.points: dict[str, DecisionPoint] = {}
        self.trials: dict[str, Trial] = {}
        self.trial_length = trial_length
        self.margin = margin
        self.enabled = True
        self.cooldown: dict[str, int] = {}
        self.system_history: deque[tuple[int, float]] = deque(maxlen=600)

    def define(self, name: str, description: str, variants: dict[str, Any], incumbent: str,
               adaptable: bool = True) -> None:
        self.points[name] = DecisionPoint(name, description, variants, incumbent, adaptable)

    def active_variant(self, name: str) -> str:
        trial = self.trials.get(name)
        return trial.candidate if trial else self.points[name].incumbent

    def value(self, name: str) -> Any:
        point = self.points[name]
        return point.variants[self.active_variant(name)]

    def candidates(self, ctx: "CognitiveContext", name: str) -> list[str]:
        point = self.points[name]
        return [v for v in point.variants if v != point.incumbent]

    def start_trial(self, ctx: "CognitiveContext", name: str, rationale: str) -> Trial | None:
        point = self.points.get(name)
        if not self.enabled or point is None or not point.adaptable or name in self.trials:
            return None
        if ctx.clock.tick < self.cooldown.get(name, 0):
            return None
        # prefer the least-tried alternative, then the best-performing one (optimism under uncertainty)
        def rank(variant: str) -> tuple[int, float]:
            stats = ctx.memory.strategic.get(name, variant)
            n = stats.n if stats else 0
            mean = stats.mean if stats else 0.0
            return (min(n, self.trial_length), -mean)

        options = sorted(self.candidates(ctx, name), key=rank)
        if not options:
            return None
        inc = ctx.memory.strategic.get(name, point.incumbent)
        trial = Trial(name, options[0], ctx.clock.tick, rationale,
                      incumbent_baseline=inc.mean if inc and inc.n else 0.0,
                      system_baseline=self._system_score(ctx),
                      baseline_samples=[v for _, v in list(self.system_history)[-24:]])
        self.trials[name] = trial
        ctx.memory.strategic.audit.append(StrategyAudit(ctx.clock.tick, name, point.incumbent, trial.candidate,
                                                        "trial", rationale=rationale))
        ctx.metrics.inc("strategy_trials")
        ctx.bus.publish(EventType.ADAPT_TRIAL, "strategy_evolution",
                        {"point": name, "incumbent": point.incumbent, "candidate": trial.candidate,
                         "rationale": rationale})
        return trial

    def record(self, ctx: "CognitiveContext", name: str, variant: str, reward: float) -> None:
        ctx.memory.strategic.record(name, variant, reward)
        trial = self.trials.get(name)
        if trial and trial.candidate == variant:
            trial.uses += 1
            trial.rewards.append(reward)
            if trial.uses >= self.trial_length:
                self._conclude(ctx, trial)

    def observe_system(self, ctx: "CognitiveContext") -> None:
        self.system_history.append((ctx.clock.tick, self._system_score(ctx)))

    @staticmethod
    def _system_score(ctx: "CognitiveContext") -> float:
        """What the change is ultimately judged on: how the agent as a whole is doing.

        Per-intention reward is a poor arbiter — a strategy can make its own
        intentions look cheap while costing the system its opportunities.
        """
        window = ctx.monitor.summary()
        return window["reward_per_tick"] + 0.5 * window["info_gain_per_tick"]

    def _conclude(self, ctx: "CognitiveContext", trial: Trial) -> None:
        """Adopt only when the improvement is larger than the noise it sits in."""
        point = self.points[trial.point]
        during = [v for tick, v in self.system_history if tick >= trial.started_tick]
        baseline = trial.baseline_samples
        cand_score = statistics.mean(during) if during else self._system_score(ctx)
        inc_score = statistics.mean(baseline) if baseline else trial.system_baseline
        spread = 0.0
        if len(during) > 1 and len(baseline) > 1:
            pooled = statistics.pstdev(during + baseline)
            spread = pooled * ((1 / len(during) + 1 / len(baseline)) ** 0.5)
        adopt = cand_score > inc_score + max(self.margin, spread)
        decision = "adopted" if adopt else "rejected"
        previous = point.incumbent
        if adopt:
            point.incumbent = trial.candidate
            ctx.metrics.inc("strategy_adaptations")
        del self.trials[trial.point]
        self.cooldown[trial.point] = ctx.clock.tick + 60
        ctx.memory.strategic.audit.append(StrategyAudit(
            ctx.clock.tick, trial.point, previous, trial.candidate, decision, inc_score, cand_score,
            trial.rationale,
            {"uses": trial.uses, "measure": "system reward+information per tick",
             "samples": [len(baseline), len(during)], "noise_threshold": round(spread, 4),
             "candidate_intention_reward": round(sum(trial.rewards) / max(1, len(trial.rewards)), 4)}))
        ctx.bus.publish(EventType.ADAPT_ADOPTED if adopt else EventType.ADAPT_REJECTED, "strategy_evolution",
                        {"point": trial.point, "incumbent": previous, "candidate": trial.candidate,
                         "incumbent_score": round(inc_score, 4), "candidate_score": round(cand_score, 4),
                         "noise_threshold": round(spread, 4), "rationale": trial.rationale})

    def to_dict(self, ctx: "CognitiveContext") -> dict[str, Any]:
        return {
            "points": [{"name": p.name, "description": p.description, "incumbent": p.incumbent,
                        "active": self.active_variant(p.name), "variants": list(p.variants),
                        "stats": [s.to_dict() for (pt, _), s in ctx.memory.strategic.stats.items() if pt == p.name]}
                       for p in self.points.values()],
            "trials": [{"point": t.point, "candidate": t.candidate, "uses": t.uses, "started": t.started_tick,
                        "rationale": t.rationale} for t in self.trials.values()],
            "audit": [a.to_dict() for a in ctx.memory.strategic.audit[-60:]],
        }
