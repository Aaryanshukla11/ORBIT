"""World Model Updater.

Safely updates AgentWorldModel state across observation ticks, action dispatches,
and failure events while strictly enforcing bounded context invariants (Guardrail 11).
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from orbit.runtime.agent.contracts import AbstractAction, ActionExecutionOutcome
from orbit.runtime.world_model.model import (
    AgentWorldModel,
    ControlSummary,
    FailedSequenceRecord,
)

logger = logging.getLogger(__name__)


class WorldModelUpdater:
    """Orchestrates state transitions and enforces boundedness on AgentWorldModel."""

    MAX_ACTION_HISTORY: int = 20
    MAX_FAILED_SEQUENCES: int = 15
    MAX_VISIBLE_CONTROLS: int = 30
    MAX_VISIBLE_WINDOWS: int = 10

    @classmethod
    def update_from_observation(
        cls,
        world_model: AgentWorldModel,
        observation: Any,  # CurrentStateObservation or duck-typed dict/object
    ) -> AgentWorldModel:
        """Update world model from a fresh observation snapshot."""
        updates: Dict[str, Any] = {"last_updated_utc": datetime.now(timezone.utc)}

        # Active window extraction (direct attributes or nested active_window)
        direct_title = getattr(observation, "active_window_title", None)
        direct_proc = getattr(observation, "active_process_name", None)
        direct_hwnd = getattr(observation, "active_window_hwnd", None)

        if direct_title or direct_proc:
            updates["active_window_title"] = direct_title or ""
            updates["active_process_name"] = direct_proc or ""
            updates["active_window_hwnd"] = direct_hwnd
        else:
            active_win = getattr(observation, "active_window", None) or {}
            if isinstance(active_win, dict):
                updates["active_window_title"] = active_win.get("title") or active_win.get("window_title", "")
                updates["active_process_name"] = active_win.get("process_name") or active_win.get("app_name", "")
                updates["active_window_hwnd"] = active_win.get("hwnd")
                bounds = active_win.get("bounds") or active_win.get("bounding_box")
                if bounds:
                    updates["active_window_bounds"] = tuple(bounds) if isinstance(bounds, (list, tuple)) else None
            elif hasattr(active_win, "title"):
                updates["active_window_title"] = getattr(active_win, "title", "")
                updates["active_process_name"] = getattr(active_win, "process_name", "")
                updates["active_window_hwnd"] = getattr(active_win, "hwnd", None)

        # Visible windows (bounded)
        raw_windows = getattr(observation, "visible_windows", []) or []
        win_list = []
        for w in raw_windows[: cls.MAX_VISIBLE_WINDOWS]:
            if isinstance(w, dict):
                win_list.append({"title": w.get("title", ""), "process_name": w.get("process_name", "")})
            else:
                win_list.append({"title": getattr(w, "title", ""), "process_name": getattr(w, "process_name", "")})
        updates["visible_windows"] = win_list

        # Visible controls (bounded)
        raw_elements = getattr(observation, "ui_elements", []) or getattr(observation, "interactive_elements", []) or []
        ctrl_list: List[ControlSummary] = []
        for el in raw_elements[: cls.MAX_VISIBLE_CONTROLS]:
            if isinstance(el, dict):
                ctrl_list.append(
                    ControlSummary(
                        control_type=el.get("control_type") or el.get("role", "Unknown"),
                        name=el.get("name") or el.get("text", ""),
                        automation_id=el.get("automation_id"),
                        bounding_box=tuple(el["bbox"]) if "bbox" in el else None,
                        is_enabled=el.get("is_enabled", True),
                    )
                )
            elif hasattr(el, "control_type"):
                ctrl_list.append(
                    ControlSummary(
                        control_type=getattr(el, "control_type", "Unknown"),
                        name=getattr(el, "name", ""),
                        automation_id=getattr(el, "automation_id", None),
                        is_enabled=getattr(el, "is_enabled", True),
                    )
                )
        updates["visible_controls"] = ctrl_list

        # Screenshot path if present
        screenshot = getattr(observation, "screenshot_path", None)
        if screenshot:
            updates["last_screenshot_path"] = str(screenshot)

        return world_model.model_copy(update=updates)

    @classmethod
    def record_action_outcome(
        cls,
        world_model: AgentWorldModel,
        action: AbstractAction,
        outcome: ActionExecutionOutcome,
    ) -> AgentWorldModel:
        """Record dispatched action and observed outcome into bounded action history."""
        entry = {
            "action_id": action.action_id,
            "action_type": action.action_type.value,
            "parameters": action.parameters,
            "target": action.target.model_dump() if action.target else None,
            "dispatch_success": outcome.dispatch_success,
            "verified": outcome.verified,
            "outcome_status": outcome.outcome_status.value,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }

        # Keep strictly bounded to MAX_ACTION_HISTORY
        new_history = list(world_model.action_history) + [entry]
        if len(new_history) > cls.MAX_ACTION_HISTORY:
            new_history = new_history[-cls.MAX_ACTION_HISTORY :]

        return world_model.model_copy(
            update={
                "action_history": new_history,
                "last_updated_utc": datetime.now(timezone.utc),
            }
        )

    @classmethod
    def record_failed_sequence(
        cls,
        world_model: AgentWorldModel,
        sub_goal_title: str,
        sequence: List[str],
        failed_at_index: int,
        action_that_failed: str,
        failure_reason: str,
        root_cause: str,
    ) -> AgentWorldModel:
        """Record an unsuccessful primitive sequence to inform future replanning."""
        record = FailedSequenceRecord(
            sub_goal_title=sub_goal_title,
            primitive_sequence=sequence,
            failed_at_index=failed_at_index,
            action_that_failed=action_that_failed,
            failure_reason=failure_reason,
            root_cause=root_cause,
        )

        new_failures = list(world_model.failed_primitive_sequences) + [record]
        if len(new_failures) > cls.MAX_FAILED_SEQUENCES:
            new_failures = new_failures[-cls.MAX_FAILED_SEQUENCES :]

        return world_model.model_copy(
            update={
                "failed_primitive_sequences": new_failures,
                "last_updated_utc": datetime.now(timezone.utc),
            }
        )

    @classmethod
    def record_fact(
        cls,
        world_model: AgentWorldModel,
        key: str,
        value: Any,
    ) -> AgentWorldModel:
        """Store an extracted entity, research data, or working fact."""
        new_facts = dict(world_model.known_information)
        new_facts[key] = value
        return world_model.model_copy(
            update={
                "known_information": new_facts,
                "last_updated_utc": datetime.now(timezone.utc),
            }
        )

    @classmethod
    def record_feasibility_block(
        cls,
        world_model: AgentWorldModel,
        sub_id: str,
        reason: str,
        missing_resources: List[str],
    ) -> AgentWorldModel:
        """Record a dynamic runtime feasibility block for a sub-goal."""
        blocks = dict(world_model.known_information.get("feasibility_blocks", {}))
        blocks[sub_id] = {
            "reason": reason,
            "missing_resources": missing_resources,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        return cls.record_fact(world_model, "feasibility_blocks", blocks)
