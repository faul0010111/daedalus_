"""Perception loop: observe → extract state → compare → detect change → update world model."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ...core.cognition.process import CognitiveProcess
from ...core.events import EventType
from .observation import Percept

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


@dataclass
class IngestReport:
    observations: int = 0
    new_beliefs: int = 0
    entropy_reduction: float = 0.0
    contradictions: list[str] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)
    surprises: float = 0.0


class PerceptionLoop(CognitiveProcess):
    name = "perception"
    period = 1

    def __init__(self) -> None:
        super().__init__()
        self._previous: set[tuple[str, str, str, bool]] = set()

    def step(self, ctx: "CognitiveContext") -> None:
        percept = ctx.env.sense()
        current = {(o.subject, o.predicate, o.object, o.positive) for o in percept.observations}
        appeared = current - self._previous
        vanished = self._previous - current
        if self._previous and (appeared or vanished):
            ctx.bus.publish(EventType.PERCEPT_CHANGE, self.name,
                            {"appeared": [list(x[:3]) + [x[3]] for x in sorted(appeared)][:12],
                             "vanished": [list(x[:3]) + [x[3]] for x in sorted(vanished)][:12]})
        self._previous = current
        report = ingest(ctx, percept)
        self.last_pressure = report.surprises


def ingest(ctx: "CognitiveContext", percept: Percept) -> IngestReport:
    report = IngestReport()
    world = ctx.world
    seen: dict[tuple[str, str], set[str]] = {}

    def absorb(s: str, p: str, o: str, positive: bool, reliability: float, source: str) -> None:
        res = world.observe(s, p, o, positive, reliability, source)
        report.observations += 1
        report.new_beliefs += int(res.created and positive)
        report.entropy_reduction += max(0.0, res.entropy_delta)
        if not res.created:
            report.surprises += abs(res.belief.confidence - res.prior)
        if res.contradiction:
            report.contradictions.append(res.contradiction.id)
        if res.resolved:
            report.resolved.append(res.resolved.id)
            ctx.metrics.inc("contradictions_resolved")

    for obs in percept.observations:
        if obs.positive:
            seen.setdefault((obs.subject, obs.predicate), set()).add(obs.object)
        absorb(obs.subject, obs.predicate, obs.object, obs.positive, obs.reliability, obs.source)
    # coverage turns silence into evidence of absence
    for entity, predicate, reliability, source in percept.coverage:
        observed = seen.get((entity, predicate), set())
        for belief in world.query(entity, predicate, None, min_conf=0.03):
            if belief.object not in observed:
                absorb(entity, predicate, belief.object, False, reliability, source)
        world.cover(entity, predicate)
    for name, value in percept.quantities.items():
        world.set_quantity(name, value)
    return report
