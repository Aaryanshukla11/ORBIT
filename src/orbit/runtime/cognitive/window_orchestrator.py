"""Native Multi-Application Window Orchestrator Subsystem.

Phase 3C (Astra 6 Modernization):
Provides cross-application window management, layout tiling, multi-monitor topology
coordination, deterministic focus switching, and inter-application clipboard pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.adapters.observation.snapshot import BoundingBox, ObservedWindow
from orbit.contracts.capabilities import WorkspaceCapability
from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType, SemanticTarget
from orbit.runtime.cognitive.models import CurrentStateObservation

logger = logging.getLogger(__name__)


class WindowLayout(str, Enum):
    """Layout arrangement patterns for multi-application workflows."""

    FULLSCREEN = "FULLSCREEN"
    SPLIT_LEFT = "SPLIT_LEFT"
    SPLIT_RIGHT = "SPLIT_RIGHT"
    SIDE_BY_SIDE = "SIDE_BY_SIDE"
    QUAD_GRID = "QUAD_GRID"


class AppWindowState(BaseModel):
    """Authoritative state for a tracked application window."""

    hwnd: int
    title: str
    class_name: str = ""
    process_name: str = ""
    bounds: BoundingBox = Field(default_factory=lambda: BoundingBox(left=0, top=0, width=800, height=600))
    is_focused: bool = False
    is_minimized: bool = False
    monitor_id: int = 0
    last_seen_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MultiAppWindowOrchestrator:
    """Orchestrates multiple application windows, tiling layouts, and cross-application data pipelines."""

    def __init__(
        self,
        workspace: Optional[WorkspaceCapability] = None,
        screen_dimensions: Tuple[int, int] = (1920, 1080),
    ) -> None:
        self.workspace = workspace
        self.screen_dimensions = screen_dimensions
        self._tracked_windows: Dict[int, AppWindowState] = {}
        self._clipboard_content: str = ""

    def update_from_observation(self, observation: CurrentStateObservation) -> None:
        """Synchronize tracked window states against live perception snapshot."""
        active_hwnd = observation.active_window_hwnd

        for win in observation.visible_windows:
            hwnd = win.get("hwnd")
            if not hwnd:
                continue

            title = win.get("title", "")
            cls_name = win.get("class_name", "")
            proc_name = win.get("process_name", "")
            raw_b = win.get("bounds", {})
            b_box = BoundingBox(
                left=raw_b.get("left", 0),
                top=raw_b.get("top", 0),
                width=raw_b.get("width", max(100, raw_b.get("right", 0) - raw_b.get("left", 0))),
                height=raw_b.get("height", max(100, raw_b.get("bottom", 0) - raw_b.get("top", 0))),
            )

            is_active = (hwnd == active_hwnd)
            self._tracked_windows[hwnd] = AppWindowState(
                hwnd=hwnd,
                title=title,
                class_name=cls_name,
                process_name=proc_name,
                bounds=b_box,
                is_focused=is_active,
                is_minimized=win.get("is_minimized", False),
            )

    def find_window_by_query(self, query: str) -> Optional[AppWindowState]:
        """Find tracked window by title substring or process name."""
        q_lower = query.strip().lower()
        # 1. Exact match on title or process
        for win in self._tracked_windows.values():
            if q_lower == win.title.lower() or q_lower == win.process_name.lower():
                return win

        # 2. Substring match
        for win in self._tracked_windows.values():
            if q_lower in win.title.lower() or q_lower in win.process_name.lower():
                return win

        return None

    def calculate_tile_geometry(
        self,
        layout: WindowLayout,
        screen_dimensions: Optional[Tuple[int, int]] = None,
    ) -> Tuple[BoundingBox, Optional[BoundingBox]]:
        """Calculate target pixel bounding boxes for tiling layouts."""
        scr_w, scr_h = screen_dimensions or self.screen_dimensions
        half_w = scr_w // 2

        if layout == WindowLayout.FULLSCREEN:
            return BoundingBox(left=0, top=0, width=scr_w, height=scr_h), None

        elif layout == WindowLayout.SPLIT_LEFT:
            return BoundingBox(left=0, top=0, width=half_w, height=scr_h), None

        elif layout == WindowLayout.SPLIT_RIGHT:
            return BoundingBox(left=half_w, top=0, width=half_w, height=scr_h), None

        elif layout == WindowLayout.SIDE_BY_SIDE:
            left_box = BoundingBox(left=0, top=0, width=half_w, height=scr_h)
            right_box = BoundingBox(left=half_w, top=0, width=half_w, height=scr_h)
            return left_box, right_box

        # Default fallback fullscreen
        return BoundingBox(left=0, top=0, width=scr_w, height=scr_h), None

    def synthesize_focus_action(self, target_window_query: str) -> Optional[AbstractAction]:
        """Synthesize a canonical FOCUS_WINDOW action for the targeted application."""
        win = self.find_window_by_query(target_window_query)
        if not win:
            logger.warning("Cannot synthesize focus action: window query '%s' not found", target_window_query)
            return None

        return AbstractAction(
            action_type=AbstractActionType.FOCUS_WINDOW,
            target=SemanticTarget(name=win.title, role="window"),
            parameters={"hwnd": win.hwnd, "application_name": win.process_name or win.title},
            expected_effect=f"Window '{win.title}' (HWND: {win.hwnd}) focused in foreground",
        )

    def set_clipboard(self, text: str) -> None:
        """Store text into orchestrator clipboard pipeline."""
        self._clipboard_content = text

    def get_clipboard(self) -> str:
        """Retrieve text from orchestrator clipboard pipeline."""
        return self._clipboard_content

    def synthesize_paste_action(self, target: Optional[SemanticTarget] = None) -> AbstractAction:
        """Synthesize a paste action using the current clipboard content."""
        return AbstractAction(
            action_type=AbstractActionType.SEND_HOTKEY,
            target=target or SemanticTarget(name="Focused Control"),
            parameters={"hotkey": "Ctrl+V", "clipboard_payload": self._clipboard_content},
            expected_effect=f"Pasted clipboard payload into target control",
        )
