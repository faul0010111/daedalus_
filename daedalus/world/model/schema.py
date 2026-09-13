"""Declarative description of what can be believed about an environment.

The schema is an *engineered capability*: it tells the world model how
predicates behave (functional, volatile, epistemic) without telling the agent
what to do with them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

Fact = tuple[str, str, str]


@dataclass
class WorldSchema:
    functional: set[str] = field(default_factory=set)          # subject -> at most one object
    inverse_functional: set[str] = field(default_factory=set)  # object  -> at most one subject
    volatile: dict[str, float] = field(default_factory=dict)   # predicate -> drift rate toward prior per tick
    priors: dict[str, float] = field(default_factory=dict)     # predicate -> prior P(true)
    epistemic: set[str] = field(default_factory=set)           # predicates describing what an entity "holds"
    fluents: set[str] = field(default_factory=set)             # predicates changed by actions (planning)
    explorable_type: str = "location"
    agent_id: str = "agent"
    position_predicate: str = "at"
    edge_predicate: str = "connected"

    def prior(self, predicate: str) -> float:
        return self.priors.get(predicate, 0.5)
