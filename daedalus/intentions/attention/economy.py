"""The Attention Economy: intentions compete; the winner earns the next moment of agency."""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ...core.events import EventType
from ..model import Intention, IntentionStatus
from ..prioritization import LearnedAttentionPolicy, PriorityStrategy, ScoreBreakdown

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


@dataclass(slots=True)
class Scored:
    intention: Intention
    breakdown: ScoreBreakdown
    final: float
    adjustments: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.intention.id, "key": self.intention.key, "kind": self.intention.kind.value,
                "description": self.intention.description, "final": round(self.final, 4),
                "base": self.breakdown.to_dict(),
                "adjustments": {k: round(v, 4) for k, v in self.adjustments.items() if abs(v) > 1e-4},
                "sources": sorted(self.intention.sources), "internal": self.intention.kind.internal}


@dataclass(slots=True)
class AttentionDecision:
    tick: int
    focal: Intention | None
    background: list[Intention]
    ranking: list[Scored]
    preempted: Intention | None = None
    temperature: float = 0.0

    def to_dict(self, top: int = 8) -> dict[str, Any]:
        return {"tick": self.tick, "focal": self.focal.id if self.focal else None,
                "focal_key": self.focal.key if self.focal else None,
                "background": [b.id for b in self.background],
                "preempted": self.preempted.key if self.preempted else None,
                "temperature": self.temperature, "ranking": [s.to_dict() for s in self.ranking[:top]],
                "candidates": len(self.ranking)}


class AttentionEconomy:
    def __init__(self, strategy: PriorityStrategy, policy: LearnedAttentionPolicy | None = None,
                 background_slots: int = 1, background_threshold: float = 0.55,
                 preempt_margin: float = 0.08, starvation_bonus: float = 0.0,
                 starvation_horizon: int = 150) -> None:
        self.strategy = strategy
        self.policy = policy
        self.background_slots = background_slots
        self.background_threshold = background_threshold
        self.preempt_margin = preempt_margin
        self.starvation_bonus = starvation_bonus
        self.starvation_horizon = starvation_horizon
        self.last_selected: dict[str, int] = {}
        self.focal_key: str | None = None
        self.outcomes: deque[tuple[int, str, bool]] = deque(maxlen=300)
        self.selection_log: deque[tuple[int, str]] = deque(maxlen=400)
        self.decisions = 0
        self.preemptions = 0

    def record_outcome(self, tick: int, key: str, success: bool) -> None:
        self.outcomes.append((tick, key, success))

    def _habituation(self, ctx: "CognitiveContext", intention: Intention) -> float:
        tick = ctx.clock.tick
        recent_failures = sum(1 for t, k, ok in self.outcomes if k == intention.key and not ok and tick - t < 40)
        penalty = 0.3 * recent_failures
        if intention.steps > 20:
            penalty += 0.015 * (intention.steps - 20)
        return penalty

    def allocate(self, ctx: "CognitiveContext") -> AttentionDecision:
        tick = ctx.clock.tick
        temperature = float(ctx.strategies.value("attention.temperature"))
        commitment = float(ctx.strategies.value("attention.commitment"))
        scored: list[Scored] = []
        for intention in ctx.pool.live.values():
            breakdown = self.strategy.score(intention, ctx)
            adj: dict[str, float] = {}
            if self.policy is not None:
                adj["learned_bias"] = self.policy.bias[intention.kind.value]
            if intention.support > 1:
                adj["support"] = 0.08 * math.log2(intention.support)
            adj["habituation"] = -self._habituation(ctx, intention)
            if self.starvation_bonus > 0 and not intention.kind.internal:
                # optimism toward a kind attention has stopped choosing: without it,
                # an early lead compounds into permanent specialization
                since = tick - self.last_selected.get(intention.kind.value, 0)
                adj["starvation"] = self.starvation_bonus * min(1.0, since / self.starvation_horizon)
            if intention.key == self.focal_key:
                adj["commitment"] = commitment
            final = breakdown.total + sum(adj.values())
            intention.last_score = final
            scored.append(Scored(intention, breakdown, final, adj))
        scored.sort(key=lambda s: s.final, reverse=True)

        focal: Scored | None = None
        if scored:
            if temperature <= 1e-3:
                focal = scored[0]
            else:
                top = scored[:12]
                m = max(s.final for s in top)
                weights = [math.exp((s.final - m) / temperature) for s in top]
                focal = ctx.rng.choices(top, weights=weights, k=1)[0]

        preempted = None
        if focal and self.focal_key and focal.intention.key != self.focal_key and not focal.intention.kind.internal:
            previous = ctx.pool.live.get(self.focal_key)
            if previous is not None and previous.status is IntentionStatus.ACTIVE:
                incumbent = next((s for s in scored if s.intention.key == self.focal_key), None)
                if incumbent is not None and focal.final < incumbent.final + self.preempt_margin:
                    focal = incumbent  # challenger not strong enough to justify switching
                else:
                    preempted = previous
                    previous.status = IntentionStatus.CANDIDATE
                    self.preemptions += 1
                    ctx.bus.publish(EventType.INTENTION_PREEMPTED, "attention",
                                    {"preempted": previous.key, "by": focal.intention.key,
                                     "incumbent_score": round(incumbent.final, 3) if incumbent else None,
                                     "challenger_score": round(focal.final, 3)})

        background: list[Intention] = []
        for s in scored:
            if len(background) >= self.background_slots:
                break
            if s is focal or not s.intention.kind.internal:
                continue
            if s.final >= self.background_threshold:
                background.append(s.intention)

        decision = AttentionDecision(tick, focal.intention if focal else None, background, scored,
                                     preempted, temperature)
        if focal:
            fi = focal.intention
            if not fi.kind.internal:
                self.focal_key = fi.key
            fi.selections += 1
            if fi.status is IntentionStatus.CANDIDATE:
                fi.status = IntentionStatus.ACTIVE
                fi.activated_tick = fi.activated_tick or tick
            self.selection_log.append((tick, fi.kind.value))
            self.last_selected[fi.kind.value] = tick
            ctx.bus.publish(EventType.ATTENTION, "attention",
                            {"focal": fi.key, "kind": fi.kind.value, "score": round(focal.final, 3),
                             "contributions": focal.breakdown.to_dict()["contributions"],
                             "runner_up": scored[1].intention.key if len(scored) > 1 and scored[1] is not focal
                             else (scored[0].intention.key if scored[0] is not focal else None),
                             "candidates": len(scored),
                             "background": [b.key for b in background]})
        for b in background:
            b.selections += 1
        self.decisions += 1
        ctx.tracer.record_decision(decision)
        return decision

    def release(self, key: str) -> None:
        if self.focal_key == key:
            self.focal_key = None
