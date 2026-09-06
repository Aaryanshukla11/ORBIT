"""Domain contracts and data models for ORBIT Task Completion Verification Subsystem (M1.8 Step 5).

Key architectural invariant:
Distinguish STEP_SUCCEEDED from TASK_COMPLETED.
A workflow is not successful merely because low-level actions returned;
the final user objective must be independently verified using fresh multimodal observation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.plan_execution.models import PlanExecutionResult
from orbit.runtime.planning.models import ExecutableTaskPlan
from orbit.runtime.task_understanding.models import TaskUnderstandingResult


class TaskCompletionStatus(str, Enum):
    """Epistemic status of end-to-end task completion."""

    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    UNVERIFIABLE = "UNVERIFIABLE"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"


class TaskCompletionEvidence(BaseModel):
    """Structured, audit-grade evidence backing final goal completion verification."""

    final_generation_id: int = Field(default=0, description="Desktop topology generation of final observation")
    observation_id: Optional[str] = Field(default=None, description="Snapshot identifier of final observation")
    application_name: Optional[str] = Field(default=None, description="Target application name")
    application_hwnd: Optional[int] = Field(default=None, description="Target application window handle")
    application_is_open: bool = Field(default=False, description="Whether target application window exists")
    application_in_foreground: bool = Field(default=False, description="Whether target application is foreground")
    verified_text: Optional[str] = Field(default=None, description="Expected text content that was verified")
    ocr_matched_text: Optional[str] = Field(default=None, description="Verbatim text extracted via fresh OCR scan")
    ocr_confidence: Optional[float] = Field(default=None, description="OCR match confidence score [0.0..1.0]")
    ocr_regions_count: int = Field(default=0, description="Number of matching OCR text regions found")
    visual_changes_detected: List[str] = Field(default_factory=list, description="Visual diffs or UI state transitions detected")
    accessibility_matched_elements: List[str] = Field(default_factory=list, description="UI Automation element names matched")
    canvas_pixel_difference_ratio: Optional[float] = Field(default=None, description="Pixel change ratio for drawing/creative tasks")
    clipboard_verified_content: Optional[str] = Field(default=None, description="Verified clipboard payload if applicable")
    completed_step_ids: List[str] = Field(default_factory=list, description="List of plan steps completed successfully")
    total_steps: int = Field(default=0, description="Total planned steps")
    replan_count: int = Field(default=0, description="Total dynamic replan attempts triggered during execution")
    verification_timestamp_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when goal verification was executed",
    )
    diagnostics: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary verification telemetry")

    @property
    def completed_steps(self) -> List[str]:
        return self.completed_step_ids


class GoalVerificationResult(BaseModel):
    """Outcome of independent final goal completion verification."""

    status: TaskCompletionStatus = Field(..., description="Final epistemic status of the goal")
    is_completed: bool = Field(default=False, description="True ONLY when status == COMPLETED")
    failure_reason: Optional[str] = Field(default=None, description="Explanation when goal is not COMPLETED")
    failure_code: Optional[str] = Field(default=None, description="Machine-readable failure code")
    evidence: TaskCompletionEvidence = Field(default_factory=TaskCompletionEvidence, description="Structured verification evidence")
    diagnostics: Dict[str, Any] = Field(default_factory=dict, description="Additional goal verification telemetry")


class TaskExecutionResult(BaseModel):
    """Complete, structured end-to-end execution result for a natural language goal."""

    task_id: str = Field(default_factory=lambda: f"task_{uuid4().hex[:8]}", description="Unique task identifier")
    session_id: str = Field(default="default_session", description="Session identifier")
    goal: str = Field(..., description="Original raw natural language goal text")
    understanding: Optional[TaskUnderstandingResult] = Field(default=None, description="Parsed task understanding")
    plan: Optional[ExecutableTaskPlan] = Field(default=None, description="Generated task execution plan")
    plan_execution_result: Optional[PlanExecutionResult] = Field(default=None, description="Plan step execution details")
    goal_verification_result: GoalVerificationResult = Field(..., description="Independent final goal verification result")
    completion_status: TaskCompletionStatus = Field(..., description="Overall task completion status")
    is_success: bool = Field(default=False, description="True ONLY when completion_status == COMPLETED")
    completed_steps: List[str] = Field(default_factory=list, description="IDs of steps completed")
    failed_steps: List[str] = Field(default_factory=list, description="IDs of steps failed")
    recovery_attempts: int = Field(default=0, description="Total recovery and replan attempts")
    replan_history: List[Dict[str, Any]] = Field(default_factory=list, description="Replan records from execution")
    evidence: TaskCompletionEvidence = Field(default_factory=TaskCompletionEvidence, description="Verification evidence")
    failure_reason: Optional[str] = Field(default=None, description="Failure reason if not completed")
    failure_code: Optional[str] = Field(default=None, description="Failure code if not completed")
    start_time_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Start time UTC")
    end_time_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="End time UTC")
    elapsed_duration_ms: float = Field(default=0.0, description="Total execution duration in milliseconds")
    diagnostics: Dict[str, Any] = Field(default_factory=dict, description="Detailed diagnostic telemetry")
