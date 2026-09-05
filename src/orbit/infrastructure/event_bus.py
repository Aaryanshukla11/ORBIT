"""Asynchronous in-process type-safe event bus for ORBIT."""

from __future__ import annotations

import asyncio
from collections import defaultdict
import inspect
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Union

from orbit.contracts.events import EventType, RuntimeEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[RuntimeEvent], Union[None, Awaitable[None]]]


class EventBus:
    """In-process asynchronous event bus with subscriber isolation and sequencing."""

    def __init__(self) -> None:
        self._handlers: Dict[Optional[EventType], List[EventHandler]] = defaultdict(list)
        self._seq_counter: int = 0
        self._lock = asyncio.Lock()
        self._closed: bool = False

    def next_sequence(self) -> int:
        """Atomically generate the next monotonically increasing 64-bit sequence number."""
        self._seq_counter += 1
        return self._seq_counter

    def subscribe(
        self,
        event_type: Optional[EventType],
        handler: EventHandler,
    ) -> Callable[[], None]:
        """Subscribe a handler to a specific EventType, or None for all events.

        Returns an unsubscribe callback.
        """
        self._handlers[event_type].append(handler)

        def unsubscribe() -> None:
            if handler in self._handlers[event_type]:
                self._handlers[event_type].remove(handler)

        return unsubscribe

    async def publish(self, event: RuntimeEvent) -> None:
        """Publish an event to all matching subscribers with error isolation."""
        if self._closed:
            logger.warning("Attempted to publish event on closed EventBus: %s", event.event_type)
            return

        # Ensure event has sequence number if not set
        if event.event_seq <= 0:
            event.event_seq = self.next_sequence()

        # Collect target handlers (specific + wildcard)
        targets: List[EventHandler] = list(self._handlers.get(event.event_type, [])) + list(
            self._handlers.get(None, [])
        )

        for handler in targets:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.exception(
                    "Error executing event handler %s for event %s: %s",
                    handler,
                    event.event_type,
                    e,
                )

    async def close(self) -> None:
        """Close the event bus and clear handlers."""
        self._closed = True
        self._handlers.clear()
