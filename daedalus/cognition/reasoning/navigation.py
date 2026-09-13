from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


def position(ctx: "CognitiveContext") -> str | None:
    schema = ctx.world.schema
    beliefs = ctx.world.query(schema.agent_id, schema.position_predicate, None, min_conf=0.5)
    return max(beliefs, key=lambda b: b.confidence).object if beliefs else None


def neighbors(ctx: "CognitiveContext", place: str, passable_only: bool = True) -> list[str]:
    schema = ctx.world.schema
    out = ctx.world.objects(place, schema.edge_predicate, 0.5)
    if passable_only:
        out = [n for n in out if not ctx.env.traversal_blocked(ctx.world, place, n)]
    return out


def distances_from(ctx: "CognitiveContext", origin: str | None, passable_only: bool = True) -> dict[str, int]:
    if origin is None:
        return {}
    dist = {origin: 0}
    queue = deque([origin])
    while queue:
        node = queue.popleft()
        for nxt in neighbors(ctx, node, passable_only):
            if nxt not in dist:
                dist[nxt] = dist[node] + 1
                queue.append(nxt)
    return dist


def blocked_frontier(ctx: "CognitiveContext") -> list[tuple[str, int]]:
    """Places that are unreachable now but would be reachable if barriers were passable.

    A blocked frontier is how a physical obstacle becomes visible to cognition as
    a dependency rather than as an absence.
    """
    optimistic = distances_from(ctx, position(ctx), passable_only=False)
    return sorted(((place, d) for place, d in optimistic.items() if place not in ctx.distances),
                  key=lambda x: x[1])
