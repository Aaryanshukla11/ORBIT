"""Production Workspace Watchdog, Health Monitoring, Failure Classification & Bounded Recovery."""

from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
import logging
import sys
import time
from typing import Any, Callable, Dict, Optional

from orbit.adapters.workspace.abi import (
    IS_WINDOWS,
    RECT,
)
from orbit.adapters.workspace.appbar import NativeAppBarDriver
from orbit.adapters.workspace.geometry import (
    WorkspaceGeometryCoordinator,
)
from orbit.adapters.workspace.state import (
    WorkspaceStateManager,
)
from orbit.adapters.workspace.telemetry import (
    WorkspaceTelemetryRecorder,
)
from orbit.adapters.workspace.types import (
    DockEdge,
    WorkspaceGeometry,
    WorkspaceState,
)
from orbit.adapters.workspace.window import NativeWorkspaceWindow
from orbit.models.common import BoundingBox

logger = logging.getLogger(__name__)


# ============================================================================
# 1. Health Status & Failure Classifications
# ============================================================================

class WorkspaceHealthStatus(str, Enum):
    """Discrete health classification of the native workspace and AppBar."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    UNKNOWN = "UNKNOWN"


class WorkspaceFailureCategory(str, Enum):
    """Granular failure attribution for workspace anomalies."""

    NONE = "NONE"
    WINDOW_DESTROYED = "WINDOW_DESTROYED"
    INVALID_HWND = "INVALID_HWND"
    GEOMETRY_MISMATCH = "GEOMETRY_MISMATCH"
    TOPOLOGY_CHANGED = "TOPOLOGY_CHANGED"
    DPI_CONTEXT_CHANGED = "DPI_CONTEXT_CHANGED"
    APPBAR_OPERATION_FAILED = "APPBAR_OPERATION_FAILED"
    NATIVE_PROBE_FAILED = "NATIVE_PROBE_FAILED"
    RECOVERY_BUDGET_EXHAUSTED = "RECOVERY_BUDGET_EXHAUSTED"
    TAKEOVER_SUPPRESSED = "TAKEOVER_SUPPRESSED"


@dataclass(frozen=True)
class WorkspaceProbeResult:
    """Structured, epistemically honest result of a native workspace health probe."""

    status: WorkspaceHealthStatus
    failure_category: WorkspaceFailureCategory
    is_healthy: bool
    is_recoverable: bool
    active_desktop_generation: int
    hwnd: Optional[int] = None
    expected_geometry: Optional[WorkspaceGeometry] = None
    measured_window_rect: Optional[BoundingBox] = None
    timestamp_ns: int = 0
    error_message: Optional[str] = None
    recovery_attempts_count: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 2. Watchdog Policy Configuration
# ============================================================================

@dataclass(frozen=True)
class WorkspaceWatchdogPolicy:
    """Tunable policy configuration for workspace watchdog polling and recovery."""

    poll_interval_sec: float = 1.0
    max_recovery_attempts: int = 3
    recovery_cooldown_sec: float = 2.0
    auto_recovery_enabled: bool = True
    geometry_drift_tolerance_px: int = 5


# ============================================================================
# 3. Native Win32 Watchdog Gateway
# ============================================================================

class WatchdogNativeGateway:
    """Win32 API gateway for non-invasive native window and HWND introspection."""

    def __init__(self, user32: Any = None) -> None:
        if IS_WINDOWS:
            self._user32 = user32 or ctypes.WinDLL("user32", use_last_error=True)
            self._setup_signatures()
        else:
            self._user32 = None

    def _setup_signatures(self) -> None:
        if self._user32 is None:
            return

        # IsWindow
        self._user32.IsWindow.argtypes = [wintypes.HWND]
        self._user32.IsWindow.restype = wintypes.BOOL

        # GetWindowRect
        self._user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            wintypes.LPRECT,
        ]
        self._user32.GetWindowRect.restype = wintypes.BOOL

        # IsWindowVisible
        self._user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self._user32.IsWindowVisible.restype = wintypes.BOOL

        # IsIconic (Minimized check)
        self._user32.IsIconic.argtypes = [wintypes.HWND]
        self._user32.IsIconic.restype = wintypes.BOOL

    def is_window(self, hwnd: int) -> bool:
        """Check whether the given HWND is an existing, valid native window."""
        if not IS_WINDOWS or self._user32 is None or hwnd <= 0:
            return False
        return bool(self._user32.IsWindow(wintypes.HWND(hwnd)))

    def get_window_rect(self, hwnd: int) -> Optional[BoundingBox]:
        """Query the live physical screen coordinates of the window."""
        if not IS_WINDOWS or self._user32 is None or hwnd <= 0:
            return None
        rc = RECT()
        res = self._user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rc))
        if not res:
            return None
        return rc.to_bounding_box()

    def is_window_visible(self, hwnd: int) -> bool:
        """Check if the window is currently marked visible on screen."""
        if not IS_WINDOWS or self._user32 is None or hwnd <= 0:
            return False
        return bool(self._user32.IsWindowVisible(wintypes.HWND(hwnd)))

    def is_window_iconic(self, hwnd: int) -> bool:
        """Check if the window is currently minimized."""
        if not IS_WINDOWS or self._user32 is None or hwnd <= 0:
            return False
        return bool(self._user32.IsIconic(wintypes.HWND(hwnd)))


# ============================================================================
# 4. Workspace Watchdog
# ============================================================================

class WorkspaceWatchdog:
    """Active watchdog monitoring native AppBar health, detecting drift, and enforcing fail-closed recovery."""

    def __init__(
        self,
        state_manager: WorkspaceStateManager,
        geometry_coordinator: WorkspaceGeometryCoordinator,
        appbar_driver: Optional[NativeAppBarDriver] = None,
        window: Optional[NativeWorkspaceWindow] = None,
        policy: WorkspaceWatchdogPolicy = WorkspaceWatchdogPolicy(),
        gateway: Optional[WatchdogNativeGateway] = None,
        is_takeover_active_fn: Optional[Callable[[], bool]] = None,
        telemetry: Optional[WorkspaceTelemetryRecorder] = None,
    ) -> None:
        self.state_manager = state_manager
        self.geometry_coordinator = geometry_coordinator
        self.appbar_driver = appbar_driver
        self.window = window
        self.policy = policy
        self.gateway = gateway or WatchdogNativeGateway()
        self.is_takeover_active_fn = is_takeover_active_fn
        self.telemetry = telemetry

        self._task: Optional[asyncio.Task[None]] = None
        self._is_running = False
        self._lock = asyncio.Lock()
        self._last_probe: Optional[WorkspaceProbeResult] = None
        self._consecutive_failures = 0
        self._last_recovery_time_sec = 0.0

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def last_probe_result(self) -> Optional[WorkspaceProbeResult]:
        return self._last_probe

    @property
    def consecutive_failures_count(self) -> int:
        return self._consecutive_failures

    async def start(self) -> None:
        """Start the background watchdog polling loop deterministically."""
        async with self._lock:
            if self._is_running:
                logger.debug("WorkspaceWatchdog is already running; start() is a no-op")
                return
            self._is_running = True
            self._task = asyncio.create_task(self._run_loop())
            logger.info("WorkspaceWatchdog started (poll_interval=%.2fs)", self.policy.poll_interval_sec)

    async def stop(self) -> None:
        """Stop the background watchdog worker deterministically."""
        async with self._lock:
            if not self._is_running:
                return
            self._is_running = False
            if self._task is not None:
                self._task.cancel()
                try:
                    await asyncio.wait_for(self._task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                self._task = None
            logger.info("WorkspaceWatchdog stopped cleanly")

    async def _run_loop(self) -> None:
        """Internal asynchronous watchdog polling loop."""
        try:
            while self._is_running:
                try:
                    probe_res = self.probe_health()
                    self._last_probe = probe_res

                    if not probe_res.is_healthy and self.policy.auto_recovery_enabled:
                        await self.attempt_recovery(probe_res)

                except Exception as ex:
                    logger.error("Unexpected error in WorkspaceWatchdog poll cycle: %s", ex, exc_info=True)

                await asyncio.sleep(self.policy.poll_interval_sec)
        except asyncio.CancelledError:
            pass

    def probe_health(self) -> WorkspaceProbeResult:
        """Synchronously probe live native state and evaluate workspace health."""
        now_ns = time.perf_counter_ns()
        current_state = self.state_manager.current_state
        active_gen = self.state_manager.desktop_generation_id

        # 1. Stopped or Uninitialized states
        if current_state in {WorkspaceState.STOPPED, WorkspaceState.UNINITIALIZED}:
            return WorkspaceProbeResult(
                status=WorkspaceHealthStatus.STOPPED if current_state == WorkspaceState.STOPPED else WorkspaceHealthStatus.UNKNOWN,
                failure_category=WorkspaceFailureCategory.NONE,
                is_healthy=(current_state != WorkspaceState.STOPPED),
                is_recoverable=False,
                active_desktop_generation=active_gen,
                timestamp_ns=now_ns,
            )

        # 2. Ready Floating (AppBar not docked)
        if current_state == WorkspaceState.READY_FLOATING:
            # Check topology stability
            current_geom = self.geometry_coordinator.query_current_geometry(is_docked=False)
            self._consecutive_failures = 0
            return WorkspaceProbeResult(
                status=WorkspaceHealthStatus.HEALTHY,
                failure_category=WorkspaceFailureCategory.NONE,
                is_healthy=True,
                is_recoverable=True,
                active_desktop_generation=active_gen,
                expected_geometry=current_geom,
                timestamp_ns=now_ns,
            )

        # 3. DOCKED State Verification
        if current_state == WorkspaceState.DOCKED:
            # Resolve native window handle
            hwnd: Optional[int] = None
            if self.appbar_driver and self.appbar_driver.window:
                hwnd = self.appbar_driver.window.hwnd
            elif self.window:
                hwnd = self.window.hwnd

            if hwnd is None or hwnd <= 0:
                self._handle_failure_transition(WorkspaceState.FAILED, "Window handle is missing or 0 while DOCKED")
                return WorkspaceProbeResult(
                    status=WorkspaceHealthStatus.FAILED,
                    failure_category=WorkspaceFailureCategory.INVALID_HWND,
                    is_healthy=False,
                    is_recoverable=False,
                    active_desktop_generation=self.state_manager.desktop_generation_id,
                    hwnd=hwnd,
                    timestamp_ns=now_ns,
                    error_message="HWND handle is 0 or unassigned while state is DOCKED",
                )

            # Check HWND validity via IsWindow
            if not self.gateway.is_window(hwnd):
                self._handle_failure_transition(WorkspaceState.FAILED, f"Native window HWND {hwnd} destroyed externally")
                return WorkspaceProbeResult(
                    status=WorkspaceHealthStatus.FAILED,
                    failure_category=WorkspaceFailureCategory.WINDOW_DESTROYED,
                    is_healthy=False,
                    is_recoverable=False,
                    active_desktop_generation=self.state_manager.desktop_generation_id,
                    hwnd=hwnd,
                    timestamp_ns=now_ns,
                    error_message=f"Native window HWND {hwnd} was destroyed externally",
                )

            # Check geometry parity
            measured_rect = self.gateway.get_window_rect(hwnd)
            expected_geom = self.geometry_coordinator.query_current_geometry(
                dock_edge=self.appbar_driver.dock_edge if self.appbar_driver else DockEdge.RIGHT,
                docked_bounds=self.appbar_driver.docked_bounds if self.appbar_driver else None,
                is_docked=True,
            )

            if measured_rect is None:
                self._consecutive_failures += 1
                return WorkspaceProbeResult(
                    status=WorkspaceHealthStatus.DEGRADED,
                    failure_category=WorkspaceFailureCategory.NATIVE_PROBE_FAILED,
                    is_healthy=False,
                    is_recoverable=True,
                    active_desktop_generation=active_gen,
                    hwnd=hwnd,
                    expected_geometry=expected_geom,
                    timestamp_ns=now_ns,
                    error_message="Failed to query live window rect via GetWindowRect",
                )

            if expected_geom.docked_bounds is not None:
                exp = expected_geom.docked_bounds
                dx = abs(measured_rect.left - exp.left)
                dy = abs(measured_rect.top - exp.top)
                dw = abs(measured_rect.width - exp.width)
                dh = abs(measured_rect.height - exp.height)
                tol = self.policy.geometry_drift_tolerance_px

                if dx > tol or dy > tol or dw > tol or dh > tol:
                    self._consecutive_failures += 1
                    return WorkspaceProbeResult(
                        status=WorkspaceHealthStatus.DEGRADED,
                        failure_category=WorkspaceFailureCategory.GEOMETRY_MISMATCH,
                        is_healthy=False,
                        is_recoverable=True,
                        active_desktop_generation=active_gen,
                        hwnd=hwnd,
                        expected_geometry=expected_geom,
                        measured_window_rect=measured_rect,
                        timestamp_ns=now_ns,
                        error_message=(
                            f"Window geometry drifted from expected dock bounds "
                            f"(Measured: {measured_rect.left},{measured_rect.top} {measured_rect.width}x{measured_rect.height}, "
                            f"Expected: {exp.left},{exp.top} {exp.width}x{exp.height})"
                        ),
                    )

            # All checks pass
            self._consecutive_failures = 0
            return WorkspaceProbeResult(
                status=WorkspaceHealthStatus.HEALTHY,
                failure_category=WorkspaceFailureCategory.NONE,
                is_healthy=True,
                is_recoverable=True,
                active_desktop_generation=active_gen,
                hwnd=hwnd,
                expected_geometry=expected_geom,
                measured_window_rect=measured_rect,
                timestamp_ns=now_ns,
            )

        # Degraded or Failed states
        return WorkspaceProbeResult(
            status=WorkspaceHealthStatus.DEGRADED if current_state == WorkspaceState.DEGRADED else WorkspaceHealthStatus.FAILED,
            failure_category=WorkspaceFailureCategory.NONE,
            is_healthy=False,
            is_recoverable=(current_state == WorkspaceState.DEGRADED),
            active_desktop_generation=active_gen,
            timestamp_ns=now_ns,
        )

    async def attempt_recovery(self, probe: WorkspaceProbeResult) -> bool:
        """Attempt safe, bounded automatic recovery from degraded workspace states."""
        # Check human takeover suppression
        if self.is_takeover_active_fn and self.is_takeover_active_fn():
            logger.info("Workspace recovery suppressed: Human takeover is currently active")
            return False

        # If not recoverable, abort immediately
        if not probe.is_recoverable:
            return False

        now_sec = time.time()
        if (now_sec - self._last_recovery_time_sec) < self.policy.recovery_cooldown_sec:
            logger.debug("Recovery in cooldown; skipping attempt")
            return False

        self._last_recovery_time_sec = now_sec

        # Check recovery budget
        if self._consecutive_failures >= self.policy.max_recovery_attempts:
            logger.warning(
                "Workspace recovery budget exhausted (%d attempts >= max %d); failing closed",
                self._consecutive_failures,
                self.policy.max_recovery_attempts,
            )
            self._handle_failure_transition(
                WorkspaceState.FAILED,
                f"Recovery budget exhausted after {self._consecutive_failures} consecutive failures",
            )
            return False

        # Attempt recovery action based on category
        logger.info("Attempting workspace recovery for failure category: %s", probe.failure_category.value)

        try:
            if probe.failure_category == WorkspaceFailureCategory.GEOMETRY_MISMATCH:
                if self.appbar_driver and self.appbar_driver.window and probe.expected_geometry:
                    exp_rect = probe.expected_geometry.docked_bounds
                    if exp_rect:
                        self.appbar_driver.window.set_position(exp_rect)
                        logger.info("Re-asserted native window position to expected dock geometry")
                        # Invalidate coordinate generation due to repositioning
                        self.state_manager.increment_desktop_generation()
                        return True

            elif probe.failure_category in {WorkspaceFailureCategory.TOPOLOGY_CHANGED, WorkspaceFailureCategory.NATIVE_PROBE_FAILED}:
                self.geometry_coordinator.state_manager.increment_topology_generation()
                self.geometry_coordinator.query_current_geometry(
                    dock_edge=self.appbar_driver.dock_edge if self.appbar_driver else DockEdge.NONE,
                    is_docked=self.state_manager.is_docked,
                )
                return True

        except Exception as ex:
            logger.error("Exception occurred during workspace recovery attempt: %s", ex, exc_info=True)

        return False

    def _handle_failure_transition(self, target_state: WorkspaceState, reason: str) -> None:
        """Safely transition state and record failure telemetry without crashing."""
        try:
            if self.state_manager.can_transition_to(target_state):
                self.state_manager.transition_to(target_state, reason=reason)
                if self.telemetry:
                    self.telemetry.record_error(f"Watchdog: {reason}")
        except Exception as ex:
            logger.error("Failed to execute state transition to %s: %s", target_state.value, ex)
