"""Legacy Action Adapter for ORBIT.

Provides normalization of external, legacy, or deprecated action types at the system boundary.
Within the internal agent pipeline (Composer, Validator, Controller, Executor, World Model),
ONLY canonical AbstractActionType values are permitted.
"""

from __future__ import annotations

from typing import Any, Dict, Union
from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType


class LegacyActionAdapter:
    """Boundary adapter that normalizes legacy action types and payloads into canonical form."""

    _ALIAS_MAP: Dict[str, AbstractActionType] = {
        "CLICK_ELEMENT": AbstractActionType.CLICK,
        "TYPE": AbstractActionType.TYPE_TEXT,
        "HOTKEY": AbstractActionType.SEND_HOTKEY,
        "DRAW": AbstractActionType.DRAW_STROKES,
        "COMPLETE": AbstractActionType.COMPLETE_GOAL,
        "ABORT": AbstractActionType.ABORT_TASK,
        "ABORT_UNACHIEVABLE": AbstractActionType.ABORT_TASK,
        "WAIT_SETTLE": AbstractActionType.WAIT_SETTLE,
    }

    @classmethod
    def normalize_action_type(cls, raw: Union[str, AbstractActionType]) -> AbstractActionType:
        """Map a raw string or action type to the canonical AbstractActionType."""
        if isinstance(raw, AbstractActionType):
            return raw

        cleaned = str(raw).strip().upper()
        if cleaned in cls._ALIAS_MAP:
            return cls._ALIAS_MAP[cleaned]

        try:
            return AbstractActionType(cleaned)
        except ValueError:
            raise ValueError(f"Unknown action type: '{raw}'. Must be one of {[e.value for e in AbstractActionType]}")

    @classmethod
    def normalize_action(cls, action_data: Union[Dict[str, Any], AbstractAction]) -> AbstractAction:
        """Normalize raw action dictionary or object into a canonical AbstractAction."""
        if isinstance(action_data, AbstractAction):
            canonical_type = cls.normalize_action_type(action_data.action_type)
            if canonical_type != action_data.action_type:
                action_data = action_data.model_copy(update={"action_type": canonical_type})
            return action_data

        if isinstance(action_data, dict):
            raw_type = action_data.get("action_type") or action_data.get("type")
            if not raw_type:
                raise ValueError("Action data missing 'action_type' or 'type'")
            canonical_type = cls.normalize_action_type(raw_type)
            data_copy = dict(action_data)
            data_copy["action_type"] = canonical_type
            data_copy.pop("type", None)
            return AbstractAction.model_validate(data_copy)

        raise TypeError(f"Expected dict or AbstractAction, got {type(action_data)}")
