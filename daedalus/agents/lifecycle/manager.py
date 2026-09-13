"""Creation, coordination and dissolution of temporary cognitive units."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.events import EventType
from ...goals import GoalStatus
from ..specialization import ROLES, CognitiveUnit

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


class AgentLifecycle:
    def __init__(self, max_units: int = 4, idle_limit: int = 80, max_age: int = 500) -> None:
        self.max_units = max_units
        self.idle_limit = idle_limit
        self.max_age = max_age
        self.units: dict[str, CognitiveUnit] = {}
        self.history: list[dict[str, Any]] = []
        self._seq = 0

    def processes(self) -> list[CognitiveUnit]:
        return list(self.units.values())

    def team_for(self, goal_id: str) -> list[CognitiveUnit]:
        return [u for u in self.units.values() if u.purpose_goal == goal_id]

    def spawn_team(self, ctx: "CognitiveContext", goal_id: str, roles: list[str], rationale: str) -> list[CognitiveUnit]:
        created = []
        for role in roles:
            if len(self.units) >= self.max_units:
                break
            self._seq += 1
            unit = ROLES[role](f"{role[:3]}{self._seq}", goal_id, ctx.clock.tick)
            self.units[unit.id] = unit
            created.append(unit)
            record = {"tick": ctx.clock.tick, "event": "spawned", "unit": unit.id, "role": role,
                      "purpose": goal_id, "rationale": rationale}
            self.history.append(record)
            ctx.metrics.inc("agent_topology_changes")
            ctx.bus.publish(EventType.AGENT_SPAWNED, "organization", record)
        return created

    def credit(self, source: str, tick: int) -> None:
        if source.startswith("agent:"):
            unit = self.units.get(source.split(":", 1)[1])
            if unit:
                unit.contributions += 1
                unit.last_contribution_tick = tick

    def upkeep(self, ctx: "CognitiveContext") -> None:
        tick = ctx.clock.tick
        by_goal: dict[str, list[CognitiveUnit]] = {}
        for unit in self.units.values():
            by_goal.setdefault(unit.purpose_goal, []).append(unit)
        for goal_id, team in by_goal.items():
            goal = ctx.goals.goals.get(goal_id)
            reason = None
            if goal is None or goal.status in (GoalStatus.ACHIEVED, GoalStatus.ABANDONED, GoalStatus.MERGED):
                reason = f"purpose complete ({goal.status.value if goal else 'missing'})"
            elif all(tick - u.last_contribution_tick > self.idle_limit for u in team):
                reason = "no contribution within idle limit"
            elif all(tick - u.created_tick > self.max_age for u in team):
                reason = "maximum team lifetime reached"
            if reason:
                self.dissolve_team(ctx, goal_id, reason)

    def dissolve_team(self, ctx: "CognitiveContext", goal_id: str, reason: str) -> None:
        team = self.team_for(goal_id)
        if not team:
            return
        tick = ctx.clock.tick
        contributions = {u.id: u.contributions for u in team}
        ctx.memory.semantic.upsert(
            f"team:{goal_id}:{min(u.created_tick for u in team)}", "team_outcome",
            f"Team {[u.role for u in team]} for {goal_id} dissolved at t{tick}: {reason}. "
            f"Contributions {contributions}.", 0.75, sum(contributions.values()), tick,
            roles=[u.role for u in team], lifetime=tick - min(u.created_tick for u in team), reason=reason)
        for unit in team:
            del self.units[unit.id]
            record = {"tick": tick, "event": "dissolved", "unit": unit.id, "role": unit.role, "purpose": goal_id,
                      "reason": reason, "contributions": unit.contributions}
            self.history.append(record)
            ctx.metrics.inc("agent_topology_changes")
            ctx.bus.publish(EventType.AGENT_DISSOLVED, "organization", record)
        ctx.metrics.inc("teams_dissolved")

    def to_dict(self) -> dict[str, Any]:
        return {"units": [u.describe() for u in self.units.values()], "history": self.history[-100:]}
