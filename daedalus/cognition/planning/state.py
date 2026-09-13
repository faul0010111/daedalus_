"""Symbolic planning state derived from beliefs above a confidence threshold."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...world.model import WorldModel

Fact = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class PlanState:
    fluents: frozenset[Fact]

    def has(self, s: str, p: str, o: str) -> bool:
        return (s, p, o) in self.fluents

    def objects(self, s: str, p: str) -> list[str]:
        return sorted(f[2] for f in self.fluents if f[0] == s and f[1] == p)

    def subjects(self, p: str, o: str) -> list[str]:
        return sorted(f[0] for f in self.fluents if f[1] == p and f[2] == o)

    def where(self, p: str) -> list[Fact]:
        return sorted(f for f in self.fluents if f[1] == p)

    def with_changes(self, add: list[Fact] = (), remove: list[Fact] = ()) -> "PlanState":
        return PlanState((self.fluents - frozenset(remove)) | frozenset(add))


class PlanDomain:
    def __init__(self, world: "WorldModel", threshold: float, relevant: set[str] | None = None) -> None:
        self.world = world
        self.threshold = threshold
        self.relevant: set[str] = set(relevant or ())
        fluents = world.schema.fluents
        self._static: set[Fact] = set()
        self._s_idx: dict[tuple[str, str], list[str]] = defaultdict(list)
        self._o_idx: dict[tuple[str, str], list[str]] = defaultdict(list)
        initial: set[Fact] = set()
        for key, b in world.beliefs.items():
            if b.confidence < threshold:
                continue
            if key[1] in fluents:
                initial.add(key)
            else:
                self._static.add(key)
                self._s_idx[(key[0], key[1])].append(key[2])
                self._o_idx[(key[1], key[2])].append(key[0])
        self.initial = PlanState(frozenset(initial))

    def static(self, s: str, p: str, o: str) -> bool:
        return (s, p, o) in self._static

    def objects(self, s: str, p: str) -> list[str]:
        return self._s_idx.get((s, p), [])

    def subjects(self, p: str, o: str) -> list[str]:
        return self._o_idx.get((p, o), [])

    def conf(self, s: str, p: str, o: str, default: float | None = None) -> float:
        return self.world.confidence(s, p, o, default)
