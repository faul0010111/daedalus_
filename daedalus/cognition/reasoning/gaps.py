"""Knowledge-gap analysis by regression over declared capabilities.

"To make X true I could use tool T, which requires knowing Y. I don't know Y."
The unknown Y is a knowledge gap — the seed of a KNOW goal.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ...world.model import is_var

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext

Fact = tuple[str, str, str]


def unify(tool_pattern: Fact, target: Fact) -> dict[str, str] | None:
    binding: dict[str, str] = {}
    for a, b in zip(tool_pattern, target):
        if is_var(a):
            if not is_var(b):
                if binding.get(a, b) != b:
                    return None
                binding[a] = b
        elif not is_var(b) and a != b:
            return None
    return binding


def knowledge_gaps(ctx: "CognitiveContext", pattern: Fact, know_threshold: float = 0.5,
                   depth: int = 0, max_depth: int = 3) -> list[Fact]:
    world = ctx.world
    if world.match(pattern, 0.7):
        return []
    if depth > max_depth:
        return []
    producers = [t for t in ctx.tools.all() if t.produces and unify(t.produces, pattern) is not None]
    if not producers:
        return []
    gaps: list[Fact] = []
    for tool in producers:
        binding = unify(tool.produces, pattern) or {}
        tool_gaps = [req for req in (tool.knowledge(binding) if tool.knowledge else [])
                     if not any(is_var(t) for t in (req[1],)) and not world.match(req, know_threshold)]
        if not tool_gaps:
            for req in (tool.requires(binding) if tool.requires else []):
                if any(is_var(t) for t in req):
                    continue
                if world.holds(*req, threshold=0.7):
                    continue
                tool_gaps.extend(knowledge_gaps(ctx, req, know_threshold, depth + 1, max_depth))
        if not tool_gaps:
            return []  # at least one producer is knowledge-viable
        gaps.extend(tool_gaps)
    unique: dict[Fact, None] = {}
    for g in gaps:
        unique[g] = None
    return list(unique)
