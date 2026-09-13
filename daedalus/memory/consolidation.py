"""Memory consolidation: experiences become reusable statistics and lessons."""
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from ..core.events import EventType
from ..intentions.generators.base import IntentionGenerator
from ..intentions.model import Intention, IntentionFeatures, IntentionKind

if TYPE_CHECKING:
    from ..core.cognition.context import CognitiveContext


class MemoryConsolidationLoop(IntentionGenerator):
    name = "memory_consolidation"
    period = 7
    phase = 4

    def step(self, ctx: "CognitiveContext") -> None:
        pending = sum(1 for e in ctx.memory.episodic.episodes.values() if not e.consolidated)
        self.last_pressure = pending / 100
        if pending < 30:
            return
        self.propose(ctx, "consolidate", IntentionKind.CONSOLIDATE_MEMORY,
                     f"Consolidate {pending} episodes into semantic memory",
                     {"type": "cognitive", "op": "consolidate"},
                     IntentionFeatures(goal_alignment=0.2, expected_value=min(1.0, pending / 120) * 0.6,
                                       urgency=0.4 if pending > 150 else 0.1, confidence=0.95, resource_cost=0.02,
                                       uncertainty_reduction=0.1,
                                       historical_success_rate=ctx.memory.success_rate("consolidate_memory")))

    def execute(self, ctx: "CognitiveContext", intention: Intention | None) -> dict:
        episodes = ctx.memory.episodic.unconsolidated()
        groups = defaultdict(list)
        for ep in episodes:
            groups[ep.signature].append(ep)
        tick = ctx.clock.tick
        updated = 0
        for signature, eps in groups.items():
            existing = ctx.memory.semantic.get(f"stat:{signature}")
            n_prev = existing.data.get("n", 0) if existing else 0
            s_prev = existing.data.get("successes", 0) if existing else 0
            r_prev = existing.data.get("reward_sum", 0.0) if existing else 0.0
            n = n_prev + len(eps)
            successes = s_prev + sum(e.success for e in eps)
            reward_sum = r_prev + sum(e.reward for e in eps)
            rate = successes / n
            ctx.memory.semantic.upsert(
                f"stat:{signature}", "statistic",
                f"{signature}: {rate:.0%} success over {n} episodes, mean reward {reward_sum / n:+.3f}",
                min(0.99, 0.5 + n / 200), n, tick, [e.id for e in eps[-10:]],
                n=n, successes=successes, reward_sum=round(reward_sum, 4), success_rate=round(rate, 4))
            updated += 1
            for e in eps:
                e.consolidated = True
        pruned = ctx.memory.episodic.prune()
        ctx.metrics.inc("consolidations")
        ctx.bus.publish(EventType.MEMORY_CONSOLIDATED, self.name,
                        {"episodes": len(episodes), "signatures": updated, "pruned": pruned})
        return {"episodes": len(episodes), "signatures": updated, "pruned": pruned}
