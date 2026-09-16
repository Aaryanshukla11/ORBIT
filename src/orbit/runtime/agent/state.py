"""Agent State Manager and Persistent Task Memory (Milestone M2.0).

Maintains persistent task memory, structured state snapshots, action history,
working variables, and cached environment knowledge across execution steps.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import ActionExecutionOutcome, AgentAction

logger = logging.getLogger(__name__)


class DesktopStateSnapshot(BaseModel):
    """Immutable snapshot of the live desktop state observed at a discrete moment."""

    snapshot_id: str = Field(default_factory=lambda: f"snp_{uuid4().hex[:8]}", description="Unique snapshot ID")
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp")
    active_window_hwnd: Optional[int] = Field(default=None, description="Foreground active window handle")
    active_window_title: Optional[str] = Field(default=None, description="Foreground active window title")
    active_window_class: Optional[str] = Field(default=None, description="Foreground active window Win32 class")
    active_process_name: Optional[str] = Field(default=None, description="Foreground executable name")
    visible_windows: List[Dict[str, Any]] = Field(default_factory=list, description="List of visible top-level windows")
    target_app_exists: bool = Field(default=False, description="Whether target application is open")
    target_app_is_active: bool = Field(default=False, description="Whether target application is foreground active")
    canvas_status: Optional[str] = Field(default=None, description="Canvas state e.g. BLANK, NON_BLANK, TARGET_NOT_OPEN")
    screen_summary: str = Field(default="", description="High-level text description of the screen")
    ocr_tokens: List[str] = Field(default_factory=list, description="Extracted OCR text tokens on screen")
    uia_elements: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted UI Automation accessibility elements")
    raw_evidence: Dict[str, Any] = Field(default_factory=dict, description="Raw perceptual and diagnostic telemetry")


class AgentStepRecord(BaseModel):
    """Historical audit record of an individual step execution."""

    step_index: int = Field(..., description="0-indexed step iteration")
    action: AgentAction = Field(..., description="Dispatched agent action")
    outcome: ActionExecutionOutcome = Field(..., description="Observed outcome and verification result")
    pre_snapshot_id: str = Field(..., description="Snapshot ID prior to action")
    post_snapshot_id: str = Field(..., description="Snapshot ID after action execution")
    duration_ms: float = Field(default=0.0, description="Step duration in milliseconds")
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskMemory(BaseModel):
    """Persistent task memory preserved across entire execution lifecycle."""

    task_id: str = Field(..., description="Unique task identifier")
    goal: str = Field(..., description="Original goal prompt")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Persistent key-value variables")
    discovered_windows: Dict[str, int] = Field(default_factory=dict, description="Cached window handles: app_name -> hwnd")
    discovered_elements: Dict[str, Any] = Field(default_factory=dict, description="Cached UI element locations")
    notes: List[str] = Field(default_factory=list, description="Agent scratchpad notes and milestones")
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentStateManager:
    """Central manager for active agent state, working memory, and snapshot history."""

    def __init__(
        self,
        task_id: str = "default_task",
        goal: str = "",
        max_snapshots: int = 50,
    ) -> None:
        self._memory = TaskMemory(task_id=task_id, goal=goal)
        self._snapshots: List[DesktopStateSnapshot] = []
        self._step_records: List[AgentStepRecord] = []
        self._max_snapshots = max_snapshots

    @property
    def task_id(self) -> str:
        return self._memory.task_id

    @property
    def goal(self) -> str:
        return self._memory.goal

    @property
    def memory(self) -> TaskMemory:
        return self._memory

    def record_snapshot(self, snapshot: DesktopStateSnapshot) -> None:
        """Store a newly observed desktop snapshot."""
        self._snapshots.append(snapshot)
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots = self._snapshots[-self._max_snapshots:]

    def get_latest_snapshot(self) -> Optional[DesktopStateSnapshot]:
        """Return the most recent desktop state snapshot, or None."""
        return self._snapshots[-1] if self._snapshots else None

    def get_snapshot_history(self, limit: int = 10) -> List[DesktopStateSnapshot]:
        """Return the N most recent desktop state snapshots."""
        return self._snapshots[-limit:]

    def record_step(
        self,
        step_index: int,
        action: AgentAction,
        outcome: ActionExecutionOutcome,
        pre_snapshot: DesktopStateSnapshot,
        post_snapshot: DesktopStateSnapshot,
        duration_ms: float = 0.0,
    ) -> None:
        """Record an executed step in the audit trail."""
        self.record_snapshot(pre_snapshot)
        self.record_snapshot(post_snapshot)

        rec = AgentStepRecord(
            step_index=step_index,
            action=action,
            outcome=outcome,
            pre_snapshot_id=pre_snapshot.snapshot_id,
            post_snapshot_id=post_snapshot.snapshot_id,
            duration_ms=duration_ms,
        )
        self._step_records.append(rec)
        self._memory.updated_at_utc = datetime.now(timezone.utc)

    def get_step_history(self, limit: int = 50) -> List[AgentStepRecord]:
        """Return recorded step execution history."""
        return self._step_records[-limit:]

    def set_variable(self, key: str, value: Any) -> None:
        """Store a persistent variable in task memory."""
        self._memory.variables[key] = value
        self._memory.updated_at_utc = datetime.now(timezone.utc)

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Retrieve a persistent variable from task memory."""
        return self._memory.variables.get(key, default)

    def cache_window(self, app_name: str, hwnd: int) -> None:
        """Cache discovered HWND for an application."""
        self._memory.discovered_windows[app_name.lower().strip()] = hwnd
        self._memory.updated_at_utc = datetime.now(timezone.utc)

    def get_cached_window(self, app_name: str) -> Optional[int]:
        """Retrieve cached HWND for an application."""
        return self._memory.discovered_windows.get(app_name.lower().strip())

    def add_note(self, note: str) -> None:
        """Append an observation or milestone note to task memory."""
        self._memory.notes.append(note)
        self._memory.updated_at_utc = datetime.now(timezone.utc)

    def get_summary(self) -> Dict[str, Any]:
        """Return a structured summary of agent memory and execution status."""
        latest = self.get_latest_snapshot()
        return {
            "task_id": self._memory.task_id,
            "goal": self._memory.goal,
            "total_steps": len(self._step_records),
            "variables_count": len(self._memory.variables),
            "discovered_windows": dict(self._memory.discovered_windows),
            "notes_count": len(self._memory.notes),
            "latest_active_window": latest.active_window_title if latest else None,
            "latest_active_hwnd": latest.active_window_hwnd if latest else None,
            "created_at_utc": self._memory.created_at_utc.isoformat(),
            "updated_at_utc": self._memory.updated_at_utc.isoformat(),
        }
