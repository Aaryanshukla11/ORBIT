"""Agent Action Protocol and Execution Contracts (Step 2).

Strict JSON schemas and Pydantic models for every agent action.
Every action specifies a semantic target, parameters, expected effect, and verification strategy.

SAFETY INVARIANT:
Physical screen coordinates (x, y) MUST NEVER originate from the AI/LLM layer.
Coordinates are resolved exclusively at runtime by EvidenceBasedTargetLocator into ResolvedAction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Set, Union
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator, model_validator

from orbit.models.common import BoundingBox
from orbit.runtime.targeting.models import SafeActionPoint, TargetBoundingBox


class AbstractActionType(str, Enum):
    """Canonical primitive vocabulary for ORBIT General Computer Agent."""

    # ── TIER 1: PHYSICAL COMPUTER PRIMITIVES ────────────────────────────
    LAUNCH_APPLICATION = "LAUNCH_APPLICATION"
    FOCUS_WINDOW = "FOCUS_WINDOW"
    CLICK = "CLICK"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    RIGHT_CLICK = "RIGHT_CLICK"
    TYPE_TEXT = "TYPE_TEXT"
    SEND_HOTKEY = "SEND_HOTKEY"
    SCROLL = "SCROLL"
    DRAG = "DRAG"
    DRAW_STROKES = "DRAW_STROKES"
    SELECT_OPTION = "SELECT_OPTION"
    WAIT = "WAIT"
    WAIT_SETTLE = "WAIT_SETTLE"

    # ── TIER 2: OBSERVATION PRIMITIVES ───────────────────────────────────
    SCREENSHOT = "SCREENSHOT"
    READ_UI_ELEMENT = "READ_UI_ELEMENT"
    READ_OCR_TEXT = "READ_OCR_TEXT"

    # ── TIER 3: ENVIRONMENT INTERFACES (Dispatched via Providers) ────────
    FILE_READ = "FILE_READ"
    FILE_WRITE = "FILE_WRITE"
    BROWSER_NAVIGATE = "BROWSER_NAVIGATE"
    SPREADSHEET_READ = "SPREADSHEET_READ"
    SPREADSHEET_WRITE = "SPREADSHEET_WRITE"
    SHELL_EXECUTE = "SHELL_EXECUTE"
    IMAGE_GENERATE = "IMAGE_GENERATE"

    # ── CONTROL SIGNALS (Never physical execution actions) ───────────────
    COMPLETE_GOAL = "COMPLETE_GOAL"
    ABORT_TASK = "ABORT_TASK"


TIER1_COMPUTER_PRIMITIVES = frozenset({
    AbstractActionType.LAUNCH_APPLICATION,
    AbstractActionType.FOCUS_WINDOW,
    AbstractActionType.CLICK,
    AbstractActionType.DOUBLE_CLICK,
    AbstractActionType.RIGHT_CLICK,
    AbstractActionType.TYPE_TEXT,
    AbstractActionType.SEND_HOTKEY,
    AbstractActionType.SCROLL,
    AbstractActionType.DRAG,
    AbstractActionType.DRAW_STROKES,
    AbstractActionType.SELECT_OPTION,
    AbstractActionType.WAIT,
    AbstractActionType.WAIT_SETTLE,
})

TIER2_OBSERVATION_PRIMITIVES = frozenset({
    AbstractActionType.SCREENSHOT,
    AbstractActionType.READ_UI_ELEMENT,
    AbstractActionType.READ_OCR_TEXT,
})

TIER3_ENVIRONMENT_INTERFACES = frozenset({
    AbstractActionType.FILE_READ,
    AbstractActionType.FILE_WRITE,
    AbstractActionType.BROWSER_NAVIGATE,
    AbstractActionType.SPREADSHEET_READ,
    AbstractActionType.SPREADSHEET_WRITE,
    AbstractActionType.SHELL_EXECUTE,
    AbstractActionType.IMAGE_GENERATE,
})

CONTROL_SIGNAL_PRIMITIVES = frozenset({
    AbstractActionType.COMPLETE_GOAL,
    AbstractActionType.ABORT_TASK,
})

# Backward compatibility alias
ActionType = AbstractActionType

# Legacy alias mappings for boundary compatibility
AbstractActionType.CLICK_ELEMENT = AbstractActionType.CLICK  # type: ignore[attr-defined]
AbstractActionType.TYPE = AbstractActionType.TYPE_TEXT  # type: ignore[attr-defined]
AbstractActionType.HOTKEY = AbstractActionType.SEND_HOTKEY  # type: ignore[attr-defined]
AbstractActionType.DRAW = AbstractActionType.DRAW_STROKES  # type: ignore[attr-defined]
AbstractActionType.COMPLETE = AbstractActionType.COMPLETE_GOAL  # type: ignore[attr-defined]
AbstractActionType.ABORT = AbstractActionType.ABORT_TASK  # type: ignore[attr-defined]
AbstractActionType.ABORT_UNACHIEVABLE = AbstractActionType.ABORT_TASK  # type: ignore[attr-defined]


class VerificationStrategy(str, Enum):
    """Verification strategy declaring how the action's immediate effect will be evaluated."""

    WINDOW_FOCUS = "WINDOW_FOCUS"                  # Verify active foreground window
    WIN32_WINDOW = "WIN32_WINDOW"                  # Verify Win32 window title, class, or state
    WINDOW_EXISTS = "WINDOW_EXISTS"                # Verify target window exists and is visible
    UIA_STATE = "UIA_STATE"                        # Verify UI Automation accessibility element state
    UIA_ELEMENT = "UIA_ELEMENT"                    # Alias for UIA_STATE
    UIA_TEXT = "UIA_TEXT"                          # Verify UI Automation text value/buffer
    OCR_TEXT = "OCR_TEXT"                          # Verify on-screen OCR text tokens
    OCR_MATCH = "OCR_MATCH"                        # Alias for OCR_TEXT
    PIXEL_DELTA = "PIXEL_DELTA"                    # Verify visual pixel delta
    PIXEL_DIFF = "PIXEL_DIFF"                      # Alias for PIXEL_DELTA
    CANVAS_CHANGE = "CANVAS_CHANGE"                # Verify canvas drawing strokes modified pixels
    CANVAS_PIXEL_DELTA = "CANVAS_PIXEL_DELTA"      # Alias for CANVAS_CHANGE
    ELEMENT_VISIBLE = "ELEMENT_VISIBLE"            # Verify target UI element appears
    APPLICATION_STATE = "APPLICATION_STATE"        # Verify process running and responsive
    VISUAL_VISION_EVAL = "VISUAL_VISION_EVAL"      # Verify visual state delta via Vision Model
    WINDOW_FOCUS_OR_STATE = "WINDOW_FOCUS_OR_STATE"# Flexible window focus or state verification
    AUTO_ROUTED = "AUTO_ROUTED"                    # Dynamically route through PerceptionRouter


