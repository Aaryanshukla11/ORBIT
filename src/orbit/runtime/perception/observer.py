"""Canonical Live Desktop Observer (Step 3).

Coordinates live multi-channel perception capture across:
1. Win32 Window Hierarchy (EnumWindows, GetForegroundWindow)
2. Desktop Visual Frame Capture (DXGI, PIL ImageGrab)
3. UI Automation Accessibility Hierarchy (UIA COM descendants)
4. Optical Character Recognition (Windows Native OCR / Tesseract)

Enforces strict observation freshness, timing telemetry, and consistency validation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from orbit.contracts.capabilities import ObservationCapability
from orbit.models.common import BoundingBox
from orbit.runtime.perception.models import (
    DesktopObservation,
    OCRToken,
    ScreenshotObservation,
    UIElementObservation,
    VisualRegion,
    VisualRegionType,
    WindowObservation,
)
from orbit.runtime.perception.ocr import WindowsNativeOCRProvider
from orbit.runtime.perception.screenshot import DesktopScreenshotObserver
from orbit.runtime.perception.uia import UIAElementObserver
from orbit.runtime.perception.windows import Win32WindowObserver

logger = logging.getLogger(__name__)


class DesktopObserver:
    """Production coordinator capturing unified, time-stamped DesktopObservation snapshots."""

    def __init__(
        self,
        window_observer: Optional[Win32WindowObserver] = None,
        screenshot_observer: Optional[DesktopScreenshotObserver] = None,
        uia_observer: Optional[UIAElementObserver] = None,
        observation_capability: Optional[ObservationCapability] = None,
    ) -> None:
        self._window_observer = window_observer or Win32WindowObserver()
        self._screenshot_observer = screenshot_observer or DesktopScreenshotObserver(observation_capability)
        self._uia_observer = uia_observer or UIAElementObserver()
        self._ocr_provider = WindowsNativeOCRProvider()

    def set_observation_capability(self, cap: ObservationCapability) -> None:
        """Attach or update the underlying ObservationCapability."""
        self._screenshot_observer.set_observation_capability(cap)

    async def observe_desktop(
        self,
        include_screenshot_base64: bool = True,
        include_ocr: bool = True,
        include_uia: bool = True,
        target_hwnd: Optional[int] = None,
    ) -> DesktopObservation:
        """Capture an immutable, fresh snapshot of the live desktop state."""
        obs_id = f"obs_{uuid4().hex[:8]}"
        t_start_utc = datetime.now(timezone.utc)
        t_perf_start = time.perf_counter()

        consistency_warnings: List[str] = []

        # 1. Capture Pre-Observation Window State
        fg_pre, visible_pre = self._window_observer.observe_windows()

        # 2. Capture Visual Screenshot Frame
        screenshot_obs: Optional[ScreenshotObservation] = None
        try:
            screenshot_obs = await self._screenshot_observer.capture(include_base64=include_screenshot_base64)
        except Exception as ss_err:
            logger.debug("Screenshot observation capture notice: %s", ss_err)
            consistency_warnings.append(f"Screenshot capture failed: {ss_err}")

        # 3. Interrogate UIA Accessibility Elements (scoped to foreground/target window)
        scoped_hwnd = target_hwnd or (fg_pre.hwnd if fg_pre else None)
        focused_element: Optional[UIElementObservation] = None
        uia_elements: List[UIElementObservation] = []
        if include_uia:
            try:
                focused_element, uia_elements = self._uia_observer.observe_elements(
                    target_hwnd=scoped_hwnd,
                    max_elements=40,
                )
            except Exception as uia_err:
                logger.debug("UIA elements observation notice: %s", uia_err)
                consistency_warnings.append(f"UIA element interrogation notice: {uia_err}")

        # 4. Extract OCR Tokens from Visual Frame
        ocr_tokens: List[OCRToken] = []
        if include_ocr and screenshot_obs and screenshot_obs.raw_bytes:
            try:
                import io
                from PIL import Image
                pil_img = Image.open(io.BytesIO(screenshot_obs.raw_bytes))
                ocr_res = await self._ocr_provider.extract_text(pil_img)
                if ocr_res and ocr_res.is_success:
                    for reg in ocr_res.text_regions:
                        tok_box = BoundingBox(
                            left=reg.bounding_box.left,
                            top=reg.bounding_box.top,
                            width=reg.bounding_box.width,
                            height=reg.bounding_box.height,
                        )
                        ocr_tokens.append(
                            OCRToken(
                                token_id=f"tok_{uuid4().hex[:8]}",
                                text=reg.text,
                                confidence=reg.confidence if reg.confidence is not None else 1.0,
                                bounding_box=tok_box,
                                source="WINDOWS_OCR",
                            )
                        )
            except Exception as ocr_err:
                logger.debug("OCR extraction notice during desktop observation: %s", ocr_err)

        # 5. Detect Visual Regions (e.g. Canvas, Application Window Bounds)
        visual_regions: List[VisualRegion] = []
        canvas_status = "UNKNOWN"
        if fg_pre:
            visual_regions.append(
                VisualRegion(
                    region_id=f"vreg_win_{fg_pre.hwnd}",
                    region_type=VisualRegionType.APPLICATION_WINDOW,
                    bounds=fg_pre.window_bounds,
                    confidence=1.0,
                    description=f"Active application window '{fg_pre.title}'",
                    source="WIN32",
                )
            )
            # Detect Paint/Drawing Canvas region
            if "paint" in fg_pre.title.lower() or "mspaint" in (fg_pre.process_name or "").lower():
                cw = max(200, fg_pre.client_bounds.width - 20)
                ch = max(200, fg_pre.client_bounds.height - 150)
                canvas_bounds = BoundingBox(
                    left=fg_pre.client_bounds.left + 10,
                    top=fg_pre.client_bounds.top + 140,
                    width=cw,
                    height=ch,
                )
                visual_regions.append(
                    VisualRegion(
                        region_id=f"vreg_canvas_{fg_pre.hwnd}",
                        region_type=VisualRegionType.CANVAS,
                        bounds=canvas_bounds,
                        confidence=0.95,
                        description="Paint Drawing Canvas Surface",
                        source="GEOMETRIC_INFERENCE",
                    )
                )
                canvas_status = "READY_FOR_DRAWING"

        # 6. Capture Post-Observation Window State & Consistency Verification
        fg_post, visible_post = self._window_observer.observe_windows()

        is_consistent = True
        if fg_pre and fg_post and fg_pre.hwnd != fg_post.hwnd:
            is_consistent = False
            consistency_warnings.append(
                f"Window focus shifted during observation capture: from HWND {fg_pre.hwnd} ('{fg_pre.title}') to HWND {fg_post.hwnd} ('{fg_post.title}')"
            )

        t_perf_end = time.perf_counter()
        t_completed_utc = datetime.now(timezone.utc)
        duration_ms = (t_perf_end - t_perf_start) * 1000.0

        screen_w = screenshot_obs.width if screenshot_obs else 1920
        screen_h = screenshot_obs.height if screenshot_obs else 1080

        return DesktopObservation(
            observation_id=obs_id,
            timestamp=t_completed_utc,
            screen_width=screen_w,
            screen_height=screen_h,
            foreground_window=fg_post or fg_pre,
            visible_windows=visible_post if visible_post else visible_pre,
            screenshot_reference=screenshot_obs,
            ocr_tokens=ocr_tokens,
            uia_elements=uia_elements,
            visual_regions=visual_regions,
            focused_element=focused_element,
            canvas_status=canvas_status,
            is_consistent=is_consistent,
            consistency_warnings=consistency_warnings,
            capture_started_at=t_start_utc,
            capture_completed_at=t_completed_utc,
            capture_duration_ms=duration_ms,
        )
