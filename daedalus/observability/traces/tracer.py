"""Decision traces: why this intention, at this moment, over the alternatives."""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...intentions.attention import AttentionDecision


class Tracer:
    def __init__(self, capacity: int = 400) -> None:
        self.decisions: deque[dict[str, Any]] = deque(maxlen=capacity)
        self.jsonl_path: Path | None = None

    def record_decision(self, decision: "AttentionDecision") -> None:
        record = decision.to_dict(top=6)
        self.decisions.append(record)
        if self.jsonl_path:
            with self.jsonl_path.open("a") as fh:
                fh.write(json.dumps(record) + "\n")

    def latest(self) -> dict[str, Any] | None:
        return self.decisions[-1] if self.decisions else None
