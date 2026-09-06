"""Data contracts for persisted execution history records (Audit-grade)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Normalized lifecycle status of an execution record."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    REPLANNING = "REPLANNING"


class ExecutionStepRecord(BaseModel):
    """Structured breakdown of a single plan step in history."""

    step_id: str = Field(..., description="Unique step identifier")
    name: str = Field(..., description="Human-readable step description")
    status: str = Field(default="PENDING", description="COMPLETED, ACTIVE, FAILED, BLOCKED, PENDING")
    action_type: Optional[str] = Field(default=None, description="Action primitive type")
    detail: Optional[str] = Field(default=None, description="Contextual target or parameters")
    duration_ms: Optional[float] = Field(default=None, description="Step duration in milliseconds")


class ReplanAuditRecord(BaseModel):
    """Record of a dynamic replan event during execution."""

    replan_id: str = Field(default_factory=lambda: f"replan_{uuid4().hex[:8]}")
    reason: str = Field(..., description="User-friendly reason for replan")
    previous_step: Optional[str] = Field(default=None, description="Step being replaced or re-evaluated")
    new_strategy: Optional[str] = Field(default=None, description="Strategy summary of new plan")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CompletionEvidenceRecord(BaseModel):
    """Structured verification evidence backing execution completion."""

    application_name: Optional[str] = Field(default=None, description="Target application name")
    application_hwnd: Optional[int] = Field(default=None, description="Target window handle")
    window_title: Optional[str] = Field(default=None, description="Observed window title")
    verified_text: Optional[str] = Field(default=None, description="Verified target text content")
    ocr_matched_text: Optional[str] = Field(default=None, description="Verbatim OCR text matched")
    ocr_confidence: Optional[float] = Field(default=None, description="OCR match confidence [0.0..1.0]")
    visual_changes_detected: List[str] = Field(default_factory=list, description="Visual changes detected")
    accessibility_matched_elements: List[str] = Field(default_factory=list, description="UIA elements matched")
    diagnostics: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary verification telemetry")


class ExecutionRecord(BaseModel):
    """Audit-grade persistent record of a single task execution."""

    execution_id: str = Field(default_factory=lambda: f"exec_{uuid4().hex[:12]}")
    task_id: str = Field(..., description="Associated task identifier")
    session_id: str = Field(default="default_session", description="Session identifier")
    goal: str = Field(..., description="Natural language prompt or goal")
    status: ExecutionStatus = Field(default=ExecutionStatus.RUNNING)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = Field(default=None)
    duration_ms: float = Field(default=0.0)
    active_model: Optional[str] = Field(default=None, description="Model ID active during execution")
    model_provider: Optional[str] = Field(default=None, description="Model provider (e.g. OLLAMA, CLOUD)")
    applications_involved: List[str] = Field(default_factory=list, description="Applications genuinely interacted with")
    steps: List[ExecutionStepRecord] = Field(default_factory=list)
    steps_completed: int = Field(default=0)
    total_steps: int = Field(default=0)
    replanning_count: int = Field(default=0)
    replan_history: List[ReplanAuditRecord] = Field(default_factory=list)
    failure_reason: Optional[str] = Field(default=None)
    failure_code: Optional[str] = Field(default=None)
    cancellation_reason: Optional[str] = Field(default=None)
    evidence: Optional[CompletionEvidenceRecord] = Field(default=None)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
