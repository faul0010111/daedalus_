from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GoalStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"
    ACHIEVED = "achieved"
    ABANDONED = "abandoned"
    MERGED = "merged"

    @property
    def open(self) -> bool:
        return self in (GoalStatus.PROPOSED, GoalStatus.ACTIVE, GoalStatus.BLOCKED, GoalStatus.SUSPENDED)


class GoalKind(str, Enum):
    ACHIEVE = "achieve"    # make a fact true
    KNOW = "know"          # find a binding for a pattern with variables
    MAINTAIN = "maintain"  # keep a quantity above a threshold


class EdgeKind(str, Enum):
    SUBGOAL = "subgoal_of"
    DEPENDS = "depends_on"
    MERGED = "merged_into"


@dataclass
class Goal:
    id: str
    description: str
    kind: GoalKind
    pattern: tuple[str, str, str] | None = None
    quantity: str | None = None
    threshold: float = 0.0
    comfort: float = 0.0   # the level that actually satisfies this goal, not just clears its floor
    importance: float = 0.5
    origin: str = "developer"          # developer | emergent:<engine>
    persistent: bool = False            # re-opens if its condition stops holding
    status: GoalStatus = GoalStatus.ACTIVE
    created_tick: int = 0
    updated_tick: int = 0
    achieved_tick: int | None = None
    stalls: int = 0
    attempts: int = 0
    failures: int = 0
    block_reason: str = ""
    history: list[tuple[int, str, str]] = field(default_factory=list)

    @property
    def emergent(self) -> bool:
        return self.origin.startswith("emergent")

    @property
    def signature(self) -> str:
        if self.kind is GoalKind.MAINTAIN:
            return f"maintain:{self.quantity}>={self.threshold}"
        return f"{self.kind.value}:{'|'.join(self.pattern or ())}"

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "description": self.description, "kind": self.kind.value,
                "pattern": list(self.pattern) if self.pattern else None, "quantity": self.quantity,
                "threshold": self.threshold, "comfort": self.comfort, "importance": round(self.importance, 3),
                "origin": self.origin, "persistent": self.persistent, "status": self.status.value,
                "created": self.created_tick, "updated": self.updated_tick,
                "achieved": self.achieved_tick, "stalls": self.stalls, "attempts": self.attempts,
                "failures": self.failures, "block_reason": self.block_reason,
                "history": self.history[-20:]}
