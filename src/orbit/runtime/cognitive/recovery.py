"""Safe Multi-Tier Recovery Engine for Closed-Loop Agent Execution (Step 5).

Provides targeted, budgeted, and observable recovery strategies when expected action effects
are not observed, synthesizing canonical primitives for controller execution.
RecoveryStrategy != Primitive. All physical actions are executed via PrimitiveExecutionController.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionResult,
)

if TYPE_CHECKING:
    from orbit.runtime.cognitive.models import CurrentStateObservation

logger = logging.getLogger(__name__)


class RecoveryStrategy(str, Enum):
    """Internal diagnostic recovery strategies for failed or unverified actions.

    RecoveryStrategy != Primitive. A recovery strategy is a diagnostic assessment
    that synthesizes a canonical primitive (e.g. FOCUS_WINDOW, SEND_HOTKEY, WAIT).
    """

    REFRESH_OBSERVATION = "REFRESH_OBSERVATION"
    WAIT_FOR_SETTLEMENT = "WAIT_FOR_SETTLEMENT"
    REFOCUS_WINDOW = "REFOCUS_WINDOW"
    RETRY_GROUNDING_ALTERNATE = "RETRY_GROUNDING_ALTERNATE"
    DISMISS_IDENTIFIED_MODAL = "DISMISS_IDENTIFIED_MODAL"
    REQUERY_MODEL = "REQUERY_MODEL"


class RecoveryRecord(BaseModel):
    """Audit record of an executed recovery attempt."""

    recovery_id: str = Field(default_factory=lambda: f"rec_{uuid4().hex[:8]}")
    cycle_number: int = 0
    attempt_number: int = 1
    strategy: RecoveryStrategy
    action_type: str = "UNKNOWN"
    diagnosis: str = ""
    recovery_success: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentRecoveryManager:
    """Manages diagnosis, selection, and primitive synthesis for recovery.

    Enforces:
    1. Zero raw adapter access: Does not accept pointer, keyboard, or workspace.
    2. RecoveryStrategy != Primitive: Synthesizes strictly canonical AbstractAction instances.
    3. No blind Return keypresses: Only synthesizes Escape when modal evidence is verified.
    """

    def __init__(self, max_recoveries_per_transition: int = 2) -> None:
        self._max_recoveries_per_transition = max_recoveries_per_transition
        self._recovery_history: List[RecoveryRecord] = []
        self._current_transition_recoveries = 0

    @property
    def max_recoveries(self) -> int:
        return self._max_recoveries_per_transition

    @property
    def current_transition_recoveries(self) -> int:
        return self._current_transition_recoveries

    def reset_transition_counter(self) -> None:
        """Reset the per-transition recovery counter when a new state transition succeeds."""
        self._current_transition_recoveries = 0

    def get_history(self) -> List[RecoveryRecord]:
        return list(self._recovery_history)

    def can_attempt_recovery(self) -> bool:
        """Check whether recovery budget for the current state transition is available."""
        return self._current_transition_recoveries < self._max_recoveries_per_transition

    def diagnose_failure(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
        post_obs: CurrentStateObservation,
        exec_res: ActionExecutionResult,
    ) -> Tuple[RecoveryStrategy, str]:
        """Analyze live observations to determine the most targeted recovery strategy."""
        act_type = action.action_type
        params = action.parameters

        # 1. Target application / window exists but lost focus
        target_app = str(params.get("application_name", params.get("app_name", action.target.name if action.target else "")))
        if target_app:
            app_lower = target_app.lower()
            for win in post_obs.visible_windows:
                title_lower = win.get("title", "").lower()
                class_lower = win.get("class_name", "").lower()
                if (app_lower in title_lower or app_lower in class_lower) and win.get("hwnd") != post_obs.active_window_hwnd:
                    return RecoveryStrategy.REFOCUS_WINDOW, f"Target window '{win.get('title')}' is visible but not focused (active HWND={post_obs.active_window_hwnd})."

        # 2. Check for unexpected blocking modal dialogs
        if post_obs.visible_windows:
            for win in post_obs.visible_windows:
                title = win.get("title", "")
                if any(kw in title.lower() for kw in ("save changes", "confirm", "warning", "error", "dialog", "alert", "unsaved")):
                    return RecoveryStrategy.DISMISS_IDENTIFIED_MODAL, f"Unexpected modal dialog detected: '{title}'"

        # 3. If action was LAUNCH_APPLICATION and target app not yet visible, UI settlement may be delayed
        if act_type == AbstractActionType.LAUNCH_APPLICATION:
            if not post_obs.target_app_exists:
                return RecoveryStrategy.WAIT_FOR_SETTLEMENT, "Application process launched but main window not yet rendered in perception snapshot."

        # 4. If action was CLICK / DOUBLE_CLICK and effect was not observed
        if act_type in (AbstractActionType.CLICK, AbstractActionType.DOUBLE_CLICK, AbstractActionType.RIGHT_CLICK):
            if not exec_res.expected_effect_observed:
                return RecoveryStrategy.RETRY_GROUNDING_ALTERNATE, "Target click produced no visible state delta; retry target locator with alternate modalities."

        # 5. If typing produced no text change
        if act_type == AbstractActionType.TYPE_TEXT:
            if not exec_res.expected_effect_observed:
                return RecoveryStrategy.REFOCUS_WINDOW, "Typed text not observed in OCR/UIA; editor may have lost focus."

        # 6. Default to refreshing observation and re-querying model
        if self._current_transition_recoveries == 0:
            return RecoveryStrategy.WAIT_FOR_SETTLEMENT, "Initial effect not observed; wait for desktop UI to settle and refresh observation."
        return RecoveryStrategy.REQUERY_MODEL, "Prior recovery attempt incomplete; re-querying model with updated desktop context."

    def synthesize_recovery_primitive(
        self,
        strategy: RecoveryStrategy,
        action: AbstractAction,
        observation: CurrentStateObservation,
    ) -> Optional[AbstractAction]:
        """Synthesize a canonical primitive action to execute the diagnosed recovery strategy.

        Enforces:
        - Output is STRICTLY an existing canonical AbstractAction (FOCUS_WINDOW, SEND_HOTKEY, WAIT).
        - No blind Return keypresses: KEYBOARD_FALLBACK is eliminated.
        - Escape is synthesized ONLY when modal dialog evidence is present in visible windows.
        """
        if strategy == RecoveryStrategy.REFOCUS_WINDOW:
            target_app = str(action.parameters.get("application_name", action.parameters.get("app_name", action.target.name if action.target else "")))
            target_hwnd = action.parameters.get("hwnd")
            if not target_hwnd and target_app:
                app_lower = target_app.lower()
                for win in observation.visible_windows:
                    if app_lower in win.get("title", "").lower() or app_lower in win.get("class_name", "").lower():
                        target_hwnd = win.get("hwnd")
                        break

            if target_hwnd:
                return AbstractAction(
                    action_type=AbstractActionType.FOCUS_WINDOW,
                    parameters={"hwnd": target_hwnd, "application_name": target_app},
                    expected_effect=f"Window {target_hwnd} brought to active foreground",
                )
            return None

        elif strategy == RecoveryStrategy.DISMISS_IDENTIFIED_MODAL:
            # Enforce evidence requirement: only synthesize Escape if a dismissible modal was detected
            has_modal_evidence = False
            for win in observation.visible_windows:
                title = str(win.get("title", "")).lower()
                if any(kw in title for kw in ("save changes", "confirm", "warning", "error", "dialog", "alert", "unsaved")):
                    has_modal_evidence = True
                    break

            if has_modal_evidence:
                return AbstractAction(
                    action_type=AbstractActionType.SEND_HOTKEY,
                    parameters={"hotkey": "Escape"},
                    expected_effect="Modal dialog dismissed via Escape key",
                )
            # No confirmed modal evidence -> do NOT blindly send keystrokes; return None to replan
            logger.info("[AgentRecoveryManager] Modal dismissal skipped: no active modal dialog evidence confirmed.")
            return None

        elif strategy == RecoveryStrategy.WAIT_FOR_SETTLEMENT:
            return AbstractAction(
                action_type=AbstractActionType.WAIT,
                parameters={"duration": 1.0},
                expected_effect="Desktop UI settled after 1.0s wait",
            )

        # Strategies like REFRESH_OBSERVATION, RETRY_GROUNDING_ALTERNATE, REQUERY_MODEL
        # do not require environment-changing physical actions; they guide cognitive replanning.
        return None

    def record_recovery(
        self,
        cycle_number: int,
        strategy: RecoveryStrategy,
        action: AbstractAction,
        diagnosis: str,
        recovery_success: bool,
        details: Dict[str, Any],
        duration_ms: float = 0.0,
    ) -> RecoveryRecord:
        """Record an executed recovery attempt into the audit log."""
        self._current_transition_recoveries += 1
        rec = RecoveryRecord(
            cycle_number=cycle_number,
            attempt_number=self._current_transition_recoveries,
            strategy=strategy,
            action_type=action.action_type.value,
            diagnosis=diagnosis,
            recovery_success=recovery_success,
            details=details,
            duration_ms=duration_ms,
        )
        self._recovery_history.append(rec)
        return rec

    async def execute_recovery(
        self,
        strategy: RecoveryStrategy,
        action: AbstractAction,
        observation: CurrentStateObservation,
        cycle_number: int = 0,
    ) -> RecoveryRecord:
        """Compatibility method for legacy callers; returns a recorded RecoveryRecord."""
        recovery_action = self.synthesize_recovery_primitive(strategy, action, observation)
        rec = self.record_recovery(
            cycle_number=cycle_number,
            strategy=strategy,
            action=action,
            diagnosis=f"Recovery strategy {strategy.value}",
            recovery_success=True,
            details={"synthesized_action": recovery_action.action_id if recovery_action else None},
        )
        return rec

