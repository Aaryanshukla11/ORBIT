"""Unit tests for pointer cooperative cancellation semantics before and after dispatch."""

import time
import pytest

from orbit.adapters.pointer.health import ActionCounter
from orbit.adapters.pointer.movement import (
    MovementDiagnosticReason,
    MovementEvidenceLevel,
    MovementExecutor,
    MovementStatus,
)
from orbit.adapters.pointer.safety import (
    AbiGate,
    VirtualDesktopMetrics,
    VirtualDesktopTopologyIdentity,
)
from orbit.runtime.cancellation import CancellationSource


def test_cancellation_before_dispatch_prevents_sendinput():
    sendinput_calls = []

    def mock_sendinput(n, ptr, sz):
        sendinput_calls.append(n)
        return n

    counter = ActionCounter()
    executor = MovementExecutor(
        action_counter=counter,
        sendinput_override=mock_sendinput,
        cursorpos_override=lambda: (500, 500),
        topology_override=lambda: VirtualDesktopTopologyIdentity(0, 0, 1920, 1080, 1),
        metrics_override=lambda: VirtualDesktopMetrics(
            x_origin=0, y_origin=0, width=1920, height=1080, is_valid=True, timestamp_ns=time.perf_counter_ns()
        ),
    )

    cancel_source = CancellationSource()
    cancel_source.cancel(reason="Operator interrupted action")

    result = executor.execute_movement(
        target_x=500,
        target_y=500,
        cancellation_token=cancel_source.token,
    )

    assert result.status == MovementStatus.CANCELLED_BEFORE_DISPATCH
    assert result.diagnostic_reason == MovementDiagnosticReason.CANCELLED
    assert len(sendinput_calls) == 0  # Zero SendInput dispatches!
    assert counter.sendinput_calls == 0
    assert counter.cancellations_before_dispatch == 1


def test_cancellation_after_dispatch_preserves_truthful_evidence():
    """Verify that cancellation observed after SendInput reports CANCELLED_AFTER_DISPATCH with accepted_packets=1."""
    cancel_source = CancellationSource()

    def sendinput_with_delayed_cancel(n, ptr, sz):
        # Cancellation occurs during/after SendInput execution
        cancel_source.cancel(reason="Preempted during dispatch")
        return n

    counter = ActionCounter()
    executor = MovementExecutor(
        action_counter=counter,
        sendinput_override=sendinput_with_delayed_cancel,
        cursorpos_override=lambda: (500, 500),
        topology_override=lambda: VirtualDesktopTopologyIdentity(0, 0, 1920, 1080, 1),
        metrics_override=lambda: VirtualDesktopMetrics(
            x_origin=0, y_origin=0, width=1920, height=1080, is_valid=True, timestamp_ns=time.perf_counter_ns()
        ),
    )

    result = executor.execute_movement(
        target_x=500,
        target_y=500,
        cancellation_token=cancel_source.token,
    )

    assert result.status == MovementStatus.CANCELLED_AFTER_DISPATCH
    assert result.diagnostic_reason == MovementDiagnosticReason.CANCELLED
    assert result.evidence_level == MovementEvidenceLevel.DISPATCH_ACCEPTED
    assert result.accepted_packets == 1
    assert counter.sendinput_calls == 1
    assert counter.cancellations_after_dispatch == 1