class OutcomeStatus(str, Enum):
    """Classification of action execution and outcome verification."""

    EFFECT_VERIFIED = "EFFECT_VERIFIED"
    EFFECT_UNVERIFIED = "EFFECT_UNVERIFIED"
    DISPATCH_FAILED = "DISPATCH_FAILED"
    RECOVERY_ATTEMPTED = "RECOVERY_ATTEMPTED"
    REDUNDANT_BLOCKED = "REDUNDANT_BLOCKED"


# ==============================================================================
# SEMANTIC TARGET (NO COORDINATES PERMITTED)
# ==============================================================================

class SemanticTarget(BaseModel):
    """Abstract semantic target representation without hardcoded coordinates.

    SAFETY INVARIANT:
    Physical screen coordinates (x, y) MUST NEVER originate from the Cognitive or LLM layer.
    Coordinates are generated exclusively at execution time by runtime perception/target locator.
    """

    name: Optional[str] = Field(default=None, description="Logical target label, button text, or window title")
    role: Optional[str] = Field(default=None, description="UI role: button, edit, canvas, window, menu, tab, etc.")
    application: Optional[str] = Field(default=None, description="Surrounding application name e.g. 'Notepad', 'Paint'")
    context: Optional[str] = Field(default=None, description="Surrounding container, dialog title, or tab name")
    anchor: Optional[str] = Field(default=None, description="Relative anchor e.g. 'top right', 'next to Username'")
    text_hint: Optional[str] = Field(default=None, description="Exact or partial text to locate via OCR")
    accessibility_hint: Optional[str] = Field(default=None, description="AutomationId, ClassName, or UIA property hint")

    @model_validator(mode="before")
    @classmethod
    def reject_all_coordinate_fields(cls, data: Any) -> Any:
        """Strictly reject any direct physical screen coordinate fields from LLM/cognitive targets."""
        if isinstance(data, dict):
            forbidden = {
                "x", "y", "width", "height", "screen_x", "screen_y", "coord_x", "coord_y",
                "pos_x", "pos_y", "position", "screen_position", "coordinates", "bbox", "bounding_box"
            }
            found = forbidden.intersection(k.lower() for k in data.keys())
            if found:
                raise ValueError(
                    f"CoordinatePolicyViolation: SemanticTarget must NEVER contain physical screen coordinates: {found}. "
                    "Coordinates must be generated at runtime by TargetLocator."
                )
        return data


