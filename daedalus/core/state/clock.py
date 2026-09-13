from __future__ import annotations


class Clock:
    """Logical time. One tick = one sense/propose/attend/act cycle of the substrate."""

    def __init__(self, tick: int = 0) -> None:
        self.tick = tick

    def advance(self) -> int:
        self.tick += 1
        return self.tick

    def __call__(self) -> int:
        return self.tick
