"""Unit tests for Step 2: Strict Agent Action Protocol & Execution Contracts.

Tests:
1. Action Schema Validation
2. Coordinate Isolation & Security Boundary
3. AbstractAction -> TargetLocator -> ResolvedAction Boundary
4. Tripartite Outcome Separation (dispatch_success != expected_effect_observed != goal_satisfied)
"""

import pytest
from pydantic import ValidationError

from orbit.runtime.agent.contracts import (
    AbortTaskParams,
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionOutcomeContract,
    ActionValidationFailureCode,
    ActionValidationResult,
    AgentActionValidator,
    ClickParams,
    CompleteGoalParams,
    DrawStrokesParams,
    ExpectedState,
    FocusWindowParams,
    LaunchApplicationParams,
    OutcomeStatus,
    ResolvedAction,
    SemanticTarget,
    SendHotkeyParams,
    TypeTextParams,
    VerificationStrategy,
)
from orbit.runtime.targeting.models import SafeActionPoint, TargetBoundingBox


# ==============================================================================
# 1. ACTION SCHEMA VALIDATION
# ==============================================================================

def test_valid_abstract_actions_pass_validation():
    """Verify that all standard valid actions pass AgentActionValidator."""
    # 1. Launch App
    launch_act = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        target=SemanticTarget(name="Notepad", role="application"),
        parameters={"application_name": "notepad.exe"},
        outcome_contract=ActionOutcomeContract(
            expected_state_transition="notepad_window_visible",
            verification_strategy=VerificationStrategy.WIN32_WINDOW,
            expected_window_title="Notepad",
        ),
    )
    res = AgentActionValidator.validate(launch_act)
    assert res.is_valid is True
    assert res.failure_code == ActionValidationFailureCode.VALID

    # 2. Click Element
    click_act = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="File", role="menu item", context="Notepad"),
        parameters={"button": "left"},
        outcome_contract=ActionOutcomeContract(
            expected_state_transition="file_menu_expanded",
            verification_strategy=VerificationStrategy.UIA_STATE,
        ),
    )
    res = AgentActionValidator.validate(click_act)
    assert res.is_valid is True

    # 3. Type Text
    type_act = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        target=SemanticTarget(name="Text Editor", role="document", context="Notepad"),
        parameters={"text": "Hello World", "press_enter": True},
        outcome_contract=ActionOutcomeContract(
            expected_state_transition="text_entered",
            verification_strategy=VerificationStrategy.UIA_TEXT,
            expected_text="Hello World",
        ),
    )
    res = AgentActionValidator.validate(type_act)
    assert res.is_valid is True

    # 4. Draw Strokes
    draw_act = AbstractAction(
        action_type=AbstractActionType.DRAW_STROKES,
        target=SemanticTarget(name="Canvas", role="canvas", context="Paint"),
        parameters={"shape": "cube", "style": "outline"},
        outcome_contract=ActionOutcomeContract(
            expected_state_transition="cube_drawn_on_canvas",
            verification_strategy=VerificationStrategy.CANVAS_CHANGE,
        ),
    )
    res = AgentActionValidator.validate(draw_act)
    assert res.is_valid is True

    # 5. Complete Goal (terminal action, outcome contract optional)
    complete_act = AbstractAction(
        action_type=AbstractActionType.COMPLETE_GOAL,
        parameters={"summary": "Successfully calculated and written to notepad"},
    )
    res = AgentActionValidator.validate(complete_act)
    assert res.is_valid is True


def test_missing_semantic_target_fails_interactive_actions():
    """Interactive pointer actions (e.g. CLICK, DOUBLE_CLICK) must have a SemanticTarget."""
    click_no_target = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=None,
        parameters={"button": "left"},
        outcome_contract=ActionOutcomeContract(expected_state_transition="button_pressed"),
    )
    res = AgentActionValidator.validate(click_no_target)
    assert res.is_valid is False
    assert res.failure_code == ActionValidationFailureCode.MISSING_SEMANTIC_TARGET
    assert "requires a SemanticTarget" in res.failure_reason


def test_missing_outcome_contract_fails_non_terminal_actions():
    """Non-terminal actions must declare an expected outcome contract."""
    act_no_contract = AbstractAction(
        action_type=AbstractActionType.FOCUS_WINDOW,
        target=SemanticTarget(name="Calculator"),
        parameters={"application_name": "calc.exe"},
        outcome_contract=None,
        expected_effect="",
    )
    res = AgentActionValidator.validate(act_no_contract)
    assert res.is_valid is False
    assert res.failure_code == ActionValidationFailureCode.MISSING_OUTCOME_CONTRACT


def test_invalid_parameters_fail_validation():
    """Action parameters with missing required fields or invalid schemas must fail."""
    # Launch app without application_name
    invalid_launch = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        target=None,
        parameters={},
        outcome_contract=ActionOutcomeContract(expected_state_transition="app_opened"),
    )
    res = AgentActionValidator.validate(invalid_launch)
    assert res.is_valid is False
    assert res.failure_code == ActionValidationFailureCode.INVALID_PARAMETERS

    # Scroll with invalid direction
    invalid_scroll = AbstractAction(
        action_type=AbstractActionType.SCROLL,
        target=SemanticTarget(name="Feed"),
        parameters={"direction": "diagonal_nowhere"},
        outcome_contract=ActionOutcomeContract(expected_state_transition="scrolled"),
    )
    res = AgentActionValidator.validate(invalid_scroll)
    assert res.is_valid is False
    assert res.failure_code == ActionValidationFailureCode.INVALID_PARAMETERS


# ==============================================================================
# 2. COORDINATE ISOLATION & SECURITY BOUNDARY
# ==============================================================================

