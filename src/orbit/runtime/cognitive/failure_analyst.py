"""Failure Analyst for ORBIT Closed-Loop Agent.

Guardrail 9: Failure Analyst ONLY Diagnoses.
FailureAnalyst produces a structured diagnosis.
It must NOT become another planner or directly execute recovery actions.

Flow must remain:
Failure -> FailureAnalyst -> FailureReport -> Planner / Composer -> new sequence
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    OutcomeStatus,
)
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.world_model import AgentWorldModel

logger = logging.getLogger(__name__)


class FailureCategory(str, Enum):
    """Diagnostic categorization of action failure."""

    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TARGET_OBSCURED = "TARGET_OBSCURED"
    TARGET_UNRESPONSIVE = "TARGET_UNRESPONSIVE"
    WINDOW_NOT_FOCUSED = "WINDOW_NOT_FOCUSED"
    APPLICATION_CRASHED = "APPLICATION_CRASHED"
    TEXT_ENTRY_MISMATCH = "TEXT_ENTRY_MISMATCH"
    POSTCONDITION_UNSATISFIED = "POSTCONDITION_UNSATISFIED"
    TIMEOUT = "TIMEOUT"
    ENVIRONMENT_BLOCKED = "ENVIRONMENT_BLOCKED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


class FailureReport(BaseModel):
    """Structured, non-executable diagnostic analysis of an action failure."""

    report_id: str = Field(default_factory=lambda: f"fail_{uuid4().hex[:8]}")
    action_id: str
    action_type: AbstractActionType
    category: FailureCategory
    diagnosis: str = Field(..., description="Root-cause diagnostic explanation")
    evidence_observed: List[str] = Field(default_factory=list, description="Observations and sensory cues establishing failure")
    suggested_remediation_direction: str = Field(
        default="",
        description="High-level guidance for the Planner/Composer (NEVER executable actions)",
    )
    is_transient: bool = Field(default=True, description="Whether this failure is likely transient and recoverable via alternate strategy")


class CognitiveFailureAnalyst:
    """Diagnoses action and milestone failures without planning or executing recoveries.

    Safety Invariant:
    Produces ONLY FailureReport. Never emits actions, executes commands, or alters environment.
    """

    def analyze_failure(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
        post_obs: CurrentStateObservation,
        exec_outcome: ActionExecutionOutcome,
        world_model: Optional[AgentWorldModel] = None,
    ) -> FailureReport:
        """Produce a structured diagnosis from pre/post observations and execution outcome."""
        act_type = action.action_type
        err_msg = exec_outcome.error_message or ""
        reason = exec_outcome.verification_reason or ""
        evidence: List[str] = []

        # 1. Window action failure
        if act_type in (AbstractActionType.LAUNCH_APPLICATION, AbstractActionType.FOCUS_WINDOW):
            app_name = str(
                action.parameters.get("application_name", action.parameters.get("app_name", action.target.name if action.target else ""))
            ).lower()
            if not post_obs.target_app_exists and not any(app_name in (w.get("title", "")).lower() for w in post_obs.visible_windows):
                evidence.append(f"Process/window for '{app_name}' not found in Win32 visible windows list")
                return FailureReport(
                    action_id=action.action_id,
                    action_type=act_type,
                    category=FailureCategory.TARGET_NOT_FOUND,
                    diagnosis=f"Application '{app_name}' failed to launch or open a visible window.",
                    evidence_observed=evidence,
                    suggested_remediation_direction="Verify application executable path or check system Start Menu",
                    is_transient=False,
                )
            elif not post_obs.target_app_is_active:
                evidence.append(f"Foreground window is '{post_obs.active_window_title}', expected '{app_name}'")
                return FailureReport(
                    action_id=action.action_id,
                    action_type=act_type,
                    category=FailureCategory.WINDOW_NOT_FOCUSED,
                    diagnosis=f"Application '{app_name}' is open but not in foreground focus.",
                    evidence_observed=evidence,
                    suggested_remediation_direction="Focus the existing application window via Win32 or click",
                    is_transient=True,
                )

        # 2. Text entry mismatch
        if act_type == AbstractActionType.TYPE_TEXT:
            expected_text = str(action.parameters.get("text", action.parameters.get("query", "")))
            evidence.append(f"Expected text '{expected_text}' not observed in post-action OCR or UIA buffers")
            if post_obs.active_window_title != pre_obs.active_window_title:
                evidence.append(f"Active window shifted during typing from '{pre_obs.active_window_title}' to '{post_obs.active_window_title}'")
                return FailureReport(
                    action_id=action.action_id,
                    action_type=act_type,
                    category=FailureCategory.WINDOW_NOT_FOCUSED,
                    diagnosis="Active window lost focus during text entry attempt.",
                    evidence_observed=evidence,
                    suggested_remediation_direction="Re-focus input field and retry typing",
                    is_transient=True,
                )
            return FailureReport(
                action_id=action.action_id,
                action_type=act_type,
                category=FailureCategory.TEXT_ENTRY_MISMATCH,
                diagnosis=f"Typed text '{expected_text}' was not accepted or rendered by target control.",
                evidence_observed=evidence,
                suggested_remediation_direction="Try clipboard atomic injection or click to focus input control first",
                is_transient=True,
            )

        # 3. Pointer click failure
        if act_type in (AbstractActionType.CLICK, AbstractActionType.DOUBLE_CLICK, AbstractActionType.RIGHT_CLICK):
            evidence.append(f"No observable desktop state delta detected after clicking target '{action.target.name if action.target else 'unnamed'}'")
            return FailureReport(
                action_id=action.action_id,
                action_type=act_type,
                category=FailureCategory.TARGET_UNRESPONSIVE,
                diagnosis=f"Click on '{action.target.name if action.target else 'target'}' produced no observable UI state change.",
                evidence_observed=evidence,
                suggested_remediation_direction="Re-ground target coordinates with visual verification or retry with settle pause",
                is_transient=True,
            )

        # 4. General postcondition failure
        evidence.append(f"Verification reason: {reason or err_msg or 'Postcondition contract unsatisfied'}")
        return FailureReport(
            action_id=action.action_id,
            action_type=act_type,
            category=FailureCategory.POSTCONDITION_UNSATISFIED,
            diagnosis=f"Action postcondition was not verified: {reason or err_msg or 'state unchanged'}",
            evidence_observed=evidence,
            suggested_remediation_direction="Re-evaluate observation and compose alternative action sequence",
            is_transient=True,
        )
