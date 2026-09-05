"""
Freshness Tracking & Invalidation Engine for ORBIT Prototype D v1.2.1.
Maintains monotonic desktop generation counters, executes Snapshot Identity Validation,
and triggers multi-signal invalidation to prevent downstream reuse of stale observations.
"""

import ctypes
from ctypes import wintypes
import time
import threading
from typing import Optional, Tuple, List, Dict, Any

from app_types import (
    Rect,
    ObservationSnapshot,
    WindowObservation,
    UIElementObservation,
    VisualFeatureObservation,
    DetectedTarget,
    ConfidenceLevel,
    InvalidationReason,
)
from window_tracker import WindowTracker

user32 = ctypes.windll.user32


class FreshnessTracker:
    """
    Manages desktop state generations and validates snapshot identity & freshness.
    """

    def __init__(self, default_ttl_ms: float = 500.0):
        self._lock = threading.RLock()
        self._current_generation: int = 0
        self.default_ttl_ms = default_ttl_ms
        self.window_tracker = WindowTracker()

    @property
    def current_generation(self) -> int:
        with self._lock:
            return self._current_generation

    def increment_generation(self, reason: InvalidationReason = InvalidationReason.NONE) -> int:
        """Increments monotonic desktop generation counter upon detected state change."""
        with self._lock:
            self._current_generation += 1
            return self._current_generation

    advance_generation = increment_generation

    def validate_snapshot(
        self,
        snapshot: ObservationSnapshot,
        target_hwnd: Optional[int] = None,
        custom_ttl_ms: Optional[float] = None,
    ) -> Tuple[bool, InvalidationReason]:
        """
        Executes Snapshot Identity Validation across 6 physical invariants.
        Returns (is_valid, invalidation_reason).
        """
        # 1. Explicit Target HWND Lifecycle Check
        if target_hwnd:
            if not user32.IsWindow(target_hwnd):
                return False, InvalidationReason.TARGET_DESTROYED

        ttl_ns = int((custom_ttl_ms if custom_ttl_ms is not None else self.default_ttl_ms) * 1_000_000)
        t_now = time.perf_counter_ns()

        # 2. TTL Expiry Check
        if (t_now - snapshot.timestamp_ns) > ttl_ns:
            return False, InvalidationReason.TTL_EXPIRED

        with self._lock:
            # 3. Monotonic Generation Parity Check
            if snapshot.generation_id != self._current_generation:
                return False, InvalidationReason.FOREGROUND_CHANGED

        # 3. Target HWND Lifecycle Check
        check_hwnd = target_hwnd or (snapshot.foreground_window.hwnd if snapshot.foreground_window else 0)
        if check_hwnd:
            if not user32.IsWindow(check_hwnd):
                return False, InvalidationReason.TARGET_DESTROYED

            # 4. Process ID Consistency Check
            pid, _ = self.window_tracker.get_process_info(check_hwnd)
            if snapshot.foreground_window and snapshot.foreground_window.hwnd == check_hwnd:
                if pid != snapshot.foreground_window.process_id:
                    return False, InvalidationReason.TARGET_DESTROYED

            # 5. Window Rectangle Shift / Resize Check
            current_bounds = self.window_tracker.get_extended_frame_bounds(check_hwnd)
            if snapshot.foreground_window and snapshot.foreground_window.hwnd == check_hwnd:
                obs_bounds = snapshot.foreground_window.extended_bounds
                if (current_bounds.left != obs_bounds.left or current_bounds.top != obs_bounds.top or
                    current_bounds.width != obs_bounds.width or current_bounds.height != obs_bounds.height):
                    return False, InvalidationReason.WINDOW_MOVED_OR_RESIZED

            # 6. Foreground Focus Check
            if snapshot.foreground_window and snapshot.foreground_window.hwnd == check_hwnd:
                curr_fg = user32.GetForegroundWindow()
                if curr_fg and curr_fg != check_hwnd:
                    return False, InvalidationReason.FOREGROUND_CHANGED

        return True, InvalidationReason.NONE

    def build_snapshot(
        self,
        snapshot_id: str,
        capture_duration_ms: float,
        desktop_geometry: Rect,
        foreground_window: Optional[WindowObservation],
        windows: Tuple[WindowObservation, ...],
        visual_evidence: Tuple[VisualFeatureObservation, ...],
        accessibility_evidence: Tuple[UIElementObservation, ...],
        detected_targets: Tuple[DetectedTarget, ...],
        confidence: ConfidenceLevel,
        conflicts: Tuple[str, ...],
        telemetry: Optional[Dict[str, Any]] = None,
    ) -> ObservationSnapshot:
        """
        Constructs an immutable ObservationSnapshot tagged with active desktop generation and timestamp.
        """
        with self._lock:
            gen = self._current_generation

        return ObservationSnapshot(
            generation_id=gen,
            timestamp_ns=time.perf_counter_ns(),
            capture_duration_ms=capture_duration_ms,
            desktop_geometry=desktop_geometry,
            foreground_window=foreground_window,
            windows=windows,
            visual_evidence=visual_evidence,
            accessibility_evidence=accessibility_evidence,
            detected_targets=detected_targets,
            confidence=confidence,
            conflicts=conflicts,
            invalidation_state=InvalidationReason.NONE,
            is_stale=False,
            telemetry=telemetry or {},
        )
