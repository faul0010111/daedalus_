from __future__ import annotations

from collections import Counter

from .spec import ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self.usage: Counter[str] = Counter()
        self.failures: Counter[str] = Counter()

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    def all(self, category: str | None = None) -> list[ToolSpec]:
        return [t for t in self._tools.values() if category is None or t.category == category]

    def plannable(self, categories: tuple[str, ...] = ("action",)) -> list[ToolSpec]:
        return [t for t in self._tools.values() if t.plannable and t.category in categories]

    def restorers(self, quantity: str) -> list[ToolSpec]:
        return [t for t in self._tools.values() if t.restores.get(quantity, 0) > 0]

    def restorer_types(self, quantity: str) -> dict[str, "ToolSpec"]:
        """Entity types that, when consumed, restore a quantity — as declared, not assumed."""
        return {t.consumes_type: t for t in self._tools.values()
                if t.consumes_type and t.restores.get(quantity, 0) > 0}

    def epistemic(self) -> list[ToolSpec]:
        return [t for t in self._tools.values() if t.category == "epistemic"]

    def describe(self) -> list[dict]:
        return [t.describe() | {"calls": self.usage[t.name], "failures": self.failures[t.name]}
                for t in self._tools.values()]
