from __future__ import annotations

from typing import TYPE_CHECKING

from ..graph import Goal, GoalKind

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


def goal_urgency(ctx: "CognitiveContext", goal: Goal) -> float:
    """Urgency is a property of state, not of the goal: maintain goals grow urgent as they erode."""
    if goal.kind is GoalKind.MAINTAIN and goal.quantity:
        value = ctx.world.quantities.get(goal.quantity)
        if value is None or goal.comfort <= goal.threshold:
            return 0.0
        # urgency reaches zero exactly where the goal is satisfied. If it decayed
        # sooner, the agent would abandon its own recovery halfway and oscillate
        # just above its floor, never accumulating a usable buffer.
        slack = (value - goal.threshold) / (goal.comfort - goal.threshold)
        return max(0.0, min(1.0, 1.0 - slack))
    age = ctx.clock.tick - goal.created_tick
    return min(0.35, 0.05 + age / 4000.0)
