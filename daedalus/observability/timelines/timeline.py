from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...core.events import EventBus

QUIET = {"world.belief.created", "intention.proposed", "perception.change", "deliberation.plan",
         "evaluation.outcome", "action.executed", "attention.allocated"}


def cognitive_timeline(bus: "EventBus", limit: int = 250, include_quiet: bool = False,
                       since_tick: int | None = None) -> list[dict[str, Any]]:
    events = [e for e in bus.history if (include_quiet or e.type not in QUIET)
              and (since_tick is None or e.tick >= since_tick)]
    return [e.to_dict() for e in events[-limit:]]