def test_semantic_target_strictly_rejects_physical_coordinates():
    """SAFETY INVARIANT: SemanticTarget must strictly reject coordinate-bearing keys."""
    # Direct x/y injection in target dict
    with pytest.raises(ValidationError) as excinfo:
        SemanticTarget.model_validate({"name": "Button", "x": 500, "y": 300})
    assert "CoordinatePolicyViolation" in str(excinfo.value)

    # Injected screen_x/screen_y or bounding box keys
    with pytest.raises(ValidationError) as excinfo:
        SemanticTarget.model_validate({"name": "Canvas", "width": 800, "height": 600})
    assert "CoordinatePolicyViolation" in str(excinfo.value)


def test_abstract_action_strictly_rejects_physical_coordinates():
    """SAFETY INVARIANT: AbstractAction parameters must strictly reject physical screen coordinates."""
    with pytest.raises(ValidationError) as excinfo:
        AbstractAction(
            action_type=AbstractActionType.CLICK,
            target=SemanticTarget(name="Submit"),
            parameters={"x": 1024, "y": 768},
            outcome_contract=ActionOutcomeContract(expected_state_transition="submitted"),
        )
    assert "CoordinatePolicyViolation" in str(excinfo.value)


def test_agent_action_validator_rejects_raw_coordinate_payloads():
    """AgentActionValidator must catch and reject raw dictionary payloads attempting coordinate bypass."""
    raw_payload = {
        "action_type": "CLICK",
        "target": {"name": "Button"},
        "parameters": {"screen_x": 450, "screen_y": 620},
        "expected_effect": "button_clicked",
    }
    res = AgentActionValidator.validate(raw_payload)
    assert res.is_valid is False
    assert res.failure_code == ActionValidationFailureCode.COORDINATE_POLICY_VIOLATION


# ==============================================================================
# 3. ABSTRACT ACTION -> TARGET LOCATOR -> RESOLVED ACTION BOUNDARY
# ==============================================================================

def test_resolved_action_construction_by_runtime():
    """Verify ResolvedAction represents the runtime-grounded execution contract."""
    # 1. AbstractAction from cognitive layer (NO coordinates)
    abstract = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="Search Button", role="button", application="Browser"),
        parameters={"button": "left"},
        outcome_contract=ActionOutcomeContract(
            expected_state_transition="search_results_visible",
            verification_strategy=VerificationStrategy.UIA_STATE,
        ),
    )
    assert "x" not in abstract.parameters
    assert "y" not in abstract.parameters

    # 2. Runtime Grounding produces ResolvedAction with physical SafeActionPoint
    bbox = TargetBoundingBox(left=200, top=100, right=280, bottom=140)
    safe_pt = SafeActionPoint(
        x=240,
        y=120,
        bounding_box=bbox,
        desktop_generation_id=1,
    )
    resolved = ResolvedAction(
        action_id=abstract.action_id,
        action_type=abstract.action_type,
        resolved_target_id="tgt_uia_9912",
        bounding_box=bbox,
        execution_point=safe_pt,
        parameters=abstract.parameters,
        outcome_contract=abstract.outcome_contract,
        resolution_confidence=0.98,
        grounding_source="UI_AUTOMATION",
    )

    assert resolved.action_id == abstract.action_id
    assert resolved.execution_point is not None
    assert resolved.execution_point.x == 240
    assert resolved.execution_point.y == 120
    assert resolved.grounding_source == "UI_AUTOMATION"


# ==============================================================================
# 4. TRIPARTITE OUTCOME SEPARATION
# ==============================================================================

def test_tripartite_outcome_dispatch_success_not_equal_effect_observed():
    """Case 1: Command dispatched (OS accepted SendInput), but expected effect NOT observed."""
    outcome_unverified = ActionExecutionOutcome(
        action_id="act_test_01",
        dispatch_success=True,
        expected_effect_observed=False,
        goal_satisfied=False,
        verification_strategy=VerificationStrategy.WINDOW_FOCUS,
        verification_reason="Active window remained Notepad; Calculator did not become foreground",
    )
    assert outcome_unverified.dispatch_success is True
    assert outcome_unverified.expected_effect_observed is False
    assert outcome_unverified.goal_satisfied is False
    assert outcome_unverified.outcome_status == OutcomeStatus.EFFECT_UNVERIFIED
    assert outcome_unverified.verified is False


def test_tripartite_outcome_effect_observed_not_equal_goal_satisfied():
    """Case 2: Immediate effect observed (e.g. 1 button clicked), but overall goal NOT yet satisfied."""
    outcome_step_ok = ActionExecutionOutcome(
        action_id="act_test_02",
        dispatch_success=True,
        expected_effect_observed=True,
        goal_satisfied=False,
        verification_strategy=VerificationStrategy.UIA_STATE,
        verification_reason="Button visually toggled state",
    )
    assert outcome_step_ok.dispatch_success is True
    assert outcome_step_ok.expected_effect_observed is True
    assert outcome_step_ok.goal_satisfied is False
    assert outcome_step_ok.outcome_status == OutcomeStatus.EFFECT_VERIFIED
    assert outcome_step_ok.verified is True


def test_tripartite_outcome_goal_satisfied():
    """Case 3: Final action produces verified goal completion."""
    outcome_completed = ActionExecutionOutcome(
        action_id="act_test_03",
        dispatch_success=True,
        expected_effect_observed=True,
        goal_satisfied=True,
        verification_strategy=VerificationStrategy.OCR_TEXT,
        verification_reason="Result 1050 confirmed in target buffer",
    )
    assert outcome_completed.dispatch_success is True
    assert outcome_completed.expected_effect_observed is True
    assert outcome_completed.goal_satisfied is True
    assert outcome_completed.outcome_status == OutcomeStatus.EFFECT_VERIFIED
