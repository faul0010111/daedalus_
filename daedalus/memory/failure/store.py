from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class FailureRecord:
    id: str
    tick: int
    tool: str
    args: dict[str, Any]
    reason: str
    intention_kind: str
    context: dict[str, Any] = field(default_factory=dict)
    recovered_tick: int | None = None
    diagnosed_cause: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FailureMemory:
    def __init__(self, capacity: int = 1500) -> None:
        self.records: list[FailureRecord] = []
        self.capacity = capacity
        self._seq = 0

    def record(self, tick: int, tool: str, args: dict[str, Any], reason: str, intention_kind: str,
               **context: Any) -> FailureRecord:
        self._seq += 1
        rec = FailureRecord(f"f{self._seq}", tick, tool, args, reason, intention_kind, context)
        self.records.append(rec)
        if len(self.records) > self.capacity:
            del self.records[0]
        return rec

    def patterns(self, since_tick: int = 0) -> Counter[tuple[str, str]]:
        return Counter((r.tool, r.reason) for r in self.records if r.tick >= since_tick)

    def mark_recovered(self, tool: str, tick: int) -> None:
        for rec in reversed(self.records):
            if rec.tool == tool and rec.recovered_tick is None:
                rec.recovered_tick = tick
                return
