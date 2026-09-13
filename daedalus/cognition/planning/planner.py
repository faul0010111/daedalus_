"""Generic best-first planner over believed state, with precondition relaxation.

When the goal is unreachable under current beliefs, relaxable preconditions may
be violated at a penalty. The cheapest violating plan reveals *blockers*: facts
that, if made true, would unlock the goal. Blockers are how dependencies
become emergent subgoals.
"""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from ...world.model import is_var
from .state import PlanDomain, PlanState

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext
    from ...tools import Precondition

Fact = tuple[str, str, str]
Step = tuple[str, dict[str, Any]]


def matches(pattern: Fact, fact: Fact) -> bool:
    return all(is_var(p) or p == f for p, f in zip(pattern, fact))


@dataclass
class Target:
    description: str
    test: Callable[[PlanState, str | None], bool]
    objects: set[str] = field(default_factory=set)
    categories: tuple[str, ...] = ("action",)

    @classmethod
    def fact(cls, pattern: Fact) -> "Target":
        pattern = tuple(pattern)
        return cls(f"{' '.join(pattern)}",
                   lambda st, last: any(matches(pattern, f) for f in st.fluents),
                   {t for t in pattern if not is_var(t)})

    @classmethod
    def position(cls, agent: str, predicate: str, places: set[str]) -> "Target":
        return cls(f"{agent} {predicate} one of {sorted(places)[:4]}",
                   lambda st, last: any(st.has(agent, predicate, p) for p in places))

    @classmethod
    def tool_use(cls, tools: set[str], objects: set[str] | None = None) -> "Target":
        return cls(f"use {'/'.join(sorted(tools))}", lambda st, last: last in tools, set(objects or ()),
                   categories=("action", "maintenance"))


@dataclass
class PlanResult:
    found: bool
    steps: list[Step] = field(default_factory=list)
    cost: float = 0.0          # search cost: includes risk penalties, not just energy
    violations: list[tuple[Fact, bool]] = field(default_factory=list)
    support: list[Fact] = field(default_factory=list)
    success: float = 0.0
    expansions: int = 0
    reason: str = ""

    @property
    def executable(self) -> bool:
        return self.found and not self.violations

    def to_dict(self) -> dict[str, Any]:
        return {"found": self.found, "steps": [[t, a] for t, a in self.steps], "cost": round(self.cost, 2),
                "violations": [[list(f), pos] for f, pos in self.violations],
                "success": round(self.success, 3), "expansions": self.expansions, "reason": self.reason}


class Planner:
    def __init__(self, penalty: float = 25.0) -> None:
        self.penalty = penalty
        self.calls = 0
        self.total_expansions = 0
        self.failures = 0

    def plan(self, ctx: "CognitiveContext", target: Target, threshold: float | None = None,
             max_expansions: int | None = None, relax: bool = True) -> PlanResult:
        self.calls += 1
        threshold = threshold if threshold is not None else float(ctx.strategies.value("planning.support_threshold"))
        max_expansions = max_expansions or ctx.config.limits.planner_expansions
        tools = ctx.tools.plannable(target.categories)
        relevant = set(target.objects)
        domain = PlanDomain(ctx.world, threshold)
        for tool in sorted(tools, key=lambda t: t.name):
            if tool.instrumental:
                relevant |= tool.instrumental(domain)
        domain.relevant = relevant
        start = domain.initial
        if target.test(start, None):
            return PlanResult(True, [], 0.0, [], [], 1.0, 0, "already satisfied")

        counter = itertools.count()
        frontier: list = [(0.0, next(counter), start, None, (), frozenset())]
        best: dict[tuple[PlanState, frozenset], float] = {(start, frozenset()): 0.0}
        expansions = 0
        while frontier and expansions < max_expansions:
            cost, _, state, last, path, violations = heapq.heappop(frontier)
            if best.get((state, violations), float("inf")) < cost:
                continue
            if target.test(state, last):
                self.total_expansions += expansions
                return self._result(domain, start, list(path), cost, violations, expansions, tools)
            expansions += 1
            for tool in sorted(tools, key=lambda t: t.name):
                for args in tool.ground(state, domain):
                    unmet: list["Precondition"] = tool.check(state, args, domain) if tool.check else []
                    if any(not u.relaxable for u in unmet):
                        continue
                    if unmet and not relax:
                        continue
                    new_violations = violations | frozenset((u.fact, u.positive) for u in unmet)
                    step_cost = tool.step_cost(state, args, domain) if tool.step_cost else 1.0
                    new_cost = cost + step_cost + self.penalty * (len(new_violations) - len(violations))
                    new_state = tool.apply(state, args, domain)
                    key = (new_state, new_violations)
                    if best.get(key, float("inf")) <= new_cost:
                        continue
                    best[key] = new_cost
                    heapq.heappush(frontier, (new_cost, next(counter), new_state, tool.name,
                                              path + ((tool.name, args),), new_violations))
        self.total_expansions += expansions
        self.failures += 1
        return PlanResult(False, expansions=expansions,
                          reason="search budget exhausted" if frontier else "unreachable under current beliefs")

    def _result(self, domain: PlanDomain, start: PlanState, steps: list[Step], cost: float,
                violations: frozenset, expansions: int, tools) -> PlanResult:
        by_name = {t.name: t for t in tools}
        state = start
        support: dict[Fact, None] = {}
        for name, args in steps:
            tool = by_name[name]
            if tool.support:
                for f in tool.support(state, args, domain):
                    support[f] = None
            state = tool.apply(state, args, domain)
        # weakest-link estimate: a plan is as sound as its least-supported assumption,
        # with a mild discount for length (more assumptions, more chances to be wrong)
        confidences = [max(0.05, domain.conf(*f)) for f in support]
        success = min(confidences) * (0.99 ** len(confidences)) if confidences else 1.0
        return PlanResult(True, steps, cost, sorted(violations), list(support), success, expansions,
                          "blocked" if violations else "ok")
