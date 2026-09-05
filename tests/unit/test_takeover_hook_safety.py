"""Unit tests for Takeover Win32 hook safety, ABI gate, and telemetry calculations."""

import ctypes
import pytest
from orbit.adapters.takeover.classifier import (
    InputDevice,
    InputEventType,
    InputSource,
    TakeoverEvidence,
)
from orbit.adapters.takeover.safety import (
    KBDLLHOOKSTRUCT,
    MSLLHOOKSTRUCT,
    POINT,
    TakeoverAbiGate,
)
from orbit.adapters.takeover.telemetry import TakeoverTelemetryLogger


def test_takeover_abi_gate_structure_sizes():
    res = TakeoverAbiGate.validate_abi()
    assert res.is_valid is True
    assert res.pointer_size == 8
    assert res.msllhook_size == 32
    assert res.kbdllhook_size == 24


def test_takeover_telemetry_aggregation():
    logger = TakeoverTelemetryLogger()

    ev1 = TakeoverEvidence(
        event_id=1,
        timestamp_ns=1000,
        device=InputDevice.MOUSE,
        event_type=InputEventType.MOUSE_MOVE,
        source=InputSource.USER_PHYSICAL,
        should_trigger_takeover=True,
        reason="Move 1",
        classification_latency_us=5.0,
    )
    ev2 = TakeoverEvidence(
        event_id=2,
        timestamp_ns=2000,
        device=InputDevice.MOUSE,
        event_type=InputEventType.MOUSE_MOVE,
        source=InputSource.USER_PHYSICAL,
        should_trigger_takeover=True,
        reason="Move 2",
        classification_latency_us=15.0,
    )

    logger.log_evidence(ev1, is_primary_trigger=True, hook_to_signal_us=100.0)
    logger.log_evidence(ev2, is_primary_trigger=False, hook_to_signal_us=200.0)

    snap = logger.get_snapshot()
    assert snap.total_events_processed == 2
    assert snap.takeover_events_triggered == 1
    assert snap.deduplicated_events == 1
    assert snap.last_takeover_reason == "Move 1"
    assert snap.classification_latency_us.count == 2
    assert snap.classification_latency_us.min == 5.0
    assert snap.classification_latency_us.max == 15.0
    assert snap.classification_latency_us.mean == 10.0

    logger.reset()
    assert logger.get_snapshot().total_events_processed == 0