# ==============================================================================
# ACTION PARAMETER SCHEMAS (TYPE-SAFE)
# ==============================================================================

class LaunchApplicationParams(BaseModel):
    """Parameters for launching a desktop application."""

    application_name: str = Field(..., description="Application name or executable, e.g. 'notepad', 'calc'")
    command_line: Optional[str] = Field(default=None, description="Optional command line arguments")
    working_directory: Optional[str] = Field(default=None, description="Optional working directory")


class FocusWindowParams(BaseModel):
    """Parameters for focusing an application window."""

    window_title: Optional[str] = Field(default=None, description="Window title substring to focus")
    application_name: Optional[str] = Field(default=None, description="Process executable or application name")
    hwnd: Optional[int] = Field(default=None, description="Win32 Window Handle if known from observation")


class ClickParams(BaseModel):
    """Parameters for pointer click actions."""

    button: str = Field(default="left", description="Mouse button: 'left', 'right', 'middle'")
    click_count: int = Field(default=1, ge=1, le=3, description="Number of clicks")


class DoubleClickParams(BaseModel):
    """Parameters for double click pointer actions."""

    button: str = Field(default="left", description="Mouse button: 'left', 'right'")


class RightClickParams(BaseModel):
    """Parameters for right click pointer actions."""

    button: str = Field(default="right", description="Mouse button: 'right'")


class TypeTextParams(BaseModel):
    """Parameters for typing text input."""

    text: str = Field(..., description="Text payload to type")
    press_enter: bool = Field(default=False, description="Whether to press Enter after typing")
    clear_existing: bool = Field(default=False, description="Whether to select/clear existing text first")


class SendHotkeyParams(BaseModel):
    """Parameters for sending keyboard hotkey combinations."""

    hotkey: str = Field(default="", description="Hotkey string representation, e.g. 'ctrl+s', 'alt+f4'")
    keys: List[str] = Field(default_factory=list, description="List of key names")


class ScrollParams(BaseModel):
    """Parameters for scroll wheel actions."""

    direction: str = Field(default="down", description="Scroll direction: 'up', 'down', 'left', 'right'")
    amount: Union[int, str] = Field(default="medium", description="Scroll amount: integer clicks or 'small', 'medium', 'large'")


class WaitParams(BaseModel):
    """Parameters for waiting/settling."""

    duration_sec: float = Field(default=1.0, ge=0.0, le=60.0, description="Duration to wait in seconds")
    reason: Optional[str] = Field(default=None, description="Reason for settling pause")


class DrawStrokesParams(BaseModel):
    """Parameters for geometric canvas drawing."""

    shape: str = Field(default="cube", description="Geometric shape or object to draw, e.g. 'cube', 'car', 'circle'")
    style: str = Field(default="outline", description="Drawing style: 'outline', 'filled', 'wireframe'")
    points: Optional[List[Dict[str, float]]] = Field(
        default=None,
        description="Optional normalized relative stroke points [0.0..1.0] within target canvas box",
    )


class DragParams(BaseModel):
    """Parameters for drag and drop actions."""

    source_target: Optional[SemanticTarget] = Field(default=None, description="Source semantic target")
    destination_target: Optional[SemanticTarget] = Field(default=None, description="Destination semantic target")
    relative_vector_x: float = Field(default=0.0, description="Relative horizontal pixel offset if no dest target")
    relative_vector_y: float = Field(default=0.0, description="Relative vertical pixel offset if no dest target")


class SelectOptionParams(BaseModel):
    """Parameters for dropdown or combo box selection."""

    option_name: str = Field(..., description="Visible label of option to select")
    index: Optional[int] = Field(default=None, description="Index of option if known")


class CompleteGoalParams(BaseModel):
    """Parameters for signaling goal satisfaction."""

    summary: str = Field(default="", description="Summary of how the objective was achieved")
    verified_evidence: Optional[Dict[str, Any]] = Field(default=None, description="Evidence verifying completion")


