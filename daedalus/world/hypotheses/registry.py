"""Hypotheses are beliefs with an explicit test: what evidence would confirm them."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Hypothesis:
    id: str
    statement: str
    key: tuple[str, str, str]
    formed_tick: int
    origin: str
    test: str
    support: int = 0
    refutations: int = 0
    status: str = "open"  # open | supported | refuted
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "statement": self.statement, "key": list(self.key),
                "formed": self.formed_tick, "origin": self.origin, "test": self.test,
                "support": self.support, "refutations": self.refutations, "status": self.status}


class HypothesisRegistry:
    def __init__(self) -> None:
        self.items: dict[str, Hypothesis] = {}
        self._seq = 0

    def form(self, statement: str, key: tuple[str, str, str], tick: int, origin: str, test: str,
             **data: Any) -> Hypothesis:
        for h in self.items.values():
            if h.key == key and h.status == "open":
                return h
        self._seq += 1
        h = Hypothesis(f"h{self._seq}", statement, key, tick, origin, test, data=dict(data))
        self.items[h.id] = h
        return h

    def record(self, hypothesis_id: str, supports: bool) -> Hypothesis:
        h = self.items[hypothesis_id]
        if supports:
            h.support += 1
        else:
            h.refutations += 1
        if h.support >= 3 and h.support >= 2 * h.refutations:
            h.status = "supported"
        elif h.refutations >= 3 and h.refutations > h.support:
            h.status = "refuted"
        return h

    def open(self) -> list[Hypothesis]:
        return [h for h in self.items.values() if h.status == "open"]
