from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Observation:
    subject: str
    predicate: str
    object: str
    positive: bool = True
    reliability: float = 0.9
    source: str = "perception"

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.subject, self.predicate, self.object)


@dataclass(slots=True)
class Percept:
    """Everything an environment reports at once: facts, coverage and quantities."""

    observations: list[Observation] = field(default_factory=list)
    # (entity, predicate, reliability, source): 'I examined this; anything not reported is absent'
    coverage: list[tuple[str, str, float, str]] = field(default_factory=list)
    quantities: dict[str, float] = field(default_factory=dict)
    signals: dict[str, Any] = field(default_factory=dict)