class AbortTaskParams(BaseModel):
    """Parameters for signaling task unachievability."""

    reason: str = Field(default="", description="Diagnostic explanation of why task cannot be achieved")


# ==============================================================================
# ACTION-TO-OUTCOME CONTRACT
# ==============================================================================

class ActionOutcomeContract(BaseModel):
    """Contract specifying the observable physical effect expected from an action."""

    expected_state_transition: str = Field(
        ...,
        description="Description of expected state delta (e.g. 'notepad_focused', 'text_entered', 'canvas_modified')",
    )
    verification_strategy: VerificationStrategy = Field(
        default=VerificationStrategy.AUTO_ROUTED,
        description="Strategy to verify outcome",
    )
    target_role: Optional[str] = Field(default=None, description="Expected active UI role")
    target_name: Optional[str] = Field(default=None, description="Expected active target name or window title")
    expected_window_title: Optional[str] = Field(default=None, description="Expected foreground window title substring")
    expected_text: Optional[str] = Field(default=None, description="Expected text to appear on screen / in buffer")
    required_evidence: Optional[Dict[str, Any]] = Field(default=None, description="Required evidence criteria")
    timeout_sec: float = Field(default=5.0, ge=0.1, le=60.0, description="Verification timeout in seconds")
    match_criteria: Optional[Dict[str, Any]] = Field(default=None, description="Custom criteria for verification")

    @property
    def description(self) -> str:
        return self.expected_state_transition

    @property
    def strategy(self) -> VerificationStrategy:
        return self.verification_strategy

    @model_validator(mode="before")
    @classmethod
    def harmonize_contract_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "expected_state_transition" not in data and "description" in data:
                data["expected_state_transition"] = data["description"]
            if "verification_strategy" not in data and "strategy" in data:
                data["verification_strategy"] = data["strategy"]
        return data

    @classmethod
    def from_description(
        cls,
        description: str,
        strategy: VerificationStrategy = VerificationStrategy.AUTO_ROUTED,
        **kwargs: Any,
    ) -> ActionOutcomeContract:
        return cls(expected_state_transition=description, verification_strategy=strategy, **kwargs)


# Alias for backward compatibility
ExpectedState = ActionOutcomeContract


# ==============================================================================
# ABSTRACT ACTION (COGNITIVE LAYER — NO COORDINATES)
# ==============================================================================

