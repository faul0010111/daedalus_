from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .update import binary_entropy


class EpistemicStatus(str, Enum):
    OBSERVED_FACT = "observed_fact"
    INFERRED_BELIEF = "inferred_belief"
    HYPOTHESIS = "hypothesis"
    UNCERTAIN = "uncertain"
    CONTRADICTED = "contradicted"


@dataclass(slots=True)
class Evidence:
    source: str
    tick: int
    positive: bool
    reliability: float


@dataclass(slots=True)
class Belief:
    subject: str
    predicate: str
    object: str
    confidence: float
    prior: float
    status: EpistemicStatus
    created_tick: int
    updated_tick: int
    evidence: list[Evidence] = field(default_factory=list)
    history: list[tuple[int, float]] = field(default_factory=list)
    contradiction_open: bool = False
    rationale: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.subject, self.predicate, self.object)

    @property
    def entropy(self) -> float:
        return binary_entropy(self.confidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "s": self.subject, "p": self.predicate, "o": self.object,
            "confidence": round(self.confidence, 4), "status": self.status.value,
            "created": self.created_tick, "updated": self.updated_tick,
            "evidence": len(self.evidence), "contradiction": self.contradiction_open,
            "history": self.history[-12:], "rationale": self.rationale,
        }
