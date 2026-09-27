"""
Provenance & Architectural Attribution:
======================================
Windows-Use Source:   windows_use/telemetry/
ORBIT Destination:    src/orbit/runtime/telemetry/broadcaster.py
Integration Paradigm: Non-Blocking Pub/Sub Telemetry Broadcaster (Brain-Body Separation)

Adaptations Applied:
- Implemented non-blocking, asynchronous telemetry broadcast engine.
- Enforced complete crash-isolation: failing or slow sinks cannot block or crash the agent execution loop.
- Enforced observer-only invariant: broadcaster does not execute actions, plan, or declare completion.
======================================
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections import deque
import logging
import time
from typing import Any, Callable, Coroutine, Deque, Dict, List, Optional, Set, Union

from orbit.runtime.telemetry.events import StructuredTelemetryEvent, TelemetryEventType

logger = logging.getLogger(__name__)


class TelemetrySink(ABC):
    """Abstract interface for consuming structured telemetry events."""

    @abstractmethod
    async def consume(self, event: StructuredTelemetryEvent) -> None:
        """Process an immutable telemetry event."""
        pass


class InMemoryBufferSink(TelemetrySink):
    """Thread-safe in-memory event buffer for testing, auditing, and inspection."""

    def __init__(self, maxlen: int = 1000) -> None:
        self._events: Deque[StructuredTelemetryEvent] = deque(maxlen=maxlen)

    async def consume(self, event: StructuredTelemetryEvent) -> None:
        self._events.append(event)

    def get_events(self) -> List[StructuredTelemetryEvent]:
        return list(self._events)

    def get_events_by_type(self, event_type: TelemetryEventType) -> List[StructuredTelemetryEvent]:
        return [e for e in self._events if e.event_type == event_type]

    def clear(self) -> None:
        self._events.clear()

    @property
    def count(self) -> int:
        return len(self._events)


class CallbackSink(TelemetrySink):
    """Sink dispatching to a custom synchronous or asynchronous callable."""

    def __init__(self, callback: Union[Callable[[StructuredTelemetryEvent], None], Callable[[StructuredTelemetryEvent], Coroutine[Any, Any, None]]]) -> None:
        self._callback = callback

    async def consume(self, event: StructuredTelemetryEvent) -> None:
        try:
            res = self._callback(event)
            if asyncio.iscoroutine(res):
                await res
        except Exception as exc:
            logger.warning("[CallbackSink] Exception in callback: %s", exc)


class LoggingSink(TelemetrySink):
    """Sink writing structured event summaries to logger."""

    def __init__(self, level: int = logging.INFO) -> None:
        self._level = level

    async def consume(self, event: StructuredTelemetryEvent) -> None:
        logger.log(
            self._level,
            "[TELEMETRY] [%s] Task:%s Cycle:%d | Source:%s | %s",
            event.event_type.value,
            event.task_id,
            event.cycle_number,
            event.source_component,
            event.payload,
        )


class SlowCrashingSink(TelemetrySink):
    """Test utility sink simulating slow or crashing consumers to verify non-blocking isolation."""

    def __init__(self, delay_sec: float = 2.0, crash_after: int = 1) -> None:
        self._delay_sec = delay_sec
        self._crash_after = crash_after
        self._consumed_count = 0

    async def consume(self, event: StructuredTelemetryEvent) -> None:
        self._consumed_count += 1
        if self._delay_sec > 0:
            await asyncio.sleep(self._delay_sec)
        if self._consumed_count >= self._crash_after:
            raise RuntimeError(f"Simulated sink crash on event {event.event_id}")


class LiveTelemetryBroadcaster:
    """Non-blocking, asynchronous telemetry distribution engine for ORBIT.

    SAFETY INVARIANTS:
    1. Non-Blocking Execution: emit() returns immediately; slow sinks run asynchronously.
    2. Crash-Isolated: Sink crashes NEVER affect the main agent loop.
    3. Observer-Only: Never triggers physical actions, selects plans, or modifies execution state.
    4. Sole Completion Authority: Never declares task completion or task failure.
    """

    def __init__(self, max_queue_size: int = 2000) -> None:
        self._sinks: List[TelemetrySink] = []
        self._queue: asyncio.Queue[StructuredTelemetryEvent] = asyncio.Queue(maxsize=max_queue_size)
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._running: bool = False
        self._emitted_count: int = 0
        self._dropped_count: int = 0

    def add_sink(self, sink: TelemetrySink) -> None:
        """Register a new telemetry sink."""
        if sink not in self._sinks:
            self._sinks.append(sink)

    def remove_sink(self, sink: TelemetrySink) -> None:
        """Unregister a telemetry sink."""
        if sink in self._sinks:
            self._sinks.remove(sink)

    @property
    def sinks(self) -> List[TelemetrySink]:
        return list(self._sinks)

    @property
    def emitted_count(self) -> int:
        return self._emitted_count

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    def start(self) -> None:
        """Start the background consumer worker if not already running."""
        if self._running and self._worker_task and not self._worker_task.done():
            return
        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._worker_task = loop.create_task(self._process_queue(), name="orbit_telemetry_worker")
        except RuntimeError:
            pass  # Will start when loop is available

    async def stop(self, timeout_sec: float = 2.0) -> None:
        """Gracefully stop broadcaster and flush queue."""
        self._running = False
        if self._worker_task and not self._worker_task.done():
            try:
                await asyncio.wait_for(self._worker_task, timeout=timeout_sec)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._worker_task.cancel()

    def emit(self, event: StructuredTelemetryEvent) -> None:
        """Synchronously enqueue event without blocking caller execution.

        Enforces non-blocking execution guarantee: returns immediately.
        """
        self._emitted_count += 1
        if not self._running:
            self.start()

        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._dropped_count += 1
            logger.warning("[LiveTelemetryBroadcaster] Queue full; dropping telemetry event %s", event.event_id)

    async def emit_async(self, event: StructuredTelemetryEvent) -> None:
        """Emit event and immediately return (compatible with async callers)."""
        self.emit(event)

    async def flush(self, timeout_sec: float = 3.0) -> None:
        """Wait until all currently queued events have been dispatched to sinks."""
        t_start = time.perf_counter()
        while not self._queue.empty():
            if time.perf_counter() - t_start > timeout_sec:
                break
            await asyncio.sleep(0.01)

    async def _process_queue(self) -> None:
        """Background worker consuming events and dispatching to registered sinks with crash isolation."""
        while self._running or not self._queue.empty():
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            # Dispatch event to all sinks concurrently with crash isolation
            for sink in list(self._sinks):
                try:
                    res = sink.consume(event)
                    if asyncio.iscoroutine(res):
                        asyncio.create_task(self._safe_sink_consume(sink, res))
                except Exception as exc:
                    logger.error("[LiveTelemetryBroadcaster] Sink %s raised during dispatch: %s", type(sink).__name__, exc)

            self._queue.task_done()

    async def _safe_sink_consume(self, sink: TelemetrySink, coro: Any) -> None:
        """Safely execute sink consume coroutine ensuring full crash isolation."""
        try:
            await coro
        except Exception as exc:
            logger.warning("[LiveTelemetryBroadcaster] Async sink %s failed: %s", type(sink).__name__, exc)


__all__ = [
    "TelemetrySink",
    "InMemoryBufferSink",
    "CallbackSink",
    "LoggingSink",
    "SlowCrashingSink",
    "LiveTelemetryBroadcaster",
]
