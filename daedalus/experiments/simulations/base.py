"""The environment port. Anything that can be sensed and acted upon can host DAEDALUS."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...cognition.perception import Percept
    from ...tools import ToolSpec
    from ...tools.execution import ToolResult
    from ...world import WorldModel, WorldSchema


class Environment(ABC):
    name: str = "environment"
    schema: "WorldSchema"

    @abstractmethod
    def capabilities(self) -> list["ToolSpec"]: ...

    @abstractmethod
    def sources(self) -> dict[str, float]:
        """Observation sources and the reliability they *claim*."""

    @abstractmethod
    def initial_goals(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def sense(self) -> "Percept": ...

    @abstractmethod
    async def execute(self, tool: str, args: dict[str, Any]) -> "ToolResult": ...

    @abstractmethod
    def advance(self, tick: int) -> list[dict[str, Any]]:
        """Hidden environment dynamics. Returned records are for observability only."""

    @abstractmethod
    def traversal_blocked(self, world: "WorldModel", a: str, b: str) -> bool: ...

    @abstractmethod
    def ground_truth(self) -> dict[str, Any]: ...

    @abstractmethod
    def task_metrics(self) -> dict[str, float]: ...

    def layout(self) -> dict[str, tuple[float, float]]:
        """Optional 2D positions for entities, used only by the console."""
        return {}

    def to_dict(self) -> dict[str, Any]:
        return {}

    def load_dict(self, data: dict[str, Any]) -> None:
        return None
