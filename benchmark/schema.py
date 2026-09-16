"""Pydantic data schemas and contracts for ORBIT 50-Task Benchmark."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.models.common import BoundingBox


class BenchmarkSplit(str, Enum):
    """Dataset partition."""
    DEVELOPMENT = "DEVELOPMENT"
    UNSEEN = "UNSEEN"


class BenchmarkCategory(str, Enum):
    """15 core desktop task categories."""
    APPLICATION_LAUNCH = "APPLICATION_LAUNCH"
    TEXT_ENTRY = "TEXT_ENTRY"
    UI_INTERACTION = "UI_INTERACTION"
    FILESYSTEM = "FILESYSTEM"
    SAVE_EXPORT = "SAVE_EXPORT"
    PAINT_CANVAS = "PAINT_CANVAS"
    BROWSER_INSPECTION = "BROWSER_INSPECTION"
    MULTI_APP_WORKFLOW = "MULTI_APP_WORKFLOW"
    MULTI_STEP_EDITING = "MULTI_STEP_EDITING"
    DIALOG_HANDLING = "DIALOG_HANDLING"
    VISUAL_GROUNDING = "VISUAL_GROUNDING"
    STATE_RECOVERY = "STATE_RECOVERY"
    LONG_HORIZON = "LONG_HORIZON"
    ARTIFACT_VALIDATION = "ARTIFACT_VALIDATION"
    MIXED_WORKFLOW = "MIXED_WORKFLOW"


class ExpectedDeliverable(BaseModel):
    """File artifact expectation contract."""
    file_path: str = Field(..., description="Target file path (relative to desktop/workspace or absolute)")
    format: str = Field(..., description="Expected format e.g. text, png, jpeg, pdf, json, bmp")
    min_size_bytes: int = Field(default=1, ge=0)
    magic_bytes_hex: Optional[str] = Field(default=None, description="Expected header magic bytes e.g. 89504E47")
    expected_content_substr: Optional[str] = Field(default=None, description="Expected text substring")
    expected_checksum_sha256: Optional[str] = Field(default=None)


class TaskExpectation(BaseModel):
    """Objective postcondition verification contract."""
    expected_window_title: Optional[str] = None
    expected_window_class: Optional[str] = None
    expected_process_name: Optional[str] = None
    expected_ui_text: Optional[str] = None
    expected_ui_control_type: Optional[str] = None
    expected_deliverable: Optional[ExpectedDeliverable] = None
    require_app_open: bool = Field(default=False)
    require_app_closed: bool = Field(default=False)
    custom_eval_rule: Optional[str] = None


class BenchmarkTask(BaseModel):
    """Complete specification of a benchmark task."""
    task_id: str = Field(..., description="Unique identifier e.g. task_001")
    title: str = Field(..., description="Short human-readable task title")
    split: BenchmarkSplit = Field(..., description="DEVELOPMENT or UNSEEN")
    category: BenchmarkCategory = Field(..., description="One of 15 desktop categories")
    natural_language_goal: str = Field(..., description="User prompt presented to the agent")
    environment_prerequisites: Dict[str, Any] = Field(default_factory=dict)
    initial_clean_processes: List[str] = Field(default_factory=list)
    initial_setup_script: Optional[str] = None
    expectations: TaskExpectation = Field(..., description="Verification contract")
    timeout_sec: float = Field(default=60.0, gt=0.0)
    max_steps: int = Field(default=15, gt=0)


class ActionStepTrace(BaseModel):
    """Granular log of an individual execution step."""
    step_index: int
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action_type: str
    target_name: Optional[str] = None
    target_role: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    grounded_coordinates: Optional[List[int]] = None
    grounding_pass: Optional[str] = None
    grounding_confidence: float = 0.0
    dispatch_success: bool = False
    verification_passed: bool = False
    verification_reason: str = ""
    latency_ms: float = 0.0
    screenshot_path: Optional[str] = None


class TaskExecutionRecord(BaseModel):
    """Structured telemetry record of a benchmark task execution."""
    task_id: str
    split: BenchmarkSplit
    category: BenchmarkCategory
    natural_language_goal: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    duration_sec: float = 0.0
    is_success: bool = False
    goal_verified: bool = False
    artifact_verified: bool = False
    total_steps: int = 0
    actions_attempted: int = 0
    actions_completed: int = 0
    recovery_attempts: int = 0
    model_calls: int = 0
    failure_category: Optional[str] = None
    failure_reason: Optional[str] = None
    step_traces: List[ActionStepTrace] = Field(default_factory=list)
    final_world_state_summary: Optional[str] = None
    human_interventions: int = 0


class BenchmarkMetricsSummary(BaseModel):
    """Aggregate metrics across the entire 50-task benchmark."""
    total_tasks: int = 50
    dev_tasks_count: int = 25
    unseen_tasks_count: int = 25
    total_passed: int = 0
    dev_passed: int = 0
    unseen_passed: int = 0
    task_success_rate: float = 0.0
    dev_success_rate: float = 0.0
    unseen_success_rate: float = 0.0
    goal_verification_accuracy: float = 0.0
    artifact_correctness_rate: float = 0.0
    grounding_accuracy: float = 0.0
    recovery_success_rate: float = 0.0
    avg_actions_per_task: float = 0.0
    avg_duration_sec: float = 0.0
    avg_model_calls_per_task: float = 0.0
    failure_category_distribution: Dict[str, int] = Field(default_factory=dict)
    category_success_rates: Dict[str, float] = Field(default_factory=dict)
