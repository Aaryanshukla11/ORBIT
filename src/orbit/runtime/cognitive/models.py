"""Domain contracts and data models for the Cognitive Intent & Decision Engine subsystem.

Re-exports strict agent action protocol, outcome contracts, and coordinate boundaries
from orbit.runtime.agent.contracts for unified AI-native execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator

from orbit.runtime.agent.contracts import (
    AbortTaskParams,
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionExecutionResult,
    ActionOutcomeContract,
    ActionType,
    ActionValidationFailureCode,
    ActionValidationResult,
    AgentAction,
    AgentActionValidator,
    ClickParams,
    CompleteGoalParams,
    DoubleClickParams,
    DragParams,
    DrawStrokesParams,
    ExpectedState,
    FocusWindowParams,
    LaunchApplicationParams,
    OutcomeStatus,
    ResolvedAction,
    RightClickParams,
    ScrollParams,
    SelectOptionParams,
    SemanticTarget,
    SendHotkeyParams,
    TypeTextParams,
    VerificationStrategy,
    WaitParams,
)
from orbit.runtime.perception.models import DesktopObservation
from orbit.runtime.task_completion.models import TaskCompletionStatus


class StructuredObjective(BaseModel):
    """Structured, epistemically grounded representation of user intent."""

    objective_id: str = Field(default_factory=lambda: f"obj_{uuid4().hex[:8]}", description="Unique objective identifier")
    raw_prompt: str = Field(..., description="Original user prompt verbatim")
    user_goal: str = Field(..., description="High-level summarized goal statement")
    end_condition: str = Field(..., description="Verifiable end state criteria (e.g. canvas_has_cube_drawing, notepad_contains_text)")
    target_entities: List[str] = Field(default_factory=list, description="Target applications, controls, files, or geometric shapes")
    constraints: List[str] = Field(default_factory=list, description="Negative or positive constraints and boundaries")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Extracted parameters (e.g. shape, text, app name)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of interpretation")


class CurrentStateObservation(BaseModel):
    """Immutable snapshot of the live desktop state observed by the perception layer."""

    observation_id: str = Field(default_factory=lambda: f"obs_{uuid4().hex[:8]}", description="Unique observation identifier")
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of observation")
    active_window_hwnd: Optional[int] = Field(default=None, description="HWND of foreground active window")
    active_window_title: Optional[str] = Field(default=None, description="Title of foreground active window")
    active_window_class: Optional[str] = Field(default=None, description="Win32 class name of active window")
    active_process_name: Optional[str] = Field(default=None, description="Process executable name of active window")
    visible_windows: List[Dict[str, Any]] = Field(default_factory=list, description="List of visible top-level windows")
    target_app_exists: bool = Field(default=False, description="Whether target application is currently running/open")
    target_app_is_active: bool = Field(default=False, description="Whether target application is the active foreground window")
    screen_summary: str = Field(default="", description="High-level text or perceptual summary of the screen")
    canvas_status: Optional[str] = Field(default=None, description="Status of target canvas if applicable: BLANK, NON_BLANK, UNKNOWN")
    ocr_tokens: List[str] = Field(default_factory=list, description="OCR text tokens recognized on screen")
    raw_evidence: Dict[str, Any] = Field(default_factory=dict, description="Raw sensory and accessibility telemetry")

    # Authoritative Canonical DesktopObservation snapshot & modality telemetry
    desktop_observation: Optional[DesktopObservation] = Field(default=None, description="Underlying canonical multimodal DesktopObservation")
    uia_status: Optional[str] = Field(default=None, description="UIA status: SUCCESS, EMPTY, UNAVAILABLE, FAILED")
    ocr_status: Optional[str] = Field(default=None, description="OCR status: SUCCESS, EMPTY, UNAVAILABLE, FAILED")
    screenshot_status: Optional[str] = Field(default=None, description="Screenshot status: SUCCESS, FALLBACK, FAILED")
    perceived_elements_count: int = Field(default=0, description="Count of fused semantic elements in perception snapshot")


class CognitiveDecision(BaseModel):
    """Output of a single reasoning cycle in the Cognitive Decision Engine.

    Stores structured, auditable decision fields without free-form unrestricted chain-of-thought.
    """

    decision_id: str = Field(default_factory=lambda: f"dec_{uuid4().hex[:8]}", description="Unique decision identifier")
    step_index: int = Field(default=0, description="0-indexed step iteration in the cognitive loop")
    decision_summary: str = Field(..., description="Auditable assessment of current state vs objective")
    decision_confidence: float = Field(default=1.0, description="Confidence in decision (0.0 to 1.0)")
    evidence_used: List[str] = Field(default_factory=list, description="Concrete observations used to make decision")
    expected_state_transition: str = Field(default="", description="Expected state transition resulting from this decision")
    reason_summary: str = Field(default="", description="Concise justification for the action")
    is_goal_satisfied: bool = Field(default=False, description="Whether current state satisfies objective end condition")
    escalated_to_llm: bool = Field(default=False, description="Whether this decision required LLM escalation")
    next_action: Optional[AbstractAction] = Field(default=None, description="The abstract action to execute next, or None if satisfied")


class ExecutionBudget(BaseModel):
    """Progress-based execution budget preventing infinite loops and tracking meaningful state change."""

    max_total_actions: int = Field(default=50, description="Hard upper bound on total actions dispatched")
    max_repeated_actions_without_progress: int = Field(default=3, description="Max consecutive identical actions without state progress")
    max_recoveries_per_transition: int = Field(default=2, description="Max recovery attempts for a single state transition")
    max_llm_escalations: int = Field(default=5, description="Max times LLM can be invoked for decision escalation")
    no_progress_timeout_sec: float = Field(default=30.0, description="Timeout if no forward state progress is made")


class CognitiveStepResult(BaseModel):
    """Audit record of an executed cognitive loop iteration."""

    step_index: int = Field(..., description="Iteration number")
    decision: CognitiveDecision = Field(..., description="Cognitive decision made in this step")
    action_dispatched: Optional[AbstractAction] = Field(default=None, description="Action sent to executor")
    execution_result: Optional[ActionExecutionResult] = Field(default=None, description="Immediate action execution and outcome verification")
    post_observation: Optional[CurrentStateObservation] = Field(default=None, description="State observed after action execution")
    state_progress_detected: bool = Field(default=False, description="Whether this step moved the system state closer to the goal")
    duration_ms: float = Field(default=0.0, description="Execution duration of this step in milliseconds")

    @property
    def action_success(self) -> bool:
        return bool(self.execution_result and self.execution_result.dispatch_success)

    @property
    def outcome_verified(self) -> bool:
        return bool(self.execution_result and self.execution_result.expected_effect_observed)


class CognitiveExecutionResult(BaseModel):
    """End-to-end outcome of a cognitive execution loop run."""

    task_id: str = Field(..., description="Task identifier")
    objective: StructuredObjective = Field(..., description="Structured objective that guided execution")
    is_success: bool = Field(default=False, description="Whether the task objective was successfully satisfied and verified")
    total_steps: int = Field(default=0, description="Total cognitive iterations executed")
    step_history: List[CognitiveStepResult] = Field(default_factory=list, description="Chronological record of every step")
    final_status: TaskCompletionStatus = Field(default=TaskCompletionStatus.FAILED, description="Terminal task status")
    failure_reason: Optional[str] = Field(default=None, description="Explanation of failure if not successful")
    failure_code: Optional[str] = Field(default=None, description="Error code if failed")
    elapsed_duration_ms: float = Field(default=0.0, description="Total wall-clock duration in milliseconds")


__all__ = [
    # Core contracts re-exported
    "AbortTaskParams",
    "AbstractAction",
    "AbstractActionType",
    "ActionExecutionOutcome",
    "ActionExecutionResult",
    "ActionOutcomeContract",
    "ActionType",
    "ActionValidationFailureCode",
    "ActionValidationResult",
    "AgentAction",
    "AgentActionValidator",
    "ClickParams",
    "CognitiveDecision",
    "CognitiveExecutionResult",
    "CognitiveStepResult",
    "CompleteGoalParams",
    "CurrentStateObservation",
    "DoubleClickParams",
    "DragParams",
    "DrawStrokesParams",
    "ExecutionBudget",
    "ExpectedState",
    "FocusWindowParams",
    "LaunchApplicationParams",
    "OutcomeStatus",
    "ResolvedAction",
    "RightClickParams",
    "ScrollParams",
    "SelectOptionParams",
    "SemanticTarget",
    "SendHotkeyParams",
    "StructuredObjective",
    "TypeTextParams",
    "VerificationStrategy",
    "WaitParams",
]
