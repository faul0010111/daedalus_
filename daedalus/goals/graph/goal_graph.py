"""Dynamic Goal Graph: goals emerge, split, merge, suspend, get abandoned and reactivate."""
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Iterable

from ...core.events import EventType
from .goal import EdgeKind, Goal, GoalKind, GoalStatus

if TYPE_CHECKING:
    from ...core.events import EventBus


class GoalGraph:
    def __init__(self, bus: "EventBus", tick_provider) -> None:
        self.bus = bus
        self._tick = tick_provider
        self.goals: dict[str, Goal] = {}
        self.edges: list[tuple[str, str, EdgeKind, int]] = []  # (child, parent, kind, tick)
        self._parents: dict[str, set[str]] = defaultdict(set)
        self._children: dict[str, set[str]] = defaultdict(set)
        self._seq = 0
        self.transitions: list[dict[str, Any]] = []

    # ---------------------------------------------------------------- creation
    def add(self, description: str, kind: GoalKind, *, pattern=None, quantity=None, threshold=0.0,
            comfort: float | None = None, importance=0.5, origin="developer", persistent=False,
            parent: str | None = None, reason: str = "") -> Goal:
        self._seq += 1
        tick = self._tick()
        if comfort is None:
            comfort = min(threshold * 2.2, 95.0) if kind is GoalKind.MAINTAIN else 0.0
        goal = Goal(f"g{self._seq}", description, kind, tuple(pattern) if pattern else None, quantity,
                    threshold, comfort, importance, origin, persistent, GoalStatus.ACTIVE, tick, tick)
        goal.history.append((tick, "active", reason or "created"))
        self.goals[goal.id] = goal
        if parent:
            self.link(goal.id, parent, EdgeKind.SUBGOAL)
        self.bus.publish(EventType.GOAL_CREATED, origin,
                         goal.to_dict() | {"parent": parent, "reason": reason})
        self.transitions.append({"tick": tick, "goal": goal.id, "to": "active", "reason": reason or "created"})
        return goal

    def link(self, child: str, parent: str, kind: EdgeKind) -> None:
        if parent in self._parents[child] or child == parent or self._creates_cycle(child, parent):
            return
        self._parents[child].add(parent)
        self._children[parent].add(child)
        self.edges.append((child, parent, kind, self._tick()))

    def _creates_cycle(self, child: str, parent: str) -> bool:
        stack, seen = [parent], set()
        while stack:
            g = stack.pop()
            if g == child:
                return True
            if g in seen:
                continue
            seen.add(g)
            stack.extend(self._parents.get(g, ()))
        return False

    def find_open(self, signature: str) -> Goal | None:
        for g in self.goals.values():
            if g.signature == signature and g.status.open:
                return g
        return None

    # -------------------------------------------------------------- transitions
    def transition(self, goal_id: str, status: GoalStatus, reason: str) -> None:
        g = self.goals[goal_id]
        if g.status is status:
            g.block_reason = reason if status is GoalStatus.BLOCKED else g.block_reason
            return
        tick = self._tick()
        previous = g.status
        g.status = status
        g.updated_tick = tick
        g.block_reason = reason if status is GoalStatus.BLOCKED else ""
        if status is GoalStatus.ACHIEVED:
            g.achieved_tick = tick
        g.history.append((tick, status.value, reason))
        self.transitions.append({"tick": tick, "goal": goal_id, "from": previous.value,
                                 "to": status.value, "reason": reason})
        self.bus.publish(EventType.GOAL_STATUS, "goal_graph",
                         {"goal": goal_id, "description": g.description, "from": previous.value,
                          "to": status.value, "reason": reason, "emergent": g.emergent})

    def merge(self, keep: str, absorb: str, reason: str) -> None:
        for parent in list(self._parents.get(absorb, ())):
            self.link(keep, parent, EdgeKind.SUBGOAL)
        self.edges.append((absorb, keep, EdgeKind.MERGED, self._tick()))
        self.transition(absorb, GoalStatus.MERGED, f"merged into {keep}: {reason}")
        self.bus.publish(EventType.GOAL_MERGED, "goal_graph", {"keep": keep, "absorbed": absorb,
                                                               "reason": reason})

    # ------------------------------------------------------------------ queries
    def parents(self, goal_id: str) -> list[Goal]:
        return [self.goals[p] for p in self._parents.get(goal_id, ())]

    def children(self, goal_id: str) -> list[Goal]:
        return [self.goals[c] for c in self._children.get(goal_id, ())]

    def depth(self, goal_id: str) -> int:
        parents = self._parents.get(goal_id)
        if not parents:
            return 0
        return 1 + min(self.depth(p) for p in parents)

    def descendants(self, goal_id: str) -> list[Goal]:
        out, stack, seen = [], list(self._children.get(goal_id, ())), set()
        while stack:
            g = stack.pop()
            if g in seen:
                continue
            seen.add(g)
            out.append(self.goals[g])
            stack.extend(self._children.get(g, ()))
        return out

    def roots(self) -> list[Goal]:
        return [g for g in self.goals.values() if not self._parents.get(g.id)]

    def open_goals(self, kinds: Iterable[GoalKind] | None = None) -> list[Goal]:
        kinds = set(kinds) if kinds else None
        return [g for g in self.goals.values() if g.status.open and (kinds is None or g.kind in kinds)]

    def value(self, goal_id: str) -> float:
        """Importance propagated down the graph: a subgoal matters as much as what it serves."""
        g = self.goals[goal_id]
        parents = [p for p in self.parents(goal_id) if p.status.open]
        inherited = max((self.value(p.id) * 0.9 for p in parents), default=0.0)
        return min(1.0, max(g.importance, inherited))

    def root_of(self, goal_id: str) -> Goal:
        g = self.goals[goal_id]
        parents = self.parents(goal_id)
        return self.root_of(parents[0].id) if parents else g

    def achieved_value(self) -> float:
        return sum(g.importance for g in self.goals.values() if g.status is GoalStatus.ACHIEVED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goals": [g.to_dict() | {"depth": self.depth(g.id), "value": round(self.value(g.id), 3),
                                     "parents": sorted(self._parents.get(g.id, ()))}
                      for g in self.goals.values()],
            "edges": [{"child": c, "parent": p, "kind": k.value, "tick": t} for c, p, k, t in self.edges],
            "transitions": self.transitions[-200:],
        }
