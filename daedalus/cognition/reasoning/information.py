"""Expected information gain estimates, grounded in coverage and belief entropy."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .navigation import neighbors

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


def information_deficit(ctx: "CognitiveContext", entity: str, staleness_horizon: float = 250.0) -> float:
    world = ctx.world
    predicates = world.schema.epistemic or {"*"}
    tick = ctx.clock.tick
    total = 0.0
    for p in sorted(predicates):
        cov = world.coverage.get((entity, p))
        if cov is None:
            total += 1.0
        else:
            # revisiting a known place is worth something, but never as much as
            # examining one that has never been examined at all
            total += 0.35 * (1.0 - math.exp(-(tick - cov[1]) / staleness_horizon))
    deficit = total / len(predicates)
    entropy = world.entity_uncertainty(entity)
    return min(1.0, deficit + 0.15 * min(entropy, 2.0))


def exploration_value(ctx: "CognitiveContext", place: str, reach: int = 1) -> float:
    own = information_deficit(ctx, place)
    if reach <= 0:
        return own
    around = [information_deficit(ctx, n) for n in neighbors(ctx, place, passable_only=False)]
    return min(1.0, 0.6 * own + 0.4 * (sum(around) / max(1, len(around))) * min(1.0, len(around) / 2))
