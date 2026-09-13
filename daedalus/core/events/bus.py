"""A deterministic, in-process event bus.

Handlers are invoked synchronously in subscription order so experiments are
reproducible. Asynchronous consumers (the API's WebSocket stream) attach bounded
queues and never block the cognitive runtime.
"""
from __future__ import annotations

import asyncio
from collections import Counter, deque
from typing import Any, Callable, Iterable

from .types import Event

Handler = Callable[[Event], None]


def _matches(pattern: str, event_type: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return event_type.startswith(pattern[:-1])
    return pattern == event_type


class EventBus:
    def __init__(self, tick_provider: Callable[[], int], history_size: int = 6000) -> None:
        self._tick = tick_provider
        self._subscribers: list[tuple[str, Handler]] = []
        self._queues: set[asyncio.Queue[Event]] = set()
        self.history: deque[Event] = deque(maxlen=history_size)
        self.counts: Counter[str] = Counter()
        self._seq = 0
        self.enabled = True

    def subscribe(self, pattern: str, handler: Handler) -> Callable[[], None]:
        entry = (pattern, handler)
        self._subscribers.append(entry)

        def unsubscribe() -> None:
            if entry in self._subscribers:
                self._subscribers.remove(entry)

        return unsubscribe

    def attach_queue(self, maxsize: int = 2000) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self._queues.add(queue)
        return queue

    def detach_queue(self, queue: asyncio.Queue[Event]) -> None:
        self._queues.discard(queue)

    def publish(
        self,
        type: str,
        source: str,
        payload: dict[str, Any] | None = None,
        causes: Iterable[str] | None = None,
    ) -> Event:
        self._seq += 1
        event = Event(
            id=f"ev{self._seq}",
            type=type,
            source=source,
            tick=self._tick(),
            payload=payload or {},
            causes=list(causes or []),
        )
        self.counts[type] += 1
        if not self.enabled:
            return event
        self.history.append(event)
        for pattern, handler in list(self._subscribers):
            if _matches(pattern, type):
                handler(event)
        for queue in list(self._queues):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:  # slow consumer: drop, never block cognition
                pass
        return event

    def recent(self, n: int = 200, category: str | None = None) -> list[Event]:
        items = list(self.history)
        if category:
            items = [e for e in items if e.category == category]
        return items[-n:]
