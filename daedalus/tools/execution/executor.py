from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ...cognition.perception.observation import Percept
from ...core.events import EventType

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


@dataclass(slots=True)
class ToolResult:
    tool: str
    args: dict[str, Any]
    success: bool
    percept: Percept = field(default_factory=Percept)
    reason: str = ""
    energy_spent: float = 0.0
    damage: float = 0.0
    info: dict[str, Any] = field(default_factory=dict)


class ToolExecutor:
    """Executes external capabilities with a timeout and accounting."""

    def __init__(self, timeout: float = 5.0) -> None:
        self.timeout = timeout

    async def execute(self, ctx: "CognitiveContext", tool: str, args: dict[str, Any],
                      intention_id: str | None = None) -> ToolResult:
        ctx.tools.usage[tool] += 1
        try:
            result: ToolResult = await asyncio.wait_for(ctx.env.execute(tool, args), self.timeout)
        except asyncio.TimeoutError:
            result = ToolResult(tool, args, False, reason="timeout")
        if not result.success:
            ctx.tools.failures[tool] += 1
        ctx.bus.publish(
            EventType.ACTION if result.success else EventType.ACTION_FAILED,
            "executor",
            {"tool": tool, "args": args, "success": result.success, "reason": result.reason,
             "energy": result.energy_spent, "damage": result.damage, "intention": intention_id},
        )
        return result
