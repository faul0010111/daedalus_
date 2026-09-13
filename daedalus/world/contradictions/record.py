from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Contradiction:
    id: str
    key: tuple[str, str, str]
    tick: int
    prior_confidence: float
    new_confidence: float
    source: str
    severity: float
    resolved_tick: int | None = None
    resolution: str = ""

    @property
    def open(self) -> bool:
        return self.resolved_tick is None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "key": list(self.key), "tick": self.tick,
                "prior": round(self.prior_confidence, 3), "new": round(self.new_confidence, 3),
                "source": self.source, "severity": round(self.severity, 3),
                "resolved_tick": self.resolved_tick, "resolution": self.resolution}
