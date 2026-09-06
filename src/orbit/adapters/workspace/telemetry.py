"""Telemetry tracking, operation metrics, and transition logging for Workspace capability."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.adapters.workspace.types import DockEdge, WorkspaceState


class WorkspaceTransitionRecord(BaseModel):
    """Immutable record of an individual workspace state transition."""

    from_state: WorkspaceState
    to_state: WorkspaceState
    timestamp_ns: int = Field(default_factory=time.perf_counter_ns)
    duration_ms: float = Field(default=0.0, ge=0.0)
    reason: Optional[str] = None
    desktop_generation_id: int = Field(default=1)


class WorkspaceOperationMetrics(BaseModel):
    """Aggregate performance and reliability metrics for workspace operations."""

    total_transitions: int = 0
    successful_dock_count: int = 0
    successful_release_count: int = 0
    reconfiguration_count: int = 0
    last_registration_latency_ms: float = 0.0
    last_unregistration_latency_ms: float = 0.0
    error_count: int = 0
    last_error: Optional[str] = None


class WorkspaceTelemetrySnapshot(BaseModel):
    """Point-in-time snapshot of workspace telemetry and operational health."""

    current_state: WorkspaceState = WorkspaceState.UNINITIALIZED
    desktop_generation_id: int = 1
    topology_generation_id: int = 1
    dock_edge: DockEdge = DockEdge.NONE
    is_docked: bool = False
    metrics: WorkspaceOperationMetrics = Field(default_factory=WorkspaceOperationMetrics)
    recent_transitions: List[WorkspaceTransitionRecord] = Field(default_factory=list)


class WorkspaceTelemetryRecorder:
    """Thread-safe performance recorder for workspace lifecycle and shell operations."""

    def __init__(self, max_history_size: int = 100) -> None:
        self._lock = threading.Lock()
        self._max_history = max_history_size
        self._metrics = WorkspaceOperationMetrics()
        self._transitions: List[WorkspaceTransitionRecord] = []
        self._current_state = WorkspaceState.UNINITIALIZED
        self._desktop_generation_id = 1
        self._topology_generation_id = 1
        self._dock_edge = DockEdge.NONE
        self._is_docked = False

    def record_transition(
        self,
        from_state: WorkspaceState,
        to_state: WorkspaceState,
        duration_ms: float = 0.0,
        reason: Optional[str] = None,
        desktop_generation_id: int = 1,
        topology_generation_id: int = 1,
        dock_edge: DockEdge = DockEdge.NONE,
    ) -> None:
        """Record an executed state transition."""
        record = WorkspaceTransitionRecord(
            from_state=from_state,
            to_state=to_state,
            timestamp_ns=time.perf_counter_ns(),
            duration_ms=duration_ms,
            reason=reason,
            desktop_generation_id=desktop_generation_id,
        )

        with self._lock:
            self._current_state = to_state
            self._desktop_generation_id = desktop_generation_id
            self._topology_generation_id = topology_generation_id
            self._dock_edge = dock_edge
            self._is_docked = (to_state == WorkspaceState.DOCKED)

            self._metrics.total_transitions += 1
            if to_state == WorkspaceState.DOCKED:
                self._metrics.successful_dock_count += 1
                if duration_ms > 0:
                    self._metrics.last_registration_latency_ms = round(duration_ms, 3)
            elif to_state == WorkspaceState.READY_FLOATING and from_state in {WorkspaceState.RELEASING, WorkspaceState.DOCKED}:
                self._metrics.successful_release_count += 1
                if duration_ms > 0:
                    self._metrics.last_unregistration_latency_ms = round(duration_ms, 3)

            self._transitions.append(record)
            if len(self._transitions) > self._max_history:
                self._transitions.pop(0)

    def record_reconfiguration(self, edge: DockEdge, latency_ms: float = 0.0) -> None:
        """Record an in-place edge or size reconfiguration."""
        with self._lock:
            self._dock_edge = edge
            self._metrics.reconfiguration_count += 1
            if latency_ms > 0:
                self._metrics.last_registration_latency_ms = round(latency_ms, 3)

    def record_error(self, error_message: str) -> None:
        """Record a native or runtime workspace error."""
        with self._lock:
            self._metrics.error_count += 1
            self._metrics.last_error = error_message

    def get_snapshot(self) -> WorkspaceTelemetrySnapshot:
        """Retrieve an immutable snapshot of workspace telemetry."""
        with self._lock:
            return WorkspaceTelemetrySnapshot(
                current_state=self._current_state,
                desktop_generation_id=self._desktop_generation_id,
                topology_generation_id=self._topology_generation_id,
                dock_edge=self._dock_edge,
                is_docked=self._is_docked,
                metrics=self._metrics.model_copy(),
                recent_transitions=list(self._transitions[-20:]),
            )

    def reset(self) -> None:
        """Reset all metrics and transition history."""
        with self._lock:
            self._metrics = WorkspaceOperationMetrics()
            self._transitions.clear()
            self._current_state = WorkspaceState.UNINITIALIZED
            self._desktop_generation_id = 1
            self._topology_generation_id = 1
            self._dock_edge = DockEdge.NONE
            self._is_docked = False
