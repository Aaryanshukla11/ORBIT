"""Advanced Self-Correction & Reflection Subagent.

Phase 3F (Astra 6 Modernization):
Provides autonomous failure diagnosis, root-cause attribution, checkpoint backtracking,
and alternate hypothesis generation when standard recovery cycles fail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType, SemanticTarget
from orbit.runtime.cognitive.context_checkpoint import ContextCheckpoint
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CognitiveStepResult,
    CurrentStateObservation,
    StructuredObjective,
)

logger = logging.getLogger(__name__)


class FailureRootCause(str, Enum):
    """Categorized root causes of complex execution failures."""

    TARGET_NOT_LOCATED = "TARGET_NOT_LOCATED"
    UNRESPONSIVE_UI = "UNRESPONSIVE_UI"
    UNEXPECTED_MODAL = "UNEXPECTED_MODAL"
    STATE_STALENESS = "STATE_STALENESS"
    INCORRECT_STRATEGY = "INCORRECT_STRATEGY"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNKNOWN = "UNKNOWN"


class CorrectionPlan(BaseModel):
    """A synthesized recovery plan containing root-cause analysis, backtrack target, and alternate actions."""

    plan_id: str = Field(default_factory=lambda: f"corr_{uuid4().hex[:8]}")
    root_cause: FailureRootCause
    root_cause_explanation: str
    target_checkpoint_id: Optional[str] = None
    backtrack_actions: List[AbstractAction] = Field(default_factory=list)
    alternate_actions: List[AbstractAction] = Field(default_factory=list)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SelfCorrectionReflectionEngine:
    """Reflective reasoning subagent that diagnoses failure cascades and synthesizes backtracking strategies."""

    def __init__(self, max_hypotheses: int = 3) -> None:
        self.max_hypotheses = max_hypotheses

    def diagnose_and_reflect(
        self,
        objective: StructuredObjective,
        failed_step: CognitiveStepResult,
        step_history: List[CognitiveStepResult],
        current_observation: CurrentStateObservation,
        available_checkpoints: Optional[List[ContextCheckpoint]] = None,
    ) -> CorrectionPlan:
        """Perform deep reflection on step history and sensory evidence to formulate a correction plan."""
        failed_act = failed_step.action_dispatched
        exec_res = failed_step.execution_result
        err_msg = (exec_res.error_message if exec_res else "") or ""

        root_cause = FailureRootCause.UNKNOWN
        explanation = ""

        # 1. Check for modal dialog interruption
        win_classes = {w.get("class_name", "") for w in current_observation.visible_windows}
        if "#32770" in win_classes or "dialog" in (current_observation.active_window_title or "").lower():
            root_cause = FailureRootCause.UNEXPECTED_MODAL
            explanation = f"Active window '{current_observation.active_window_title}' is an unexpected modal dialog blocking interaction."

        # 2. Check for target location failure
        elif "target not found" in err_msg.lower() or "grounding failed" in err_msg.lower():
            root_cause = FailureRootCause.TARGET_NOT_LOCATED
            explanation = f"Target '{failed_act.target.name if failed_act and failed_act.target else ''}' could not be located in observation."

        # 3. Check for unresponsive UI / unobserved effect
        elif exec_res and not exec_res.expected_effect_observed:
            root_cause = FailureRootCause.UNRESPONSIVE_UI
            explanation = f"Action dispatched successfully, but expected effect '{failed_act.expected_effect if failed_act else ''}' was not observed."

        # 4. Check for state staleness
        elif current_observation.target_app_exists and not current_observation.target_app_is_active:
            root_cause = FailureRootCause.STATE_STALENESS
            explanation = "Target application is running but lost foreground focus."

        # Select latest healthy checkpoint if available
        target_ckpt_id: Optional[str] = None
        if available_checkpoints:
            target_ckpt_id = available_checkpoints[-1].checkpoint_id

        # Synthesize backtrack actions
        backtrack_acts = self._synthesize_backtrack(root_cause, current_observation)

        # Synthesize alternate hypotheses
        alt_acts = self._synthesize_alternates(root_cause, failed_act, current_observation)

        return CorrectionPlan(
            root_cause=root_cause,
            root_cause_explanation=explanation,
            target_checkpoint_id=target_ckpt_id,
            backtrack_actions=backtrack_acts,
            alternate_actions=alt_acts,
            confidence=0.90,
        )

    def _synthesize_backtrack(
        self,
        root_cause: FailureRootCause,
        observation: CurrentStateObservation,
    ) -> List[AbstractAction]:
        """Synthesize immediate cleanup/backtrack actions before retrying."""
        if root_cause == FailureRootCause.UNEXPECTED_MODAL:
            return [
                AbstractAction(
                    action_type=AbstractActionType.SEND_HOTKEY,
                    parameters={"hotkey": "Escape"},
                    expected_effect="Dismissed unexpected modal dialog via Escape",
                )
            ]
        elif root_cause == FailureRootCause.STATE_STALENESS and observation.active_window_hwnd:
            return [
                AbstractAction(
                    action_type=AbstractActionType.FOCUS_WINDOW,
                    parameters={"hwnd": observation.active_window_hwnd},
                    expected_effect="Refocused target window",
                )
            ]
        return []

    def _synthesize_alternates(
        self,
        root_cause: FailureRootCause,
        failed_action: Optional[AbstractAction],
        observation: CurrentStateObservation,
    ) -> List[AbstractAction]:
        """Formulate alternate actionable hypotheses."""
        if not failed_action:
            return []

        alternates: List[AbstractAction] = []

        # If GUI Click failed, propose keyboard shortcut or alternate mark
        if failed_action.action_type == AbstractActionType.CLICK:
            t_name = (failed_action.target.name if failed_action.target else "").lower()
            if "save" in t_name:
                alternates.append(
                    AbstractAction(
                        action_type=AbstractActionType.SEND_HOTKEY,
                        parameters={"hotkey": "Ctrl+S"},
                        expected_effect="Save document via keyboard shortcut",
                    )
                )
            elif "copy" in t_name:
                alternates.append(
                    AbstractAction(
                        action_type=AbstractActionType.SEND_HOTKEY,
                        parameters={"hotkey": "Ctrl+C"},
                        expected_effect="Copy via keyboard shortcut",
                    )
                )
            elif "paste" in t_name:
                alternates.append(
                    AbstractAction(
                        action_type=AbstractActionType.SEND_HOTKEY,
                        parameters={"hotkey": "Ctrl+V"},
                        expected_effect="Paste via keyboard shortcut",
                    )
                )

        # Propose UI wait / settle fallback
        alternates.append(
            AbstractAction(
                action_type=AbstractActionType.WAIT,
                parameters={"duration": 1.0},
                expected_effect="Allow UI to settle before retrying",
            )
        )

        return alternates[: self.max_hypotheses]
