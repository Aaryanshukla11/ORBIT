"""Production Observation Adapter integrating Prototype D capabilities into ORBIT."""

from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
import io
import logging
import sys
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4
from PIL import Image

from orbit.adapters.base import (
    BaseCapabilityAdapter,
    CapabilityUnavailableError,
    ObservationError,
)
from orbit.adapters.observation.freshness import FreshnessEvaluator
from orbit.adapters.observation.health import ObservationHealthTracker
from orbit.adapters.observation.mapper import (
    map_prototype_snapshot,
    map_rect_to_bounding_box,
)
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationSnapshot,
)
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealth,
    CapabilityLifecycleState,
    CapabilityType,
    DisplayMetrics,
    FrameData,
    ObservationCapability,
)
from orbit.models.common import BoundingBox, Resolution

logger = logging.getLogger(__name__)


class ProductionObservationAdapter(BaseCapabilityAdapter, ObservationCapability):
    """Production observation adapter backed by validated Prototype D observation engines."""

    def __init__(self, default_ttl_ms: float = 500.0) -> None:
        super().__init__(
            capability_name="ProductionObservation",
            capability_type=CapabilityType.OBSERVATION,
            adapter_mode=AdapterMode.PRODUCTION,
        )
        self.default_ttl_ms = default_ttl_ms
        self.health_tracker = ObservationHealthTracker()
        self.freshness_evaluator = FreshnessEvaluator(max_ttl_ms=default_ttl_ms)

        # Prototype D engine instances (instantiated on initialize, not import time)
        self._coord_mapper: Any = None
        self._capture_engine: Any = None
        self._window_tracker: Any = None
        self._acc_coordinator: Any = None
        self._freshness_tracker: Any = None
        self._com_initialized = False

    async def _on_initialize(self) -> None:
        """Initialize COM, DPI awareness, and Prototype D observation engines."""
        try:
            # Ensure Prototype D internal modules (like app_types) resolve cleanly
            from pathlib import Path
            proto_d_dir = str(Path(__file__).resolve().parents[4] / "prototypes" / "prototype_d_observation")
            if proto_d_dir not in sys.path:
                sys.path.insert(0, proto_d_dir)

            # Lazy import inside adapter boundary
            from coordinate_mapper import CoordinateMapper
            from capture_engine import CaptureEngine
            from window_tracker import WindowTracker
            from accessibility_coordinator import AccessibilityCoordinator
            from freshness_tracker import FreshnessTracker

            # Initialize COM in worker context if on Windows
            if sys.platform == "win32":
                try:
                    # COINIT_MULTITHREADED = 0x0
                    ctypes.windll.ole32.CoInitializeEx(None, 0)
                    self._com_initialized = True
                except Exception as ex:
                    logger.debug("CoInitializeEx notice: %s", ex)

            # Instantiation of Prototype D engines
            self._coord_mapper = CoordinateMapper()
            self._capture_engine = CaptureEngine()
            self._window_tracker = WindowTracker()
            self._acc_coordinator = AccessibilityCoordinator()
            self._freshness_tracker = FreshnessTracker(default_ttl_ms=self.default_ttl_ms)

            # Test basic GDI virtual desktop query
            bounds = self._coord_mapper.get_virtual_desktop_bounds()
            if bounds.width <= 0 or bounds.height <= 0:
                raise ObservationError("Invalid virtual desktop dimensions retrieved from GDI")

            self.health_tracker.record_success("GDI_CAPTURE", 0.0)
            self.health_tracker.record_success("WINDOW_TRACKER", 0.0)

            self._details["virtual_desktop"] = {
                "left": bounds.left,
                "top": bounds.top,
                "width": bounds.width,
                "height": bounds.height,
            }
            logger.info(
                "ProductionObservationAdapter initialized (Virtual Desktop: %dx%d)",
                bounds.width,
                bounds.height,
            )

        except Exception as ex:
            self.health_tracker.record_failure("GDI_CAPTURE", str(ex))
            raise ObservationError(f"Failed to initialize Prototype D observation engines: {ex}") from ex

    async def _on_shutdown(self) -> None:
        """Release COM resources and clear engine handles."""
        self._capture_engine = None
        self._window_tracker = None
        self._acc_coordinator = None
        self._freshness_tracker = None
        self._coord_mapper = None

        if self._com_initialized and sys.platform == "win32":
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass
            self._com_initialized = False

    def sync_generation(self, generation_id: int) -> None:
        """Synchronize active desktop generation ID from workspace adapter."""
        if self._freshness_tracker is not None:
            self._freshness_tracker._current_generation = generation_id

    async def capture_screen(self, display_index: int = 0) -> FrameData:
        """Capture the live virtual desktop or display area via Win32 GDI capture engine."""
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production observation adapter is not initialized and ready",
            )

        t0 = time.perf_counter()
        try:
            # Capture full virtual desktop in thread pool to avoid blocking async loop
            img, duration_ms, bounds = await asyncio.to_thread(
                self._capture_engine.capture_full_desktop
            )

            if img is None:
                raise ObservationError("GDI screen capture returned None")

            # Compress to JPEG in memory
            buffer = io.BytesIO()
            img.convert("RGB").save(buffer, format="JPEG", quality=85)
            raw_bytes = buffer.getvalue()

            self.health_tracker.record_success("GDI_CAPTURE", duration_ms)

            return FrameData(
                frame_id=f"frame_{uuid4().hex[:8]}",
                timestamp_ns=time.perf_counter_ns(),
                resolution=Resolution(width=bounds.width, height=bounds.height, scale_factor=1.0),
                raw_bytes=raw_bytes,
                format="jpeg",
                roi=BoundingBox(left=bounds.left, top=bounds.top, width=bounds.width, height=bounds.height),
            )

        except Exception as ex:
            self.health_tracker.record_failure("GDI_CAPTURE", str(ex))
            raise ObservationError(f"Live screen capture failed: {ex}") from ex

    async def capture_snapshot(self, target_hwnd: Optional[int] = None) -> ObservationSnapshot:
        """Capture a rich multi-source observation snapshot of the desktop state."""
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production observation adapter is not ready",
            )

        t0 = time.perf_counter()
        try:
            snapshot_id = f"snap_{uuid4().hex[:12]}"

            # Execute capture pipeline in worker thread
            def _do_snapshot() -> Any:
                com_inited = False
                if sys.platform == "win32":
                    try:
                        hr = ctypes.windll.ole32.CoInitializeEx(None, 0)
                        com_inited = (hr in (0, 1))
                    except Exception:
                        pass
                try:
                    from app_types import ConfidenceLevel 
                    bounds = self._coord_mapper.get_virtual_desktop_bounds()
                    fg_win = self._window_tracker.get_foreground_window_observation()
                    active_hwnd = target_hwnd or (fg_win.hwnd if fg_win else 0)
                    if target_hwnd and fg_win and target_hwnd != fg_win.hwnd:
                        active_win = self._window_tracker.get_window_observation(target_hwnd)
                    else:
                        active_win = fg_win

                    # Check if active_hwnd belongs to the current process to prevent COM/MSAA cross-thread deadlock
                    import os
                    is_local_process_window = False
                    if active_hwnd and sys.platform == "win32":
                        pid = wintypes.DWORD(0)
                        ctypes.windll.user32.GetWindowThreadProcessId(active_hwnd, ctypes.byref(pid))
                        if pid.value == os.getpid():
                            is_local_process_window = True

                    # Window observations from WindowTracker (handles thread and input desktop enumeration)
                    windows = tuple(self._window_tracker.enumerate_visible_windows())

                    # Accessibility observations: query explicit target_hwnd or fallback to active foreground window
                    acc_hwnd = target_hwnd if (target_hwnd and not is_local_process_window) else (active_hwnd if (active_hwnd and not is_local_process_window) else 0)
                    elements, prov_results = ((), ())
                    if acc_hwnd:
                        try:
                            elements, prov_results = self._acc_coordinator.collect_accessibility_observations(
                                hwnd=acc_hwnd,
                                generation_id=self._freshness_tracker.current_generation,
                            )
                        except Exception as acc_ex:
                            self.health_tracker.record_failure("ACC_COORDINATOR", str(acc_ex))
                            elements, prov_results = ((), ())

                    # Record individual provider health results
                    for pres in prov_results:
                        if hasattr(pres, "status") and getattr(pres.status, "value", str(pres.status)) == "SUCCESS":
                            self.health_tracker.record_success(pres.provider_name, getattr(pres, "duration_ms", 0.0))
                        else:
                            err = getattr(pres, "error_message", "Error") or "Error"
                            self.health_tracker.record_failure(getattr(pres, "provider_name", "UNKNOWN"), str(err))

                    # Determine snapshot confidence
                    conf = ConfidenceLevel.CONFIRMED if (active_win and elements) else ConfidenceLevel.PARTIALLY_CONFIRMED

                    # Capture live screenshot for visual/OCR pipelines
                    img = None
                    try:
                        img, _, _ = self._capture_engine.capture_full_desktop()
                    except Exception as cap_err:
                        logger.debug("Desktop screenshot capture skipped: %s", cap_err)

                    # Build Prototype D snapshot
                    proto_snap = self._freshness_tracker.build_snapshot(
                        snapshot_id=snapshot_id,
                        capture_duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                        desktop_geometry=bounds,
                        foreground_window=active_win,
                        windows=windows,
                        visual_evidence=(),
                        accessibility_evidence=elements,
                        detected_targets=(),
                        confidence=conf,
                        conflicts=(),
                    )
                    return proto_snap, img
                finally:
                    if com_inited and sys.platform == "win32":
                        try:
                            ctypes.windll.ole32.CoUninitialize()
                        except Exception:
                            pass

            proto_snap, img = await asyncio.to_thread(_do_snapshot)

            # Map to production contract
            mapped_snap = map_prototype_snapshot(proto_snap, snapshot_id=snapshot_id)
            if img is not None:
                mapped_snap.telemetry["screenshot"] = img
                mapped_snap.telemetry["image"] = img

            # Evaluate freshness
            fresh_state, is_stale, inv_reason = self.freshness_evaluator.evaluate_freshness(
                mapped_snap,
                current_generation=self._freshness_tracker.current_generation,
            )
            mapped_snap.freshness_state = fresh_state
            mapped_snap.is_stale = is_stale
            mapped_snap.invalidation_reason = inv_reason

            return mapped_snap

        except Exception as ex:
            logger.exception("Failed to capture observation snapshot: %s", ex)
            raise ObservationError(f"Snapshot capture failed: {ex}") from ex

    async def get_display_metrics(self) -> List[DisplayMetrics]:
        """Query attached monitor topologies and DPI metrics."""
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production observation adapter is not ready",
            )

        try:
            bounds = self._coord_mapper.get_virtual_desktop_bounds()
            return [
                DisplayMetrics(
                    display_index=0,
                    bounds=BoundingBox(left=bounds.left, top=bounds.top, width=bounds.width, height=bounds.height),
                    resolution=Resolution(width=bounds.width, height=bounds.height, scale_factor=1.0),
                    is_primary=True,
                )
            ]
        except Exception as ex:
            raise ObservationError(f"Failed to query display metrics: {ex}") from ex

    async def get_health(self) -> CapabilityHealth:
        """Generate structured CapabilityHealth diagnostic report."""
        return self.health_tracker.evaluate_overall_health(self._lifecycle_state)
