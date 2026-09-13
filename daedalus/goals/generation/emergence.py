"""Goal emergence: turning gaps and blockers into new goals, with deduplication."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.events import EventType
from ..graph import EdgeKind, Goal, GoalKind, GoalStatus

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


def _describe(kind: GoalKind, pattern: tuple[str, str, str]) -> str:
    s, p, o = pattern
    if kind is GoalKind.KNOW:
        unknown = [t for t in pattern if t.startswith("?")]
        return f"Discover {' '.join(unknown)} such that {s} {p} {o}"
    return f"Make true: {s} {p} {o}"


class GoalEmergence:
    def __init__(self, max_depth: int = 4, max_open: int = 24) -> None:
        self.max_depth = max_depth
        self.max_open = max_open

    def spawn(self, ctx: "CognitiveContext", parents: list[Goal], kind: GoalKind,
              patterns: list[tuple[str, str, str]], reason: str, engine: str) -> list[Goal]:
        graph = ctx.goals
        created: list[Goal] = []
        linked: list[Goal] = []
        for parent in parents:
            if graph.depth(parent.id) + 1 > self.max_depth:
                return []
        for pattern in patterns:
            signature = f"{kind.value}:{'|'.join(pattern)}"
            existing = graph.find_open(signature)
            if existing:
                for parent in parents:
                    if parent.id not in {p.id for p in graph.parents(existing.id)} and parent.id != existing.id:
                        graph.link(existing.id, parent.id, EdgeKind.SUBGOAL)
                        ctx.bus.publish(EventType.GOAL_MERGED, engine,
                                        {"keep": existing.id, "absorbed": None, "new_parent": parent.id,
                                         "reason": f"shared dependency: {reason}"})
                if existing.status is GoalStatus.SUSPENDED:
                    graph.transition(existing.id, GoalStatus.ACTIVE, "needed again")
                linked.append(existing)
                continue
            if len(graph.open_goals()) >= self.max_open:
                break
            importance = max((graph.value(p.id) for p in parents), default=0.5) * 0.95
            goal = graph.add(_describe(kind, pattern), kind, pattern=pattern, importance=importance,
                             origin=f"emergent:{engine}", parent=parents[0].id if parents else None,
                             reason=reason)
            for extra in parents[1:]:
                graph.link(goal.id, extra.id, EdgeKind.SUBGOAL)
            ctx.metrics.inc("emergent_goals")
            created.append(goal)
        if len(created) > 1 and parents:
            ctx.bus.publish(EventType.GOAL_SPLIT, engine,
                            {"parent": parents[0].id, "children": [g.id for g in created], "reason": reason})
        return created + linked
