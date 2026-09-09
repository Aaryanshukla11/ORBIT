"""Agent World Model representation.

Maintains live state of active windows, visible controls, known environment facts,
bounded action history, and failure diagnostic memory.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field


class ControlSummary(BaseModel):
    """Normalized summary of a visible UI control."""

    control_type: str = Field(..., description="UI control type (Button, Edit, TabItem, etc.)")
    name: str = Field(default="", description="Accessible label or control text")
    automation_id: Optional[str] = Field(default=None, description="UIA AutomationId if present")
    bounding_box: Optional[Tuple[int, int, int, int]] = Field(default=None, description="Screen (x, y, w, h)")
    is_enabled: bool = Field(default=True, description="Whether control is interactable")


class FailedSequenceRecord(BaseModel):
    """Record of a failed primitive sequence for adaptive learning and replanning."""

    sub_goal_title: str
    primitive_sequence: List[str]
    failed_at_index: int
    action_that_failed: str
    failure_reason: str
    root_cause: str
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentWorldModel(BaseModel):
    """Comprehensive, bounded world model for the ORBIT general computer agent."""

    session_id: str = Field(default_factory=lambda: f"wm_{uuid4().hex[:8]}")

    # Active Window & OS State
    active_process_name: str = Field(default="", description="Executable name of active foreground process")
    active_window_title: str = Field(default="", description="Title text of active foreground window")
    active_window_hwnd: Optional[int] = Field(default=None, description="Win32 Window Handle")
    active_window_bounds: Optional[Tuple[int, int, int, int]] = Field(default=None, description="(x, y, w, h)")
    is_desktop_locked: bool = Field(default=False, description="Whether desktop is locked / screensaver active")

    # Visible UI Context (Bounded)
    visible_windows: List[Dict[str, Any]] = Field(default_factory=list, description="Top visible window summaries")
    visible_controls: List[ControlSummary] = Field(default_factory=list, description="Top foreground interactable controls")

    # Domain & Tool State
    current_url: Optional[str] = Field(default=None, description="Active browser URL if browser is focused")
    active_document: Optional[str] = Field(default=None, description="Active document or spreadsheet path")
    clipboard_text: Optional[str] = Field(default=None, description="Current system clipboard text content")

    # Working Memory & Knowledge Facts
    known_information: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted entities, research facts, and working variables",
    )

    # Action History (Bounded to prevent context bloat)
    action_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Recent executed actions and observed outcome statuses",
    )

    # Adaptive Failure Memory (Bounded)
    failed_primitive_sequences: List[FailedSequenceRecord] = Field(
        default_factory=list,
        description="Recorded sequence failures to avoid during replanning",
    )

    # Telemetry
    last_screenshot_path: Optional[str] = None
    last_updated_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
