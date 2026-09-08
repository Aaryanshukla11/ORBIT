"""Current State Observer for cognitive runtime perception (Step 3).

Integrates DesktopPerceptionEngine to provide fresh multimodal desktop observations
(Win32, UIA, OCR, Visual regions) to the AgentExecutionLoop and Decision Engine.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from orbit.contracts.capabilities import ObservationCapability
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.perception.engine import DesktopPerceptionEngine
from orbit.runtime.perception.models import DesktopObservation

logger = logging.getLogger(__name__)


class CurrentStateObserver:
    """Observes live desktop window state, foreground application, screen pixels, and target entities."""

    def __init__(
        self,
        observation: Optional[ObservationCapability] = None,
        perception_engine: Optional[DesktopPerceptionEngine] = None,
    ) -> None:
        self._observation = observation
        self._perception_engine = perception_engine or DesktopPerceptionEngine(observation_capability=observation)

    @property
    def observation(self) -> Optional[ObservationCapability]:
        return self._observation

    @property
    def perception_engine(self) -> DesktopPerceptionEngine:
        return self._perception_engine

    def set_observation(self, observation: ObservationCapability) -> None:
        self._observation = observation
        self._perception_engine.set_observation_capability(observation)

    async def observe_canonical(
        self,
        target_hwnd: Optional[int] = None,
        include_base64: bool = True,
    ) -> DesktopObservation:
        """Capture canonical, multimodal DesktopObservation snapshot."""
        return await self._perception_engine.observe(
            target_hwnd=target_hwnd,
            include_screenshot_base64=include_base64,
        )

    async def observe(
        self,
        objective: Optional[StructuredObjective] = None,
    ) -> CurrentStateObservation:
        """Capture live state observation relative to the current objective."""
        desktop_obs = await self.observe_canonical()

        target_app_name = ""
        if objective and objective.parameters:
            target_app_name = str(objective.parameters.get("app_name", "")).lower()
        if not target_app_name and objective and objective.target_entities:
            target_app_name = str(objective.target_entities[0]).lower()

        active_hwnd = desktop_obs.foreground_window.hwnd if desktop_obs.foreground_window else None
        active_title = desktop_obs.foreground_window.title if desktop_obs.foreground_window else ""
        active_class = desktop_obs.foreground_window.window_class if desktop_obs.foreground_window else ""

        visible_windows = [
            {
                "hwnd": w.hwnd,
                "title": w.title,
                "class_name": w.window_class,
                "process_id": w.process_id,
                "process_name": w.process_name,
                "is_foreground": w.is_foreground,
            }
            for w in desktop_obs.visible_windows
        ]

        logger.info(
            "OBSERVE: target_app='%s', active_hwnd=%s, active_title='%s', active_class='%s', visible_count=%d",
            target_app_name, active_hwnd, active_title, active_class, len(visible_windows)
        )

        target_app_exists = False
        target_app_is_active = False

        if target_app_name:
            if self._matches_app(active_title, active_class, target_app_name):
                target_app_exists = True
                target_app_is_active = True
                logger.info("OBSERVE: Target app '%s' IS ACTIVE FOREGROUND (HWND: %s)", target_app_name, active_hwnd)
            else:
                for win in visible_windows:
                    if self._matches_app(win.get("title", ""), win.get("class_name", ""), target_app_name):
                        target_app_exists = True
                        logger.info("OBSERVE: Target app '%s' FOUND IN VISIBLE WINDOWS (HWND: %s, Title: '%s')", target_app_name, win.get("hwnd"), win.get("title"))
                        break

        # Canvas status evaluation
        canvas_status = desktop_obs.canvas_status
        if not canvas_status and objective and "draw" in str(objective.parameters.get("action_type", "")).lower():
            if target_app_is_active:
                canvas_status = "READY_FOR_DRAWING"
            elif target_app_exists:
                canvas_status = "TARGET_OPEN_NEEDS_FOCUS"
            else:
                canvas_status = "TARGET_NOT_OPEN"

        ocr_token_texts = [t.text for t in desktop_obs.ocr_tokens]

        return CurrentStateObservation(
            observation_id=desktop_obs.observation_id,
            timestamp_utc=desktop_obs.timestamp,
            active_window_hwnd=active_hwnd,
            active_window_title=active_title,
            active_window_class=active_class,
            active_process_name=desktop_obs.foreground_window.process_name if desktop_obs.foreground_window else None,
            visible_windows=visible_windows,
            target_app_exists=target_app_exists,
            target_app_is_active=target_app_is_active,
            screen_summary=desktop_obs.desktop_summary or f"Active: '{active_title}' (HWND: {active_hwnd})",
            canvas_status=canvas_status,
            ocr_tokens=ocr_token_texts,
            raw_evidence={
                "target_app_name": target_app_name,
                "visible_window_count": len(visible_windows),
                "is_consistent": desktop_obs.is_consistent,
                "consistency_warnings": desktop_obs.consistency_warnings,
                "perceived_elements_count": len(desktop_obs.perceived_elements),
            },
        )

    def _matches_app(self, title: Optional[str], class_name: Optional[str], target: str) -> bool:
        """Helper to match window title/class against target app name."""
        t_low = (title or "").lower()
        c_low = (class_name or "").lower()
        tgt_low = target.lower()

        # Ignore IDE / code editor windows that merely display file names in tabs
        if "antigravity" in t_low or "visual studio code" in t_low or "cursor" in t_low:
            return False

        if tgt_low in ("paint", "mspaint"):
            return (("paint" in t_low and not t_low.endswith(".py") and not t_low.endswith(".ts") and not t_low.endswith(".js")) 
                    or "mspaintapp" in c_low or "msppaint" in c_low)
        if tgt_low in ("notepad", "notepad.exe"):
            return "notepad" in t_low or "notepad" in c_low
        if tgt_low in ("calculator", "calc"):
            return "calculator" in t_low or "calc" in t_low
        if tgt_low in ("chrome", "google chrome"):
            return "chrome" in t_low or "chrome" in c_low

        return tgt_low in t_low or tgt_low in c_low
