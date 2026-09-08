"""Domain contracts and data models for ORBIT Task Understanding Subsystem (M1.8 Step 1)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


class TaskGoal(str, Enum):
    """Minimal extensible taxonomy of supported and classified task goals."""

    OPEN_APPLICATION = "OPEN_APPLICATION"
    CREATE_DOCUMENT = "CREATE_DOCUMENT"
    WRITE_TEXT = "WRITE_TEXT"
    SEARCH = "SEARCH"
    NAVIGATE = "NAVIGATE"
    CLICK_TARGET = "CLICK_TARGET"
    CALCULATE = "CALCULATE"
    SELECT_OPTION = "SELECT_OPTION"
    COPY_CONTENT = "COPY_CONTENT"
    PASTE_CONTENT = "PASTE_CONTENT"
    SAVE_DOCUMENT = "SAVE_DOCUMENT"
    CLOSE_APPLICATION = "CLOSE_APPLICATION"
    DRAW = "DRAW"
    INTERACT = "INTERACT"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"


class TaskUnderstandingStatus(str, Enum):
    """Epistemic outcome classification of task understanding."""

    UNDERSTOOD = "UNDERSTOOD"
    PARTIALLY_UNDERSTOOD = "PARTIALLY_UNDERSTOOD"
    AMBIGUOUS = "AMBIGUOUS"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID = "INVALID"
    FAILED = "FAILED"


class RawTaskRequest(BaseModel):
    """Original immutable user task request preserving provenance."""

    task_id: str = Field(default_factory=lambda: f"req_{uuid4().hex[:8]}", description="Unique request identifier")
    raw_text: str = Field(..., description="Exact raw user instruction text preserved verbatim")
    source: str = Field(default="user", description="Originating channel (e.g., user, api, websocket)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp of capture")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary client metadata")


class TargetReference(BaseModel):
    """Abstract semantic target reference.

    SAFETY INVARIANT:
    TargetReference represents abstract entities (e.g. application name, button text, role).
    It MUST NEVER contain physical screen coordinates (x, y). Physical grounding is deferred
    exclusively to runtime perception layers (M1.7).
    """

    semantic_type: str = Field(..., description="Entity category: application, ui_control, text, document, search_box, unknown")
    identifier: Optional[str] = Field(default=None, description="Recognized label, text, or title (e.g., 'Notepad', 'Save')")
    role: Optional[str] = Field(default=None, description="UI role if specified (e.g., 'button', 'edit', 'window')")
    anchor: Optional[str] = Field(default=None, description="Spatial or semantic anchor if specified")
    is_ambiguous: bool = Field(default=False, description="Whether target has ambiguity (e.g., 'it', 'the button')")
    unresolved_reason: Optional[str] = Field(default=None, description="Explanation when target cannot be resolved statically")


class TaskConstraints(BaseModel):
    """Extracted positive and negative constraints governing task execution."""

    application_name: Optional[str] = Field(default=None, description="Target application name context")
    content: Optional[str] = Field(default=None, description="Exact literal text payload (case, punctuation, Unicode preserved)")
    is_generative: bool = Field(default=False, description="Whether this task requires dynamic LLM generation")
    generation_prompt: Optional[str] = Field(default=None, description="The prompt instructions for the LLM")
    destination: Optional[str] = Field(default=None, description="Destination path or area if specified")
    source_reference: Optional[str] = Field(default=None, description="Source reference if applicable")
    is_negated: bool = Field(default=False, description="Whether the operation contains an explicit negative constraint")
    negation_details: Optional[str] = Field(default=None, description="Captured negation text (e.g., 'do not save', 'don't type')")
    confirmation_required: bool = Field(default=False, description="Whether user confirmation is explicitly required")
    custom_parameters: Dict[str, Any] = Field(default_factory=dict, description="Additional structured parameters")


class StructuredTaskIntent(BaseModel):
    """Single extracted conceptual operation with goal, target, constraints, and evidence."""

    intent_id: str = Field(default_factory=lambda: f"intent_{uuid4().hex[:8]}", description="Unique intent identifier")
    sequence_index: int = Field(default=0, description="0-indexed position in multi-goal sequence")
    goal: TaskGoal = Field(..., description="Classified primary goal")
    target: Optional[TargetReference] = Field(default=None, description="Abstract target reference")
    constraints: TaskConstraints = Field(default_factory=TaskConstraints, description="Extracted constraints")
    evidence: List[str] = Field(default_factory=list, description="Deterministic evidence explaining recognition")
    is_negated: bool = Field(default=False, description="Whether this specific intent is negated")
    is_ambiguous: bool = Field(default=False, description="Whether this intent contains unresolved ambiguity")
    unresolved_reason: Optional[str] = Field(default=None, description="Explanation of ambiguity or missing binding")


class TaskUnderstandingResult(BaseModel):
    """Complete structured outcome of task understanding."""

    request_id: str = Field(..., description="Associated RawTaskRequest identifier")
    raw_request: RawTaskRequest = Field(..., description="Original raw request record")
    status: TaskUnderstandingStatus = Field(..., description="Epistemic status of understanding")
    intents: List[StructuredTaskIntent] = Field(default_factory=list, description="Ordered sequence of structured intents")
    unresolved_constraints: List[str] = Field(default_factory=list, description="List of unresolved ambiguities or missing bindings")
    diagnostic_messages: List[str] = Field(default_factory=list, description="Parser and validator diagnostics")
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Parsing timestamp")

    @property
    def is_understood(self) -> bool:
        return self.status == TaskUnderstandingStatus.UNDERSTOOD

    @property
    def has_intents(self) -> bool:
        return len(self.intents) > 0
