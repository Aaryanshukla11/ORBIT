"""Unit tests for Workspace Telemetry Recorder and metrics aggregation."""

import threading
from orbit.adapters.workspace.telemetry import (
    WorkspaceOperationMetrics,
    WorkspaceTelemetryRecorder,
    WorkspaceTelemetrySnapshot,
    WorkspaceTransitionRecord,
)
from orbit.adapters.workspace.types import DockEdge, WorkspaceState


def test_transition_recording():
    rec = WorkspaceTelemetryRecorder(max_history_size=5)
    rec.record_transition(
        from_state=WorkspaceState.UNINITIALIZED,
        to_state=WorkspaceState.READY_FLOATING,
        duration_ms=1.5,
        reason="Initialized",
        desktop_generation_id=1,
    )

    snap = rec.get_snapshot()
    assert snap.current_state == WorkspaceState.READY_FLOATING
    assert snap.desktop_generation_id == 1
    assert snap.metrics.total_transitions == 1
    assert len(snap.recent_transitions) == 1
    assert snap.recent_transitions[0].from_state == WorkspaceState.UNINITIALIZED
    assert snap.recent_transitions[0].to_state == WorkspaceState.READY_FLOATING
    assert snap.recent_transitions[0].duration_ms == 1.5


def test_dock_and_release_metrics():
    rec = WorkspaceTelemetryRecorder()
    rec.record_transition(
        from_state=WorkspaceState.REGISTERING,
        to_state=WorkspaceState.DOCKED,
        duration_ms=0.15,
        reason="Docked Right",
        desktop_generation_id=2,
        dock_edge=DockEdge.RIGHT,
    )

    snap = rec.get_snapshot()
    assert snap.is_docked is True
    assert snap.dock_edge == DockEdge.RIGHT
    assert snap.metrics.successful_dock_count == 1
    assert snap.metrics.last_registration_latency_ms == 0.15

    rec.record_transition(
        from_state=WorkspaceState.RELEASING,
        to_state=WorkspaceState.READY_FLOATING,
        duration_ms=0.08,
        reason="Undocked",
        desktop_generation_id=3,
        dock_edge=DockEdge.NONE,
    )

    snap2 = rec.get_snapshot()
    assert snap2.is_docked is False
    assert snap2.dock_edge == DockEdge.NONE
    assert snap2.metrics.successful_release_count == 1
    assert snap2.metrics.last_unregistration_latency_ms == 0.08


def test_reconfiguration_recording():
    rec = WorkspaceTelemetryRecorder()
    rec.record_reconfiguration(edge=DockEdge.LEFT, latency_ms=0.22)

    snap = rec.get_snapshot()
    assert snap.dock_edge == DockEdge.LEFT
    assert snap.metrics.reconfiguration_count == 1
    assert snap.metrics.last_registration_latency_ms == 0.22


def test_error_recording():
    rec = WorkspaceTelemetryRecorder()
    rec.record_error("Native shell error code 5")

    snap = rec.get_snapshot()
    assert snap.metrics.error_count == 1
    assert snap.metrics.last_error == "Native shell error code 5"


def test_reset():
    rec = WorkspaceTelemetryRecorder()
    rec.record_transition(
        from_state=WorkspaceState.READY_FLOATING,
        to_state=WorkspaceState.DOCKED,
        duration_ms=1.0,
        desktop_generation_id=2,
    )
    rec.record_error("Test error")
    rec.reset()

    snap = rec.get_snapshot()
    assert snap.current_state == WorkspaceState.UNINITIALIZED
    assert snap.desktop_generation_id == 1
    assert snap.metrics.total_transitions == 0
    assert snap.metrics.error_count == 0
    assert snap.metrics.last_error is None
    assert len(snap.recent_transitions) == 0


def test_concurrent_telemetry_recording():
    rec = WorkspaceTelemetryRecorder()

    def worker():
        for i in range(50):
            rec.record_transition(
                from_state=WorkspaceState.REGISTERING,
                to_state=WorkspaceState.DOCKED,
                duration_ms=0.1,
                desktop_generation_id=i,
            )
            _ = rec.get_snapshot()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    snap = rec.get_snapshot()
    assert snap.metrics.total_transitions == 400
