"""Context Checkpointing and State Snapshot Management (Phase 2G.1).

Enables state serialization, milestone rollbacks, and long-horizon stability across 10-30+ step execution cycles.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import logging
from typing import Any, Deque, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.cognitive.models import (
    CognitiveStepResult,
    CurrentStateObservation,
    StructuredObjective,
)

logger = logging.getLogger(__name__)


class ContextCheckpoint(BaseModel):
    """Snapshot of agent reasoning state, milestones, and environment context at a discrete step."""

    checkpoint_id: str = Field(default_factory=lambda: f"chk_{uuid4().hex[:8]}", description="Unique checkpoint ID")
    step_index: int = Field(..., description="Step index when snapshot was taken")
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Snapshot timestamp")
    milestone_id: Optional[str] = Field(default=None, description="Active milestone ID if taken at boundary")
    milestone_name: Optional[str] = Field(default=None, description="Human-readable milestone label")
    is_milestone_boundary: bool = Field(default=False, description="True if captured on milestone completion")

    # Structured goals & progress
    user_goal: str = Field(..., description="Primary user goal")
    end_condition: str = Field(..., description="Target end condition")
    subgoal_statuses: Dict[str, str] = Field(default_factory=dict, description="Status mapping for subgoals")

    # Desktop state summary
    active_window_title: str = Field(default="", description="Foreground window title")
    active_window_class: str = Field(default="", description="Foreground window class name")
    visible_window_titles: List[str] = Field(default_factory=list, description="Titles of visible top-level windows")
    active_processes: List[str] = Field(default_factory=list, description="Identified active processes")

    # Compressed reasoning facts
    accumulated_summary: str = Field(default="", description="High-level narrative of achieved sub-goals")
    recent_actions_summary: str = Field(default="", description="Concise log of recent actions leading to checkpoint")
    key_facts: Dict[str, Any] = Field(default_factory=dict, description="Domain facts (e.g. file paths, typed strings)")


class CheckpointManager:
    """Manages circular ring buffer of checkpoints with automatic cadence and milestone triggers."""

    def __init__(
        self,
        max_checkpoints: int = 10,
        checkpoint_interval_steps: int = 5,
    ) -> None:
        self.max_checkpoints = max(3, max_checkpoints)
        self.checkpoint_interval_steps = max(1, checkpoint_interval_steps)
        self._checkpoints: Deque[ContextCheckpoint] = deque(maxlen=self.max_checkpoints)
        self._milestone_checkpoints: Dict[str, ContextCheckpoint] = {}
        self._last_checkpoint_step: int = -1

    @property
    def checkpoint_count(self) -> int:
        """Total active checkpoints in buffer."""
        return len(self._checkpoints)

    def should_checkpoint(self, step_index: int, is_milestone_completed: bool = False) -> bool:
        """Determine if a checkpoint should be captured at the current step."""
        if is_milestone_completed:
            return True
        if step_index <= 0:
            return False
        if self._last_checkpoint_step == -1:
            return step_index >= self.checkpoint_interval_steps
        return (step_index - self._last_checkpoint_step) >= self.checkpoint_interval_steps

    def create_checkpoint(
        self,
        step_index: int,
        objective: StructuredObjective,
        observation: Optional[CurrentStateObservation] = None,
        subgoal_statuses: Optional[Dict[str, str]] = None,
        accumulated_summary: str = "",
        recent_actions_summary: str = "",
        key_facts: Optional[Dict[str, Any]] = None,
        milestone_id: Optional[str] = None,
        milestone_name: Optional[str] = None,
        is_milestone_boundary: bool = False,
    ) -> ContextCheckpoint:
        """Capture and store a new context checkpoint."""
        active_title = ""
        active_class = ""
        vis_titles: List[str] = []
        if observation:
            active_title = observation.active_window_title or ""
            active_class = observation.active_window_class or ""
            for w in observation.visible_windows:
                title = w.get("title") if isinstance(w, dict) else getattr(w, "title", "")
                if title:
                    vis_titles.append(title)

        chk = ContextCheckpoint(
            step_index=step_index,
            milestone_id=milestone_id,
            milestone_name=milestone_name,
            is_milestone_boundary=is_milestone_boundary,
            user_goal=objective.user_goal,
            end_condition=objective.end_condition,
            subgoal_statuses=subgoal_statuses or {},
            active_window_title=active_title,
            active_window_class=active_class,
            visible_window_titles=vis_titles[:10],
            accumulated_summary=accumulated_summary,
            recent_actions_summary=recent_actions_summary,
            key_facts=key_facts or {},
        )

        self._checkpoints.append(chk)
        self._last_checkpoint_step = step_index

        if milestone_id:
            self._milestone_checkpoints[milestone_id] = chk

        logger.info(
            "Created ContextCheckpoint '%s' at Step %d (Milestone: %s, Boundary: %s)",
            chk.checkpoint_id,
            step_index,
            milestone_id or "None",
            is_milestone_boundary,
        )
        return chk

    def get_latest_checkpoint(self) -> Optional[ContextCheckpoint]:
        """Return the most recently captured checkpoint."""
        if not self._checkpoints:
            return None
        return self._checkpoints[-1]

    def get_checkpoint_by_id(self, checkpoint_id: str) -> Optional[ContextCheckpoint]:
        """Lookup checkpoint by unique ID."""
        for chk in self._checkpoints:
            if chk.checkpoint_id == checkpoint_id:
                return chk
        return None

    def get_checkpoint_by_milestone(self, milestone_id: str) -> Optional[ContextCheckpoint]:
        """Retrieve checkpoint for a specific completed milestone."""
        return self._milestone_checkpoints.get(milestone_id)

    def list_checkpoints(self) -> List[ContextCheckpoint]:
        """Return ordered list of all checkpoints currently in the buffer."""
        return list(self._checkpoints)

    def clear(self) -> None:
        """Reset checkpoint buffer."""
        self._checkpoints.clear()
        self._milestone_checkpoints.clear()
        self._last_checkpoint_step = -1
