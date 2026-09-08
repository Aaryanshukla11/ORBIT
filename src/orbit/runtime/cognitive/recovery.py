"""Safe Multi-Tier Recovery Engine for Closed-Loop Agent Execution (Step 5).

Provides targeted, budgeted, and observable recovery strategies when expected action effects
are not observed, avoiding blind keystrokes or infinite retry loops.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
import logging
import sys
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionResult,
    SemanticTarget,
)
from orbit.runtime.perception.models import DesktopObservation

if TYPE_CHECKING:
    from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective

logger = logging.getLogger(__name__)


class RecoveryStrategy(str, Enum):
    """Canonical recovery strategies for failed or unverified actions."""

    REFRESH_OBSERVATION = "REFRESH_OBSERVATION"
    WAIT_FOR_SETTLEMENT = "WAIT_FOR_SETTLEMENT"
    REFOCUS_WINDOW = "REFOCUS_WINDOW"
    RETRY_GROUNDING_ALTERNATE = "RETRY_GROUNDING_ALTERNATE"
    DISMISS_IDENTIFIED_MODAL = "DISMISS_IDENTIFIED_MODAL"
    KEYBOARD_FALLBACK = "KEYBOARD_FALLBACK"
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
    """Manages diagnosis, selection, execution, and budgeting of recovery strategies."""

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
            # Check if target window exists in visible windows but is not active foreground
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

        # 4. If action was CLICK / DOUBLE_CLICK and coordinate grounding failed
        if act_type in (AbstractActionType.CLICK, AbstractActionType.DOUBLE_CLICK, AbstractActionType.RIGHT_CLICK):
            if not exec_res.expected_effect_observed:
                return RecoveryStrategy.RETRY_GROUNDING_ALTERNATE, "Target click produced no visible state delta; retry target locator with alternate modalities."

        # 5. If typing produced no text change
        if act_type in (AbstractActionType.TYPE_TEXT, AbstractActionType.TYPE):
            if not exec_res.expected_effect_observed:
                return RecoveryStrategy.REFOCUS_WINDOW, "Typed text not observed in OCR/UIA; editor may have lost focus."

        # 6. Default to refreshing observation and re-querying model
        if self._current_transition_recoveries == 0:
            return RecoveryStrategy.WAIT_FOR_SETTLEMENT, "Initial effect not observed; wait for desktop UI to settle and refresh observation."
        return RecoveryStrategy.REQUERY_MODEL, "Prior recovery attempt incomplete; re-querying model with updated desktop context."

    async def execute_recovery(
        self,
        strategy: RecoveryStrategy,
        action: AbstractAction,
        observation: CurrentStateObservation,
        cycle_number: int = 0,
        pointer: Optional[Any] = None,
        keyboard: Optional[Any] = None,
        workspace: Optional[Any] = None,
    ) -> RecoveryRecord:
        """Execute the chosen recovery action safely against the desktop."""
        t_start = time.perf_counter()
        self._current_transition_recoveries += 1
        success = False
        details: Dict[str, Any] = {"strategy": strategy.value}

        logger.info("Executing Recovery Strategy [%s] (Attempt %d/%d) for action %s", strategy.value, self._current_transition_recoveries, self._max_recoveries_per_transition, action.action_id)

        try:
            if strategy == RecoveryStrategy.WAIT_FOR_SETTLEMENT:
                await asyncio.sleep(1.0)
                success = True
                details["settle_sleep_sec"] = 1.0

            elif strategy == RecoveryStrategy.REFRESH_OBSERVATION:
                await asyncio.sleep(0.3)
                success = True
                details["refreshed"] = True

            elif strategy == RecoveryStrategy.REFOCUS_WINDOW:
                target_app = str(action.parameters.get("application_name", action.parameters.get("app_name", action.target.name if action.target else "")))
                target_hwnd = action.parameters.get("hwnd")
                if not target_hwnd and target_app:
                    app_lower = target_app.lower()
                    for win in observation.visible_windows:
                        if app_lower in win.get("title", "").lower() or app_lower in win.get("class_name", "").lower():
                            target_hwnd = win.get("hwnd")
                            break

                if target_hwnd and sys.platform == "win32":
                    from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
                    EvidenceBasedTargetLocator._force_foreground_window(int(target_hwnd))
                    await asyncio.sleep(0.3)
                    success = True
                    details["refocused_hwnd"] = target_hwnd
                elif workspace and hasattr(workspace, "set_focus_window") and target_hwnd:
                    await workspace.set_focus_window(target_hwnd)
                    success = True
                    details["refocused_hwnd"] = target_hwnd
                else:
                    success = False
                    details["error"] = "No target HWND identified to refocus"

            elif strategy == RecoveryStrategy.DISMISS_IDENTIFIED_MODAL:
                # If an identified modal is present, send Escape or click outside
                if keyboard:
                    await keyboard.press_key("Escape")
                    await asyncio.sleep(0.3)
                    success = True
                    details["sent_key"] = "Escape"
                else:
                    success = True

            elif strategy == RecoveryStrategy.KEYBOARD_FALLBACK:
                # E.g. press Enter or Tab to confirm / advance
                if keyboard:
                    await keyboard.press_key("Return")
                    await asyncio.sleep(0.3)
                    success = True
                    details["sent_key"] = "Return"

            elif strategy == RecoveryStrategy.RETRY_GROUNDING_ALTERNATE:
                await asyncio.sleep(0.2)
                success = True
                details["alternate_grounding_ready"] = True

            elif strategy == RecoveryStrategy.REQUERY_MODEL:
                success = True
                details["requery_ready"] = True

        except Exception as ex:
            logger.warning("Recovery execution exception for %s: %s", strategy.value, ex)
            success = False
            details["error"] = str(ex)

        dur_ms = (time.perf_counter() - t_start) * 1000.0
        rec = RecoveryRecord(
            cycle_number=cycle_number,
            attempt_number=self._current_transition_recoveries,
            strategy=strategy,
            action_type=action.action_type.value,
            diagnosis=details.get("diagnosis", ""),
            recovery_success=success,
            details=details,
            duration_ms=dur_ms,
        )
        self._recovery_history.append(rec)
        return rec