class AbstractAction(BaseModel):
    """An abstract action command emitted by the AI / Cognitive Decision Engine."""

    action_id: str = Field(default_factory=lambda: f"act_{uuid4().hex[:8]}", description="Unique action ID")
    action_type: AbstractActionType = Field(..., description="Action classification")
    target: Optional[SemanticTarget] = Field(default=None, description="Semantic target specification (NO coordinates)")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Semantic parameters (e.g. text, shape, app_name)")
    outcome_contract: Optional[ActionOutcomeContract] = Field(default=None, description="Action-to-outcome contract")
    expected_effect: str = Field(default="", description="High-level expected effect description")
    rationale: str = Field(default="", description="Reasoning for choosing this specific action")

    @property
    def semantic_target(self) -> Optional[SemanticTarget]:
        return self.target

    @property
    def expected_state(self) -> Optional[ActionOutcomeContract]:
        return self.outcome_contract

    @property
    def verification_strategy(self) -> VerificationStrategy:
        if self.outcome_contract:
            return self.outcome_contract.verification_strategy
        return VerificationStrategy.AUTO_ROUTED

    @field_validator("parameters")
    @classmethod
    def validate_no_physical_coordinates(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Enforce architectural invariant: LLM/Cognitive layer must never emit physical screen coordinates."""
        forbidden_keys = {
            "x", "y", "screen_x", "screen_y", "coord_x", "coord_y", "pos_x", "pos_y",
            "screen_position", "coordinates", "raw_x", "raw_y"
        }
        found = forbidden_keys.intersection(k.lower() for k in v.keys())
        if found:
            raise ValueError(
                f"CoordinatePolicyViolation: Cognitive AbstractAction parameters must NOT contain physical coordinates: {found}. "
                "Coordinates must be determined dynamically at execution time by TargetLocator."
            )
        return v

    @model_validator(mode="before")
    @classmethod
    def harmonize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Target alias
            if "target" not in data and "semantic_target" in data:
                data["target"] = data["semantic_target"]
            # Outcome contract alias
            if "outcome_contract" not in data and "expected_state" in data:
                data["outcome_contract"] = data["expected_state"]
            # Fallback outcome contract from expected_effect
            if not data.get("outcome_contract") and data.get("expected_effect"):
                data["outcome_contract"] = {
                    "expected_state_transition": data["expected_effect"],
                    "verification_strategy": data.get("verification_strategy", "AUTO_ROUTED"),
                }
        return data


# Backward compatibility alias
AgentAction = AbstractAction


# ==============================================================================
# RESOLVED ACTION (RUNTIME EXECUTION CONTRACT — GROUNDED BY TARGET LOCATOR)
# ==============================================================================

class ResolvedAction(BaseModel):
    """Runtime execution contract produced ONLY by ORBIT target resolution components.

    SAFETY INVARIANT:
    The AI/LLM must NEVER construct a ResolvedAction directly.
    ResolvedAction is generated exclusively by ORBIT runtime components by grounding an
    AbstractAction's SemanticTarget against live desktop perception.
    """

    action_id: str = Field(..., description="Action ID matching the source AbstractAction")
    action_type: AbstractActionType = Field(..., description="Action classification")
    resolved_target_id: Optional[str] = Field(default=None, description="Unique identifier of grounded UI target")
    bounding_box: Optional[TargetBoundingBox] = Field(default=None, description="Live grounded physical bounding box")
    execution_point: Optional[SafeActionPoint] = Field(default=None, description="Computed safe physical (x, y) execution point")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Validated runtime parameters")
    outcome_contract: Optional[ActionOutcomeContract] = Field(default=None, description="Contract for post-execution verification")
    target_hwnd: Optional[int] = Field(default=None, description="Owning top-level window handle if resolved")
    resolved_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of resolution")
    resolution_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Target locator confidence score")
    grounding_source: str = Field(default="TARGET_LOCATOR", description="Grounding source: UIA, WIN32, OCR, VISION")


# ==============================================================================
# ACTION EXECUTION RESULT (TRIPARTITE DISTINCTION)
# ==============================================================================

class ActionExecutionOutcome(BaseModel):
    """Strict execution and verification outcome of a single dispatched action.

    CRITICAL TRIPARTITE DISTINCTION:
    1. dispatch_success: Did the operating system / adapter accept the low-level input command?
    2. expected_effect_observed: Was the expected physical state transition verified?
    3. goal_satisfied: Did this action satisfy the overall user objective?

    These three states are NEVER treated as equivalent.
    """

    action_id: str = Field(default_factory=lambda: f"act_{uuid4().hex[:8]}", description="Associated action identifier")
    dispatch_success: bool = Field(..., description="Whether low-level OS adapter accepted the input command")
    expected_effect_observed: bool = Field(..., description="Whether expected semantic state transition was verified")
    goal_satisfied: bool = Field(default=False, description="Whether overall goal is satisfied")
    outcome_status: OutcomeStatus = Field(
        default=OutcomeStatus.EFFECT_UNVERIFIED,
        description="Outcome status classification",
    )
    verified: bool = Field(default=False, description="Whether immediate action effect is verified (alias for expected_effect_observed)")
    verification_strategy: VerificationStrategy = Field(
        default=VerificationStrategy.AUTO_ROUTED,
        description="Strategy applied during verification",
    )
    verification_reason: str = Field(default="", description="Reasoning and diagnostic findings from verification")
    pre_action_state: Optional[Dict[str, Any]] = Field(default=None, description="Pre-action desktop state summary")
    post_action_state: Optional[Dict[str, Any]] = Field(default=None, description="Post-action desktop state summary")
    observed_delta: Dict[str, Any] = Field(default_factory=dict, description="Observed pre vs post state changes")
    verification_evidence: Dict[str, Any] = Field(default_factory=dict, description="Raw sensory evidence from verification")
    error_message: Optional[str] = Field(default=None, description="Error message if dispatch or verification failed")
    failure_code: Optional[str] = Field(default=None, description="Structured failure classification code")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Elapsed verification time in milliseconds")

    text_verification: Optional[TextVerificationResult] = Field(default=None, description="Detailed provenance and comparison for text entry verification")

    @model_validator(mode="after")
    def sync_verified_fields(self) -> ActionExecutionOutcome:
        # Keep verified and expected_effect_observed in sync
        if self.expected_effect_observed and not self.verified:
            self.verified = True
        elif self.verified and not self.expected_effect_observed:
            self.expected_effect_observed = True

        # Synchronize outcome_status
        if not self.dispatch_success:
            self.outcome_status = OutcomeStatus.DISPATCH_FAILED
        elif self.expected_effect_observed:
            self.outcome_status = OutcomeStatus.EFFECT_VERIFIED
        else:
            self.outcome_status = OutcomeStatus.EFFECT_UNVERIFIED
        return self


# Backward compatibility alias
ActionExecutionResult = ActionExecutionOutcome


class TextMatchState(str, Enum):
    """Explicit categorical text verification states."""

    EXACT_MATCH = "EXACT_MATCH"
    NORMALIZED_MATCH = "NORMALIZED_MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    MISMATCH = "MISMATCH"
    NO_TEXT_EVIDENCE = "NO_TEXT_EVIDENCE"


class TextVerificationResult(BaseModel):
    """Detailed evidence-based verification result for text actions."""

    expected_text: str = Field(..., description="Exact expected text string")
    normalized_expected_text: str = Field(..., description="Normalized expected text for comparison")
    observed_text_candidates: List[str] = Field(default_factory=list, description="Observed text strings from post-action perception")
    evidence_sources: List[str] = Field(default_factory=list, description="Perception sources evaluated: UIA, OCR, etc.")
    match_state: TextMatchState = Field(default=TextMatchState.NO_TEXT_EVIDENCE, description="Categorical match classification")
    exact_match: bool = Field(default=False, description="Whether an exact match was observed")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence of text match")
    observation_id: str = Field(..., description="Provenance ID of the post-action observation")
    primary_source: Optional[str] = Field(default=None, description="Source yielding the primary match/closest candidate")
    observed_text: Optional[str] = Field(default=None, description="Actual observed text from primary source")
    dispatch_success: bool = Field(default=True, description="Whether the low-level physical dispatch succeeded")
    expected_effect_observed: bool = Field(default=False, description="Whether the exact/normalized text was independently observed on desktop")
    goal_satisfied: bool = Field(default=False, description="Whether the complete user objective is verified")
    selected_input_strategy: Optional[str] = Field(default=None, description="Input strategy utilized (e.g. CLIPBOARD_ATOMIC, KEYBOARD_STREAM)")
    input_attempt_id: Optional[str] = Field(default=None, description="Unique identifier for the physical text input attempt")
    target_window_before: Optional[str] = Field(default=None, description="Target window title/identifier before dispatch")
    target_window_after: Optional[str] = Field(default=None, description="Target window title/identifier after dispatch")


# ==============================================================================
# COMPONENT 3: ACTION VALIDATOR
# ==============================================================================

class ActionValidationFailureCode(str, Enum):
    """Failure classifications for agent action validation."""

    VALID = "VALID"
    INVALID_ACTION = "INVALID_ACTION"
    UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"
    INVALID_PARAMETERS = "INVALID_PARAMETERS"
    MISSING_SEMANTIC_TARGET = "MISSING_SEMANTIC_TARGET"
    COORDINATE_POLICY_VIOLATION = "COORDINATE_POLICY_VIOLATION"
    MISSING_OUTCOME_CONTRACT = "MISSING_OUTCOME_CONTRACT"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"


class ActionValidationResult(BaseModel):
    """Result of validating an AbstractAction prior to execution."""

    is_valid: bool = Field(..., description="Whether action satisfies all validation rules")
    failure_code: Optional[ActionValidationFailureCode] = Field(default=None, description="Failure code if invalid")
    failure_reason: Optional[str] = Field(default=None, description="Diagnostic reason if invalid")
    validated_action: Optional[AbstractAction] = Field(default=None, description="Normalized validated action")


class AgentActionValidator:
    """Validator enforcing strict action protocol, parameter schemas, and coordinate boundaries."""

    INTERACTIVE_ACTION_TYPES: Set[AbstractActionType] = {
        AbstractActionType.CLICK,
        AbstractActionType.DOUBLE_CLICK,
        AbstractActionType.RIGHT_CLICK,
        AbstractActionType.TYPE_TEXT,
        AbstractActionType.SELECT_OPTION,
        AbstractActionType.DRAW_STROKES,
        AbstractActionType.DRAG,
    }

    FORBIDDEN_COORDINATE_KEYS: Set[str] = {
        "x", "y", "screen_x", "screen_y", "coord_x", "coord_y", "pos_x", "pos_y",
        "screen_position", "coordinates", "raw_x", "raw_y", "bbox", "bounding_box"
    }

    @classmethod
    def validate(
        cls,
        action: Any,
        available_capabilities: Optional[Set[str]] = None,
    ) -> ActionValidationResult:
        """Validate an action against the strict Agent Action Protocol."""
        if action is None:
            return ActionValidationResult(
                is_valid=False,
                failure_code=ActionValidationFailureCode.INVALID_ACTION,
                failure_reason="Action cannot be None",
            )

        # 1. Parse or validate into AbstractAction
        if isinstance(action, dict):
            # Check coordinate policy on raw dict first
            params = action.get("parameters", {})
            if isinstance(params, dict):
                found_coords = cls.FORBIDDEN_COORDINATE_KEYS.intersection(k.lower() for k in params.keys())
                if found_coords:
                    return ActionValidationResult(
                        is_valid=False,
                        failure_code=ActionValidationFailureCode.COORDINATE_POLICY_VIOLATION,
                        failure_reason=f"Action contains prohibited physical coordinates in parameters: {found_coords}",
                    )
            target = action.get("target") or action.get("semantic_target")
            if isinstance(target, dict):
                found_coords = cls.FORBIDDEN_COORDINATE_KEYS.intersection(k.lower() for k in target.keys())
                if found_coords:
                    return ActionValidationResult(
                        is_valid=False,
                        failure_code=ActionValidationFailureCode.COORDINATE_POLICY_VIOLATION,
                        failure_reason=f"Semantic target contains prohibited physical coordinates: {found_coords}",
                    )
            try:
                action_obj = AbstractAction.model_validate(action)
            except Exception as e:
                return ActionValidationResult(
                    is_valid=False,
                    failure_code=ActionValidationFailureCode.INVALID_ACTION,
                    failure_reason=f"Failed to parse action schema: {e}",
                )
        elif isinstance(action, AbstractAction):
            action_obj = action
        else:
            return ActionValidationResult(
                is_valid=False,
                failure_code=ActionValidationFailureCode.INVALID_ACTION,
                failure_reason=f"Unsupported action object type: {type(action)}",
            )

        # 2. Validate Action Type
        if not isinstance(action_obj.action_type, AbstractActionType):
            return ActionValidationResult(
                is_valid=False,
                failure_code=ActionValidationFailureCode.UNSUPPORTED_ACTION,
                failure_reason=f"Unsupported action type: {action_obj.action_type}",
            )

        # 3. Check for Coordinate Policy Violation in parameters
        if action_obj.parameters:
            found_coords = cls.FORBIDDEN_COORDINATE_KEYS.intersection(k.lower() for k in action_obj.parameters.keys())
            if found_coords:
                return ActionValidationResult(
                    is_valid=False,
                    failure_code=ActionValidationFailureCode.COORDINATE_POLICY_VIOLATION,
                    failure_reason=f"Action contains prohibited physical coordinates: {found_coords}",
                )

        # 4. Validate Semantic Target for Interactive Actions
        if action_obj.action_type in cls.INTERACTIVE_ACTION_TYPES:
            if action_obj.target is None and action_obj.action_type not in (
                AbstractActionType.TYPE_TEXT,
                AbstractActionType.DRAW_STROKES,
            ):
                return ActionValidationResult(
                    is_valid=False,
                    failure_code=ActionValidationFailureCode.MISSING_SEMANTIC_TARGET,
                    failure_reason=f"Action type {action_obj.action_type.value} requires a SemanticTarget",
                )

        # 5. Validate Action Parameters against Schema
        param_error = cls._validate_parameters_for_type(action_obj.action_type, action_obj.parameters)
        if param_error:
            return ActionValidationResult(
                is_valid=False,
                failure_code=ActionValidationFailureCode.INVALID_PARAMETERS,
                failure_reason=f"Parameter validation failed for {action_obj.action_type.value}: {param_error}",
            )

        # 6. Validate Outcome Contract
        if action_obj.action_type not in (
            AbstractActionType.COMPLETE_GOAL,
            AbstractActionType.ABORT_TASK,
            AbstractActionType.WAIT,
            AbstractActionType.WAIT_SETTLE,
        ):
            if not action_obj.outcome_contract and not action_obj.expected_effect:
                return ActionValidationResult(
                    is_valid=False,
                    failure_code=ActionValidationFailureCode.MISSING_OUTCOME_CONTRACT,
                    failure_reason=f"Action {action_obj.action_type.value} must declare an expected outcome contract",
                )

        # 7. Validate Capability Availability (if provided)
        if available_capabilities is not None:
            required_cap = cls._get_required_capability(action_obj.action_type)
            if required_cap and required_cap not in available_capabilities:
                return ActionValidationResult(
                    is_valid=False,
                    failure_code=ActionValidationFailureCode.CAPABILITY_UNAVAILABLE,
                    failure_reason=f"Required capability '{required_cap}' is unavailable",
                )

        return ActionValidationResult(
            is_valid=True,
            failure_code=ActionValidationFailureCode.VALID,
            validated_action=action_obj,
        )

    @classmethod
    def _validate_parameters_for_type(cls, action_type: AbstractActionType, params: Dict[str, Any]) -> Optional[str]:
        """Validate type-specific parameters."""
        try:
            if action_type == AbstractActionType.LAUNCH_APPLICATION:
                if not params.get("application_name") and not params.get("app_name") and not params.get("name"):
                    return "Missing required parameter 'application_name'"
            elif action_type == AbstractActionType.TYPE_TEXT:
                if "text" not in params and "query" not in params:
                    return "Missing required parameter 'text'"
            elif action_type == AbstractActionType.SEND_HOTKEY:
                if "hotkey" not in params and "keys" not in params and "key" not in params:
                    return "Missing required parameter 'hotkey' or 'keys'"
            elif action_type == AbstractActionType.SCROLL:
                direction = params.get("direction", "down")
                if direction not in ("up", "down", "left", "right"):
                    return f"Invalid scroll direction: '{direction}'"
            elif action_type == AbstractActionType.FILE_WRITE:
                if "path" not in params and "file_path" not in params:
                    return "Missing required parameter 'path'"
            elif action_type == AbstractActionType.FILE_READ:
                if "path" not in params and "file_path" not in params:
                    return "Missing required parameter 'path'"
            elif action_type == AbstractActionType.BROWSER_NAVIGATE:
                if "url" not in params:
                    return "Missing required parameter 'url'"
            elif action_type == AbstractActionType.DRAW_STROKES:
                strokes = params.get("strokes")
                if not strokes and not params.get("shape") and not params.get("target"):
                    return "DRAW_STROKES requires 'target' and normalized 'strokes' geometry"
                if strokes is not None:
                    if not isinstance(strokes, list):
                        return "Parameter 'strokes' must be a list of stroke point sequences"
                    for s_idx, stroke in enumerate(strokes):
                        if not isinstance(stroke, list):
                            return f"Stroke {s_idx} must be a list of 2-numeric points (u, v)"
                        for p_idx, pt in enumerate(stroke):
                            if isinstance(pt, dict):
                                return f"Stroke {s_idx} point {p_idx} cannot be a dictionary (raw coordinate dictionaries are prohibited)"
                            if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                                return f"Stroke {s_idx} point {p_idx} must be a 2-tuple of numeric coordinates (u, v)"
                            u, v = pt
                            if not isinstance(u, (int, float)) or not isinstance(v, (int, float)):
                                return f"Stroke {s_idx} point {p_idx} coordinates must be numbers"
                            if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0:
                                return f"Stroke {s_idx} point {p_idx} ({u}, {v}) violates normalized canvas bounds [0.0, 1.0]"
            return None
        except Exception as e:
            return str(e)

    @classmethod
    def _get_required_capability(cls, action_type: AbstractActionType) -> Optional[str]:
        """Map action type to required ORBIT capability name."""
        if action_type in (
            AbstractActionType.CLICK,
            AbstractActionType.DOUBLE_CLICK,
            AbstractActionType.RIGHT_CLICK,
            AbstractActionType.SCROLL,
            AbstractActionType.DRAW_STROKES,
            AbstractActionType.DRAG,
        ):
            return "pointer"
        elif action_type in (
            AbstractActionType.TYPE_TEXT,
            AbstractActionType.SEND_HOTKEY,
        ):
            return "keyboard"
        elif action_type in (
            AbstractActionType.LAUNCH_APPLICATION,
            AbstractActionType.FOCUS_WINDOW,
        ):
            return "workspace"
        elif action_type in (
            AbstractActionType.SCREENSHOT,
            AbstractActionType.READ_UI_ELEMENT,
            AbstractActionType.READ_OCR_TEXT,
        ):
            return "vision"
        elif action_type in (
            AbstractActionType.FILE_READ,
            AbstractActionType.FILE_WRITE,
            AbstractActionType.BROWSER_NAVIGATE,
            AbstractActionType.SPREADSHEET_READ,
            AbstractActionType.SPREADSHEET_WRITE,
        ):
            return "environment"
        return None
