from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.cognition.process import CognitiveProcess
from ..model import Intention, IntentionFeatures, IntentionKind

if TYPE_CHECKING:
    from ...core.cognition.context import CognitiveContext


class IntentionGenerator(CognitiveProcess):
    """A cognitive process whose only output is pressure, expressed as intentions."""

    name = "generator"

    def propose(self, ctx: "CognitiveContext", key: str, kind: IntentionKind, description: str,
                target: dict[str, Any], features: IntentionFeatures, goal_id: str | None = None,
                max_steps: int = 60) -> Intention:
        intention = Intention(key=key, kind=kind, description=description, target=target,
                              features=features.clamp(), goal_id=goal_id, max_steps=max_steps)
        return ctx.pool.propose(ctx, intention, self.name)
