"""The intention pool: proposals persist only while something keeps proposing them."""
from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from ..core.events import EventType
from .model import Intention, IntentionStatus

if TYPE_CHECKING:
    from ..core.cognition.context import CognitiveContext


class IntentionPool:
    def __init__(self, ttl: int = 4, capacity: int = 80) -> None:
        self.ttl = ttl
        self.capacity = capacity
        self.live: dict[str, Intention] = {}
        self.archive: deque[Intention] = deque(maxlen=400)
        self._seq = 0
        self.proposals = 0
        self._tick_sources: dict[str, tuple[int, set[str]]] = {}

    def propose(self, ctx: "CognitiveContext", intention: Intention, source: str) -> Intention:
        self.proposals += 1
        tick = ctx.clock.tick
        existing = self.live.get(intention.key)
        seen_tick, seen = self._tick_sources.get(intention.key, (-1, set()))
        if seen_tick != tick:
            seen = set()
        seen.add(source)
        self._tick_sources[intention.key] = (tick, seen)
        if existing:
            existing.support = len(seen)
            existing.sources.add(source)
            existing.features = intention.features
            existing.description = intention.description
            existing.last_proposed_tick = tick
            if intention.goal_id and not existing.goal_id:
                existing.goal_id = intention.goal_id
            existing.target.update({k: v for k, v in intention.target.items() if k not in existing.target})
            return existing
        if len(self.live) >= self.capacity:
            weakest = min((i for i in self.live.values() if i.status is IntentionStatus.CANDIDATE),
                          key=lambda i: i.last_score, default=None)
            if weakest is None:
                return intention
            self._retire(ctx, weakest, IntentionStatus.EXPIRED, "displaced by capacity")
        self._seq += 1
        intention.id = f"i{self._seq}"
        intention.created_tick = tick
        intention.last_proposed_tick = tick
        intention.sources.add(source)
        self.live[intention.key] = intention
        ctx.bus.publish(EventType.INTENTION_PROPOSED, source,
                        {"id": intention.id, "key": intention.key, "kind": intention.kind.value,
                         "description": intention.description, "goal": intention.goal_id})
        return intention

    def expire_stale(self, ctx: "CognitiveContext", protected: set[str]) -> None:
        tick = ctx.clock.tick
        for intention in list(self.live.values()):
            if intention.key in protected:
                continue
            if tick - intention.last_proposed_tick > self.ttl:
                self._retire(ctx, intention, IntentionStatus.EXPIRED, "no longer proposed")

    def finish(self, ctx: "CognitiveContext", intention: Intention, status: IntentionStatus,
               outcome: str) -> None:
        self._retire(ctx, intention, status, outcome)

    def _retire(self, ctx: "CognitiveContext", intention: Intention, status: IntentionStatus,
                outcome: str) -> None:
        self.live.pop(intention.key, None)
        self._tick_sources.pop(intention.key, None)
        intention.status = status
        intention.outcome = outcome
        self.archive.append(intention)
        event = {IntentionStatus.COMPLETED: EventType.INTENTION_COMPLETED,
                 IntentionStatus.FAILED: EventType.INTENTION_FAILED}.get(status, EventType.INTENTION_EXPIRED)
        if status is IntentionStatus.EXPIRED and intention.selections == 0:
            return  # silent: never-attended candidates fading away is normal pressure dynamics
        ctx.bus.publish(event, "intention_pool",
                        {"id": intention.id, "key": intention.key, "kind": intention.kind.value,
                         "outcome": outcome, "reward": round(intention.reward, 3),
                         "steps": intention.steps, "goal": intention.goal_id})
