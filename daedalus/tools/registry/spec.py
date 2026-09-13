"""Capability declarations. This is where the developer engineers what is *possible*."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Iterable

if TYPE_CHECKING:
    from ...cognition.planning.state import PlanDomain, PlanState

Fact = tuple[str, str, str]


@dataclass(slots=True)
class Precondition:
    fact: Fact
    positive: bool = True
    relaxable: bool = False  # planner may assume it can be achieved later (reveals blockers)


@dataclass
class ToolSpec:
    name: str
    description: str
    category: str  # action | epistemic | maintenance | cognitive
    params: list[str] = field(default_factory=list)
    energy_cost: float = 0.0
    # forward planning model
    ground: Callable[["PlanState", "PlanDomain"], Iterable[dict[str, Any]]] | None = None
    check: Callable[["PlanState", dict[str, Any], "PlanDomain"], list[Precondition]] | None = None
    apply: Callable[["PlanState", dict[str, Any], "PlanDomain"], "PlanState"] | None = None
    step_cost: Callable[["PlanState", dict[str, Any], "PlanDomain"], float] | None = None
    support: Callable[["PlanState", dict[str, Any], "PlanDomain"], list[Fact]] | None = None
    instrumental: Callable[["PlanDomain"], set[str]] | None = None
    # regression model (used for knowledge-gap analysis)
    produces: Fact | None = None
    requires: Callable[[dict[str, str]], list[Fact]] | None = None
    knowledge: Callable[[dict[str, str]], list[Fact]] | None = None
    # declarative effects on resources and sources
    restores: dict[str, float] = field(default_factory=dict)
    consumes_type: str | None = None   # the entity type this tool spends, e.g. "fuel"
    maintains: str | None = None
    reveals: set[str] = field(default_factory=set)
    reach: int = 0  # epistemic tools: how far (in edges) the tool can observe

    @property
    def plannable(self) -> bool:
        return self.ground is not None and self.apply is not None

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "category": self.category,
                "params": self.params, "energy_cost": self.energy_cost, "restores": self.restores,
                "consumes_type": self.consumes_type,
                "maintains": self.maintains, "reveals": sorted(self.reveals)}
