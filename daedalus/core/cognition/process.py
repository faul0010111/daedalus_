"""The base unit of cognition: a persistent process with its own cadence.

Processes never call each other. They read shared state, publish events and
propose intentions. Which process "wins" is decided by the attention economy.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import CognitiveContext


class CognitiveProcess(ABC):
    name: str = "process"
    period: int = 1  # run every `period` ticks
    phase: int = 0   # offset, so processes with equal periods spread over time

    def __init__(self) -> None:
        self.runs = 0
        self.last_pressure = 0.0

    def due(self, tick: int) -> bool:
        return (tick + self.phase) % max(1, self.period) == 0

    async def run(self, ctx: "CognitiveContext") -> None:
        self.runs += 1
        self.step(ctx)

    @abstractmethod
    def step(self, ctx: "CognitiveContext") -> None: ...

    def describe(self) -> dict:
        return {"name": self.name, "period": self.period, "runs": self.runs,
                "pressure": round(self.last_pressure, 3)}
