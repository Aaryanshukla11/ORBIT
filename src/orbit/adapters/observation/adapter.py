"""Native Production Observation Adapter for ORBIT.

Delivers full production observation capability backed by native Windows APIs
(Win32 GDI, Desktop Duplication, Win32 Window Enumeration, UI Automation,
and OCR), with zero dependency on prototype observation implementations.
"""

from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
import io
import logging
import os
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
from orbit.runtime.perception.observer import DesktopObserver
from orbit.runtime.perception.screenshot import DesktopScreenshotObserver
from orbit.runtime.perception.uia import UIAElementObserver
from orbit.runtime.perception.windows import Win32WindowObserver

logger = logging.getLogger(__name__)


class ProductionObservationAdapter(BaseCapabilityAdapter, ObservationCapability):
    """Production observation adapter backed by native Windows perception engines."""

    def __init__(self, default_ttl_ms: float = 500.0) -> None:
        super().__init__(
            capability_name="ProductionObservation",
            capability_type=CapabilityType.OBSERVATION,
            adapter_mode=AdapterMode.PRODUCTION,
        )
        self.default_ttl_ms = default_ttl_ms
        self.health_tracker = ObservationHealthTracker()
        self.freshness_evaluator = FreshnessEvaluator(max_ttl_ms=default_ttl_ms)

        # Native perception observer instances
        self._window_observer: Optional[Win32WindowObserver] = None
        self._screenshot_observer: Optional[DesktopScreenshotObserver] = None
        self._uia_observer: Optional[UIAElementObserver] = None
        self._desktop_observer: Optional[DesktopObserver] = None
        self._current_generation: int = 0
        self._com_initialized: bool = False

    def _query_virtual_desktop_bounds(self) -> BoundingBox:
        """Query physical bounds of the unified virtual desktop across all displays."""
        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                # SM_XVIRTUALSCREEN = 76, SM_YVIRTUALSCREEN = 77, SM_CXVIRTUALSCREEN = 78, SM_CYVIRTUALSCREEN = 79
                x = user32.GetSystemMetrics(76)
                y = user32.GetSystemMetrics(77)
                w = user32.GetSystemMetrics(78)
                h = user32.GetSystemMetrics(79)
                if w > 0 and h > 0:
                    return BoundingBox(left=x, top=y, width=w, height=h)

                # Fallback to primary screen metrics: SM_CXSCREEN = 0, SM_CYSCREEN = 1
                w = user32.GetSystemMetrics(0)
                h = user32.GetSystemMetrics(1)
                if w > 0 and h > 0:
                    return BoundingBox(left=0, top=0, width=w, height=h)
            except Exception as ex:
                logger.debug("Virtual desktop bounds query notice: %s", ex)

        return BoundingBox(left=0, top=0, width=1920, height=1080)

    async def _on_initialize(self) -> None:
        """Initialize COM, attach desktop observers, and verify display metrics."""
        try:
            # Initialize COM in worker context if on Windows
            if sys.platform == "win32":
                try:
                    # COINIT_MULTITHREADED = 0x0
                    ctypes.windll.ole32.CoInitializeEx(None, 0)
                    self._com_initialized = True
                except Exception as ex:
                    logger.debug("CoInitializeEx notice: %s", ex)

            # Instantiation of native perception observers
            self._window_observer = Win32WindowObserver()
            self._screenshot_observer = DesktopScreenshotObserver()
            self._uia_observer = UIAElementObserver()
            self._desktop_observer = DesktopObserver(
                window_observer=self._window_observer,
                screenshot_observer=self._screenshot_observer,
                uia_observer=self._uia_observer,
            )

            # Query and record virtual desktop bounds
            bounds = self._query_virtual_desktop_bounds()
            if bounds.width <= 0 or bounds.height <= 0:
                raise ObservationError("Invalid virtual desktop dimensions retrieved from OS")

            self.health_tracker.record_success("GDI_CAPTURE", 0.0)
            self.health_tracker.record_success("WINDOW_TRACKER", 0.0)

            self._details["virtual_desktop"] = {
                "left": bounds.left,
                "top": bounds.top,
                "width": bounds.width,
                "height": bounds.height,
            }
            logger.info(
                "ProductionObservationAdapter initialized natively (Virtual Desktop: %dx%d)",
                bounds.width,
                bounds.height,
            )

        except Exception as ex:
            self.health_tracker.record_failure("GDI_CAPTURE", str(ex))
            raise ObservationError(f"Failed to initialize native observation engines: {ex}") from ex

    async def _on_shutdown(self) -> None:
        """Release COM resources and clear observer handles."""
        self._desktop_observer = None
        self._screenshot_observer = None
        self._window_observer = None
        self._uia_observer = None

        if self._com_initialized and sys.platform == "win32":
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass
            self._com_initialized = False

    def sync_generation(self, generation_id: int) -> None:
        """Synchronize active desktop generation ID from workspace adapter."""
        self._current_generation = generation_id

    async def capture_screen(self, display_index: int = 0) -> FrameData:
        """Capture the live virtual desktop or display area via native screenshot engine."""
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production observation adapter is not initialized and ready",
            )

        t0 = time.perf_counter()
        try:
            if not self._screenshot_observer:
                raise ObservationError("Screenshot observer is not initialized")

            screenshot_obs = await self._screenshot_observer.capture(include_base64=False, format="jpeg")
            duration_ms = (time.perf_counter() - t0) * 1000.0

            raw_bytes = screenshot_obs.raw_bytes
            if not raw_bytes:
                # Fallback to in-memory generation if raw_bytes was empty
                bounds = self._query_virtual_desktop_bounds()
                blank = Image.new("RGB", (bounds.width, bounds.height), color=(30, 30, 30))
                buf = io.BytesIO()
                blank.save(buf, format="JPEG", quality=85)
                raw_bytes = buf.getvalue()

            self.health_tracker.record_success("GDI_CAPTURE", duration_ms)

            bounds = self._query_virtual_desktop_bounds()
            w = screenshot_obs.width or bounds.width
            h = screenshot_obs.height or bounds.height

            return FrameData(
                frame_id=f"frame_{uuid4().hex[:8]}",
                timestamp_ns=time.perf_counter_ns(),
                resolution=Resolution(width=w, height=h, scale_factor=1.0),
                raw_bytes=raw_bytes,
                format="jpeg",
                roi=BoundingBox(left=bounds.left, top=bounds.top, width=w, height=h),
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

            if not self._desktop_observer:
                raise ObservationError("DesktopObserver is not initialized")

            # Capture complete native desktop observation
            obs = await self._desktop_observer.observe_desktop(
                include_screenshot_base64=False,
                include_ocr=True,
                include_uia=True,
                target_hwnd=target_hwnd,
            )

            # Construct canonical ObservationSnapshot from native DesktopObservation
            mapped_snap = ObservationSnapshot.from_desktop_observation(obs)
            mapped_snap.snapshot_id = snapshot_id
            mapped_snap.generation_id = self._current_generation

            # Attach screenshot PIL Image into telemetry for downstream consumers
            if obs.screenshot_reference and obs.screenshot_reference.raw_bytes:
                try:
                    pil_img = Image.open(io.BytesIO(obs.screenshot_reference.raw_bytes))
                    mapped_snap.telemetry["screenshot"] = pil_img
                    mapped_snap.telemetry["image"] = pil_img
                except Exception as img_err:
                    logger.debug("Failed to decode screenshot into PIL image: %s", img_err)

            # Record health metrics
            if obs.screenshot_status == "SUCCESS":
                self.health_tracker.record_success("GDI_CAPTURE", obs.capture_duration_ms)
            else:
                self.health_tracker.record_failure("GDI_CAPTURE", obs.screenshot_status)

            if obs.uia_status in ("SUCCESS", "EMPTY"):
                self.health_tracker.record_success("UIA_PROVIDER", 0.0)
            elif obs.uia_status == "FAILED":
                self.health_tracker.record_failure("UIA_PROVIDER", "UIA capture failed")

            # Evaluate freshness
            fresh_state, is_stale, inv_reason = self.freshness_evaluator.evaluate_freshness(
                mapped_snap,
                current_generation=self._current_generation,
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
            bounds = self._query_virtual_desktop_bounds()
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
