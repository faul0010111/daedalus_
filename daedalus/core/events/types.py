"""Event primitives. Every cognitive transition in DAEDALUS is an event."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class EventType:
    """Canonical event names, grouped by cognitive category (prefix before the dot)."""

    ENV_DYNAMICS = "environment.dynamics"

    PERCEPT = "perception.observed"
    PERCEPT_CHANGE = "perception.change"

    BELIEF_CREATED = "world.belief.created"
    BELIEF_REVISED = "world.belief.revised"
    CONTRADICTION = "world.contradiction.detected"
    CONTRADICTION_RESOLVED = "world.contradiction.resolved"
    HYPOTHESIS = "world.hypothesis.formed"

    INTENTION_PROPOSED = "intention.proposed"
    INTENTION_COMPLETED = "intention.completed"
    INTENTION_FAILED = "intention.failed"
    INTENTION_EXPIRED = "intention.expired"
    INTENTION_PREEMPTED = "intention.preempted"

    ATTENTION = "attention.allocated"

    GOAL_CREATED = "goal.created"
    GOAL_STATUS = "goal.status"
    GOAL_SPLIT = "goal.split"
    GOAL_MERGED = "goal.merged"

    PLAN = "deliberation.plan"
    NO_PLAN = "deliberation.no_plan"

    ACTION = "action.executed"
    ACTION_FAILED = "action.failed"

    OUTCOME = "evaluation.outcome"

    REFLECTION = "reflection.insight"

    ADAPT_TRIAL = "adaptation.trial_started"
    ADAPT_ADOPTED = "adaptation.adopted"
    ADAPT_REJECTED = "adaptation.rejected"
    POLICY_UPDATE = "adaptation.attention_policy"

    MEMORY_CONSOLIDATED = "memory.consolidated"

    DIAGNOSIS = "meta.diagnosis"

    AGENT_SPAWNED = "agent.spawned"
    AGENT_DISSOLVED = "agent.dissolved"

    RUNTIME = "runtime.lifecycle"


@dataclass(slots=True)
class Event:
    id: str
    type: str
    source: str
    tick: int
    payload: dict[str, Any] = field(default_factory=dict)
    causes: list[str] = field(default_factory=list)

    @property
    def category(self) -> str:
        return self.type.split(".", 1)[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "category": self.category,
            "source": self.source,
            "tick": self.tick,
            "payload": self.payload,
            "causes": self.causes,
        }
