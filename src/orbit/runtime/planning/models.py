"""Domain contracts and data models for ORBIT Task Planning Subsystem (M1.8 Step 2)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.task_understanding.models import (
    RawTaskRequest,
    StructuredTaskIntent,
    TargetReference,
    TaskConstraints,
    TaskGoal,
)
from orbit.runtime.targeting.models import TargetStrategy


class PlanActionType(str, Enum):
    """Abstract action objectives generated during planning."""

    ENSURE_APPLICATION_OPEN = "ENSURE_APPLICATION_OPEN"
    FOCUS_APPLICATION = "FOCUS_APPLICATION"
    LOCATE_TARGET = "LOCATE_TARGET"
    LOCATE_INPUT_SURFACE = "LOCATE_INPUT_SURFACE"
    ENTER_TEXT = "ENTER_TEXT"
    ACTIVATE_CONTROL = "ACTIVATE_CONTROL"
    DRAW_STROKES = "DRAW_STROKES"
    COPY_CONTENT = "COPY_CONTENT"
    PASTE_CONTENT = "PASTE_CONTENT"
    SAVE_DOCUMENT = "SAVE_DOCUMENT"
    CLOSE_APPLICATION = "CLOSE_APPLICATION"
    SEARCH_QUERY = "SEARCH_QUERY"
    SELECT_OPTION = "SELECT_OPTION"
    NAVIGATE_VIEW = "NAVIGATE_VIEW"
    VALIDATE_SELECTION_CONTEXT = "VALIDATE_SELECTION_CONTEXT"
    VERIFY_APPLICATION_AVAILABLE = "VERIFY_APPLICATION_AVAILABLE"
    VERIFY_TEXT_ENTRY = "VERIFY_TEXT_ENTRY"
    VERIFY_TARGET_EFFECT = "VERIFY_TARGET_EFFECT"
    VERIFY_DOCUMENT_SAVED = "VERIFY_DOCUMENT_SAVED"
    VERIFY_CLIPBOARD_STATE = "VERIFY_CLIPBOARD_STATE"
    UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"


class PlanStatus(str, Enum):
    """Epistemic outcome classification of plan generation and validation."""

    DRAFT = "DRAFT"
    VALID = "VALID"
    PARTIALLY_PLANNED = "PARTIALLY_PLANNED"
    AMBIGUOUS = "AMBIGUOUS"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID = "INVALID"
    FAILED = "FAILED"


class Precondition(BaseModel):
    """Machine-readable condition that must hold true before step execution."""

    condition_type: str = Field(..., description="Precondition category (e.g., application_running, element_visible)")
    target: Optional[str] = Field(default=None, description="Target entity or application name")
    description: str = Field(..., description="Human-readable description of precondition")
    required_state: Dict[str, Any] = Field(default_factory=dict, description="Expected state attributes")


class Postcondition(BaseModel):
    """Expected outcome state description after successful step execution."""

    condition_type: str = Field(..., description="Postcondition category (e.g., text_rendered, window_active)")
    target: Optional[str] = Field(default=None, description="Target entity or outcome reference")
    description: str = Field(..., description="Human-readable description of expected post-state")
    expected_state: Dict[str, Any] = Field(default_factory=dict, description="Verifiable post-execution attributes")


class DeferredGroundingRequirement(BaseModel):
    """Abstract perception requirement to be grounded at runtime by M1.7 perception."""

    strategy_preferences: List[TargetStrategy] = Field(
        default_factory=lambda: [
            TargetStrategy.ACCESSIBILITY_ELEMENT,
            TargetStrategy.OCR_TEXT,
            TargetStrategy.VISUAL_TEMPLATE,
        ],
        description="Ordered perception strategy preferences for runtime grounding",
    )
    target_reference: TargetReference = Field(..., description="Abstract target reference to locate on live screen")
    anchor: Optional[str] = Field(default=None, description="Optional spatial or hierarchical anchor")
    grounding_notes: Optional[str] = Field(default=None, description="Perception hints for runtime resolver")


class PlanStep(BaseModel):
    """Abstract, strongly-typed execution objective in a dependency graph.

    SAFETY INVARIANT:
    PlanStep represents high-level semantic operations (e.g., LOCATE_TARGET, ENTER_TEXT).
    It MUST NEVER contain physical screen coordinates (x, y). All coordinate resolution
    is strictly deferred to runtime M1.7 perception layers.
    """

    step_id: str = Field(default_factory=lambda: f"step_{uuid4().hex[:6]}", description="Unique step identifier")
    step_index: int = Field(default=0, description="Topological sequence index")
    action_type: PlanActionType = Field(..., description="Abstract plan action objective")
    description: str = Field(..., description="Human-readable step objective")
    target: Optional[TargetReference] = Field(default=None, description="Abstract target reference")
    constraints: TaskConstraints = Field(default_factory=TaskConstraints, description="Inherited task constraints")
    preconditions: List[Precondition] = Field(default_factory=list, description="Preconditions required before execution")
    postconditions: List[Postcondition] = Field(default_factory=list, description="Expected postconditions upon completion")
    dependencies: List[str] = Field(default_factory=list, description="List of step_ids that must complete prior to this step")
    deferred_grounding: Optional[DeferredGroundingRequirement] = Field(default=None, description="Runtime perception requirements")
    evidence: List[str] = Field(default_factory=list, description="Traceability evidence (source goal, rule, constraints)")
    is_negated: bool = Field(default=False, description="Whether this step is negated or prohibited")
    is_ambiguous: bool = Field(default=False, description="Whether this step has unresolved ambiguity")
    unresolved_reason: Optional[str] = Field(default=None, description="Diagnostic explanation if step is ambiguous")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary step metadata")


class ExecutableTaskPlan(BaseModel):
    """Validated, dependency-aware task execution plan ready for future M1.8 execution."""

    plan_id: str = Field(default_factory=lambda: f"plan_{uuid4().hex[:8]}", description="Unique plan identifier")
    task_id: str = Field(..., description="Associated task identifier")
    description: str = Field(..., description="High-level plan summary")
    status: PlanStatus = Field(..., description="Epistemic validation status of the plan")
    steps: List[PlanStep] = Field(default_factory=list, description="Topologically ordered execution steps")
    step_dependencies: Dict[str, List[str]] = Field(default_factory=dict, description="Adjacency list mapping step_id -> predecessor step_ids")
    unresolved_items: List[str] = Field(default_factory=list, description="Unresolved ambiguities or missing bindings")
    explanation: Dict[str, Any] = Field(default_factory=dict, description="Deterministic explainability breakdown")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Plan creation timestamp")

    @property
    def is_valid(self) -> bool:
        return self.status == PlanStatus.VALID

    @property
    def step_count(self) -> int:
        return len(self.steps)
