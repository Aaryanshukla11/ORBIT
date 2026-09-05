"""Unit tests for asynchronous event bus."""

import asyncio
import pytest

from orbit.contracts.events import EventType, RuntimeEvent
from orbit.infrastructure.event_bus import EventBus


@pytest.mark.asyncio
async def test_event_bus_monotonic_sequence():
    bus = EventBus()
    seqs = [bus.next_sequence() for _ in range(10)]
    assert seqs == list(range(1, 11))


@pytest.mark.asyncio
async def test_event_bus_subscribe_and_publish():
    bus = EventBus()
    received = []

    async def on_status(event: RuntimeEvent):
        received.append(event)

    bus.subscribe(EventType.RUNTIME_STATUS, on_status)

    evt1 = RuntimeEvent(
        event_id="e1",
        event_type=EventType.RUNTIME_STATUS,
        event_seq=0,
        session_id="s1",
        payload={"state": "IDLE"},
    )
    evt2 = RuntimeEvent(
        event_id="e2",
        event_type=EventType.TASK_STATE_CHANGED,
        event_seq=0,
        session_id="s1",
        payload={"status": "RUNNING"},
    )

    await bus.publish(evt1)
    await bus.publish(evt2)

    assert len(received) == 1
    assert received[0].event_id == "e1"
    assert received[0].event_seq == 1


@pytest.mark.asyncio
async def test_event_bus_wildcard_subscription():
    bus = EventBus()
    all_events = []

    def on_any(event: RuntimeEvent):
        all_events.append(event)

    bus.subscribe(None, on_any)

    await bus.publish(RuntimeEvent(
        event_id="e1",
        event_type=EventType.RUNTIME_STATUS,
        event_seq=0,
        session_id="s1",
        payload={},
    ))
    await bus.publish(RuntimeEvent(
        event_id="e2",
        event_type=EventType.ERROR,
        event_seq=0,
        session_id="s1",
        payload={},
    ))

    assert len(all_events) == 2


@pytest.mark.asyncio
async def test_event_bus_error_isolation():
    bus = EventBus()
    executed_good = []

    async def failing_handler(event: RuntimeEvent):
        raise ValueError("Simulated handler crash")

    async def good_handler(event: RuntimeEvent):
        executed_good.append(event)

    bus.subscribe(EventType.RUNTIME_STATUS, failing_handler)
    bus.subscribe(EventType.RUNTIME_STATUS, good_handler)

    await bus.publish(RuntimeEvent(
        event_id="e1",
        event_type=EventType.RUNTIME_STATUS,
        event_seq=0,
        session_id="s1",
        payload={},
    ))

    # The good handler should have executed despite the failing handler raising
    assert len(executed_good) == 1


@pytest.mark.asyncio
async def test_event_bus_unsubscribe():
    bus = EventBus()
    received = []

    def handler(event: RuntimeEvent):
        received.append(event)

    unsub = bus.subscribe(EventType.RUNTIME_STATUS, handler)

    await bus.publish(RuntimeEvent(
        event_id="e1",
        event_type=EventType.RUNTIME_STATUS,
        event_seq=0,
        session_id="s1",
        payload={},
    ))
    assert len(received) == 1

    unsub()

    await bus.publish(RuntimeEvent(
        event_id="e2",
        event_type=EventType.RUNTIME_STATUS,
        event_seq=0,
        session_id="s1",
        payload={},
    ))
    assert len(received) == 1
