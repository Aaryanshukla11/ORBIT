"""Current State Observer for cognitive runtime perception."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from orbit.contracts.capabilities import ObservationCapability
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.perception import SemanticPerceptionEngine

logger = logging.getLogger(__name__)


class CurrentStateObserver:
    """Observes live desktop window state, foreground application, screen pixels, and target entities."""

    def __init__(
        self,
        observation: Optional[ObservationCapability] = None,
        perception_engine: Optional[SemanticPerceptionEngine] = None,
    ) -> None:
        self._observation = observation
        self._perception_engine = perception_engine or SemanticPerceptionEngine()

    @property
    def observation(self) -> Optional[ObservationCapability]:
        return self._observation

    def set_observation(self, observation: ObservationCapability) -> None:
        self._observation = observation

    async def observe(
        self,
        objective: Optional[StructuredObjective] = None,
    ) -> CurrentStateObservation:
        """Capture live state observation relative to the current objective."""
        now = datetime.now(timezone.utc)
        active_hwnd, active_title, active_class = self._get_foreground_window_info()
        visible_windows = self._enumerate_visible_windows()

        target_app_name = ""
        if objective and objective.parameters:
            target_app_name = str(objective.parameters.get("app_name", "")).lower()
        if not target_app_name and objective and objective.target_entities:
            target_app_name = str(objective.target_entities[0]).lower()

        # Check if target app exists and is active
        target_app_exists = False
        target_app_is_active = False

        if target_app_name:
            # Check active window match
            if self._matches_app(active_title, active_class, target_app_name):
                target_app_exists = True
                target_app_is_active = True
            else:
                # Check visible windows
                for win in visible_windows:
                    if self._matches_app(win.get("title", ""), win.get("class_name", ""), target_app_name):
                        target_app_exists = True
                        break

        # Capture OCR / Perceptual Screen Frame if Observation Capability is present
        ocr_tokens: List[str] = []
        canvas_status = None
        screen_summary = ""

        if self._observation is not None:
            try:
                frame = await self._observation.capture_screen(display_index=0)
                if frame:
                    screen_summary = f"Screen captured ({getattr(frame.resolution, 'width', 1920)}x{getattr(frame.resolution, 'height', 1080)})"
                    # Run perception if needed
                    if self._perception_engine and hasattr(frame, "data") and frame.data:
                        try:
                            perception_res = await self._perception_engine.perceive(frame)
                            if perception_res:
                                for elem in getattr(perception_res, "elements", []):
                                    if getattr(elem, "text", None):
                                        ocr_tokens.append(elem.text)
                        except Exception as p_ex:
                            logger.debug("Perception engine notice: %s", p_ex)
            except Exception as ex:
                logger.debug("Perceptual observation capture skipped: %s", ex)

        # Infer Canvas Status if objective is drawing
        if objective and "draw" in str(objective.parameters.get("action_type", "")).lower():
            if target_app_is_active:
                canvas_status = "READY_FOR_DRAWING"
            elif target_app_exists:
                canvas_status = "TARGET_OPEN_NEEDS_FOCUS"
            else:
                canvas_status = "TARGET_NOT_OPEN"

        return CurrentStateObservation(
            timestamp_utc=now,
            active_window_hwnd=active_hwnd,
            active_window_title=active_title,
            active_window_class=active_class,
            visible_windows=visible_windows,
            target_app_exists=target_app_exists,
            target_app_is_active=target_app_is_active,
            screen_summary=screen_summary or f"Active: '{active_title}' (HWND: {active_hwnd})",
            canvas_status=canvas_status,
            ocr_tokens=ocr_tokens,
            raw_evidence={
                "target_app_name": target_app_name,
                "visible_window_count": len(visible_windows),
            },
        )

    def _matches_app(self, title: Optional[str], class_name: Optional[str], target: str) -> bool:
        """Helper to match window title/class against target app name."""
        t_low = (title or "").lower()
        c_low = (class_name or "").lower()
        tgt_low = target.lower()

        if tgt_low in ("paint", "mspaint"):
            return "paint" in t_low or "mspaintapp" in c_low or "msppaint" in c_low
        if tgt_low in ("notepad", "notepad.exe"):
            return "notepad" in t_low or "notepad" in c_low
        if tgt_low in ("calculator", "calc"):
            return "calc" in t_low or "calculator" in t_low or "applicationframewindow" in c_low and "calculator" in t_low
        if tgt_low in ("edge", "msedge"):
            return "edge" in t_low or "edge" in c_low
        if tgt_low in ("chrome", "google-chrome"):
            return "chrome" in t_low or "chrome" in c_low

        return tgt_low in t_low or tgt_low in c_low

    def _get_foreground_window_info(self) -> tuple[Optional[int], Optional[str], Optional[str]]:
        """Query the current Win32 foreground window HWND, title, and class."""
        if sys.platform != "win32":
            return 1001, "Mock Desktop Active Window", "MockWindowClass"

        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None, None, None

            # Get title
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value

            # Get class name
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            cls_name = cls_buf.value

            return hwnd, title, cls_name
        except Exception as ex:
            logger.debug("Win32 foreground window query notice: %s", ex)
            return None, None, None

    def _enumerate_visible_windows(self) -> List[Dict[str, Any]]:
        """Enumerate visible top-level windows on the desktop."""
        if sys.platform != "win32":
            return [{"hwnd": 1001, "title": "Mock Desktop Window", "class_name": "MockWindowClass"}]

        windows: List[Dict[str, Any]] = []
        try:
            user32 = ctypes.windll.user32
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def enum_proc(hwnd: Any, lparam: Any) -> bool:
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value
                        cls_buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(hwnd, cls_buf, 256)
                        windows.append({
                            "hwnd": hwnd,
                            "title": title,
                            "class_name": cls_buf.value,
                        })
                return True

            cb = WNDENUMPROC(enum_proc)
            user32.EnumWindows(cb, 0)
        except Exception as ex:
            logger.debug("Win32 EnumWindows notice: %s", ex)

        return windows
