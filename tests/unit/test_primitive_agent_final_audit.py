"""Comprehensive Final Implementation Audit Test Suite.

Audits and proves:
- PART 3: Coordinate Isolation Invariant (No coordinates in Cognitive/LLM layer; SafeActionPoint after grounding).
- PART 4: Closed-Loop Invariant (N -> dispatch -> observe -> verify -> N+1).
- PART 5: Fail-Closed Invariants (Missing components, failed grounding, unverified outcomes explicitly fail).
- PART 6: Verifier Invariants (Contract-driven multi-evidence verification; no generic weighted score declaring success).
- PART 7: Provider Semantic Compatibility (CSV provider availability does NOT imply Excel-specific task feasibility).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionOutcomeContract,
    OutcomeStatus,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.agent.grounding_validator import GroundingValidator
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CurrentStateObservation,
    StructuredObjective,
    SubObjective,
)
from orbit.runtime.cognitive.primitive_composer import PrimitiveComposer
from orbit.runtime.cognitive.primitive_execution_controller import (
    ControllerExecutionResult,
    PrimitiveExecutionController,
)
from orbit.runtime.cognitive.primitive_validator import (
    ActionValidationFailureCode,
    PrimitiveValidator,
)
from orbit.runtime.cognitive.runtime_feasibility import RuntimeFeasibilityEvaluator
from orbit.runtime.environment.registry import (
    EnvironmentProviderRegistry,
    get_default_environment_registry,
)
from orbit.runtime.environment.spreadsheet_providers import CsvSpreadsheetProvider
from orbit.runtime.targeting.models import ResolvedTarget, SafeActionPoint, TargetBoundingBox
from orbit.runtime.task_completion.multi_evidence_verifier import (
    MultiEvidenceActionVerifier,
    MultiEvidenceVerificationResult,
)
from orbit.runtime.world_model.model import AgentWorldModel


# ==============================================================================
# PART 3: COORDINATE AUDIT TESTS
# ==============================================================================

def test_semantic_target_strictly_rejects_physical_screen_coordinates():
    """Prove cognitive SemanticTarget rejects physical coordinates (x, y, screen_x, bbox)."""
    with pytest.raises(ValueError, match="CoordinatePolicyViolation"):
        SemanticTarget(name="search_btn", role="button", x=100, y=200)  # type: ignore[call-arg]

    with pytest.raises(ValueError, match="CoordinatePolicyViolation"):
        SemanticTarget(name="search_btn", role="button", screen_x=500, screen_y=600)  # type: ignore[call-arg]

    with pytest.raises(ValueError, match="CoordinatePolicyViolation"):
        SemanticTarget(name="canvas", role="canvas", bbox={"left": 10, "top": 20})  # type: ignore[call-arg]


def test_abstract_action_strictly_rejects_physical_coordinates_in_parameters():
    """Prove AbstractAction parameters reject physical coordinates."""
    with pytest.raises(ValueError, match="CoordinatePolicyViolation"):
        AbstractAction(
            action_type=AbstractActionType.CLICK,
            target=SemanticTarget(name="submit", role="button"),
            parameters={"x": 500, "y": 300},
            expected_effect="submitted",
        )

    with pytest.raises(ValueError, match="CoordinatePolicyViolation"):
        AbstractAction(
            action_type=AbstractActionType.CLICK,
            target=SemanticTarget(name="submit", role="button"),
            parameters={"screen_position": (100, 200)},
            expected_effect="submitted",
        )


@pytest.mark.asyncio
async def test_composer_cannot_produce_physical_coordinates():
    """Prove PrimitiveComposer outputs AbstractActions containing no screen coordinates."""
    from orbit.runtime.cognitive.context_builder import StructuredAgentContext
    composer = PrimitiveComposer()
    obj = StructuredObjective(raw_prompt="click search button", user_goal="click search", end_condition="done")
    context = StructuredAgentContext(active_goal="click search button")
    seq = await composer.compose(
        objective=obj,
        sub_objective=SubObjective(title="click search button"),
        context=context,
    )
    for act in seq.actions:
        assert act.target is not None or act.action_type in (AbstractActionType.WAIT, AbstractActionType.WAIT_SETTLE)
        if act.target:
            assert not hasattr(act.target, "x")
            assert not hasattr(act.target, "y")
        for key in act.parameters:
            assert key.lower() not in {"x", "y", "screen_x", "screen_y", "coord_x", "coord_y"}


def test_safe_action_point_created_only_after_grounding_validation():
    """Prove SafeActionPoint and physical coordinates pass strict validation."""
    validator = GroundingValidator(desktop_width=1920, desktop_height=1080, min_confidence=0.70)
    target = SemanticTarget(name="btn", role="button")

    # Outside screen bounds
    res_oob = validator.validate_grounding(target=target, candidate_coords=(2500, 500))
    assert res_oob.is_valid is False
    assert "outside desktop bounds" in res_oob.failure_reason

    # Negative coordinates
    res_neg = validator.validate_grounding(target=target, candidate_coords=(-10, 500))
    assert res_neg.is_valid is False

    # Low confidence
    from orbit.runtime.targeting.models import TargetEvidence
    bbox = TargetBoundingBox(left=50, top=50, right=150, bottom=150, width=100, height=100)
    ev = TargetEvidence(source="UI_AUTOMATION", identifier="btn")
    resolved_target = ResolvedTarget(
        target_id="tgt_low",
        bounding_box=bbox,
        safe_point=SafeActionPoint(x=100, y=100, bounding_box=bbox, desktop_generation_id=1),
        confidence=0.50,
        evidence=ev,
        observation_id="obs_1",
        desktop_generation_id=1,
    )
    res_low = validator.validate_grounding(target=target, resolved_target=resolved_target)
    assert res_low.is_valid is False
    assert "below safety threshold" in res_low.failure_reason

    # Valid grounded target
    bbox_valid = TargetBoundingBox(left=50, top=50, right=250, bottom=350, width=200, height=300)
    resolved_valid = ResolvedTarget(
        target_id="tgt_valid",
        bounding_box=bbox_valid,
        safe_point=SafeActionPoint(x=200, y=300, bounding_box=bbox_valid, desktop_generation_id=1),
        confidence=0.95,
        evidence=ev,
        observation_id="obs_1",
        desktop_generation_id=1,
    )
    res_valid = validator.validate_grounding(target=target, resolved_target=resolved_valid)
    assert res_valid.is_valid is True
    assert res_valid.validated_point == (200, 300)


# ==============================================================================
# PART 4: CLOSED-LOOP AUDIT TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_closed_loop_verified_success_allows_next_action():
    """1. verified success -> next action executes (should_continue is True)."""
    controller = PrimitiveExecutionController()
    action = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        parameters={"application_name": "notepad"},
        target=SemanticTarget(name="notepad", role="application"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="notepad_active"),
    )
    pre = CurrentStateObservation(observation_id="obs_1", active_window_title="Desktop")
    post = CurrentStateObservation(observation_id="obs_2", active_window_title="Notepad - Untitled")

    res = await controller.execute_primitive(
        action=action,
        pre_observation=pre,
        objective=StructuredObjective(raw_prompt="open notepad", user_goal="open notepad", end_condition="open"),
        grounding_fn=AsyncMock(return_value=None),
        safety_gate_fn=MagicMock(return_value=(True, None)),
        dispatch_fn=AsyncMock(return_value=(True, None)),
        observe_fn=AsyncMock(return_value=post),
    )
    assert res.should_continue is True
    assert res.execution_outcome.expected_effect_observed is True


@pytest.mark.asyncio
async def test_closed_loop_verification_failure_blocks_next_action():
    """2. verification failure -> next action does NOT execute (should_continue is False)."""
    controller = PrimitiveExecutionController()
    action = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        parameters={"application_name": "notepad"},
        target=SemanticTarget(name="notepad", role="application"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="notepad_active"),
    )
    pre = CurrentStateObservation(observation_id="obs_1", active_window_title="Desktop")
    # Post observation did NOT open Notepad
    post = CurrentStateObservation(observation_id="obs_2", active_window_title="Desktop")

    res = await controller.execute_primitive(
        action=action,
        pre_observation=pre,
        objective=StructuredObjective(raw_prompt="open notepad", user_goal="open notepad", end_condition="open"),
        grounding_fn=AsyncMock(return_value=None),
        safety_gate_fn=MagicMock(return_value=(True, None)),
        dispatch_fn=AsyncMock(return_value=(True, None)),
        observe_fn=AsyncMock(return_value=post),
    )
    assert res.should_continue is False
    assert res.execution_outcome.expected_effect_observed is False
    assert res.failure_report is not None
    assert res.failure_report["phase"] == "VERIFICATION"


@pytest.mark.asyncio
async def test_closed_loop_executor_failure_blocks_next_action():
    """4. executor failure -> next action does NOT execute (should_continue is False)."""
    controller = PrimitiveExecutionController()
    action = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        parameters={"application_name": "notepad"},
        target=SemanticTarget(name="notepad", role="application"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="notepad_active"),
    )
    pre = CurrentStateObservation(observation_id="obs_1")

    res = await controller.execute_primitive(
        action=action,
        pre_observation=pre,
        objective=StructuredObjective(raw_prompt="open notepad", user_goal="open notepad", end_condition="open"),
        grounding_fn=AsyncMock(return_value=None),
        safety_gate_fn=MagicMock(return_value=(True, None)),
        dispatch_fn=AsyncMock(return_value=(False, "Failed to spawn process")),
        observe_fn=AsyncMock(),
    )
    assert res.should_continue is False
    assert res.execution_outcome.dispatch_success is False
    assert res.execution_outcome.outcome_status == OutcomeStatus.DISPATCH_FAILED
    assert res.failure_report["phase"] == "DISPATCH"


# ==============================================================================
# PART 5: FAIL-CLOSED AUDIT TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_fail_closed_missing_target_for_click():
    """Missing target for CLICK must fail closed in validator."""
    validator = PrimitiveValidator()
    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=None,  # Missing target
        expected_effect="clicked",
    )
    val_res = validator.validate_action(action)
    assert val_res.is_valid is False
    assert val_res.failure_code == ActionValidationFailureCode.MISSING_SEMANTIC_TARGET


@pytest.mark.asyncio
async def test_fail_closed_failed_grounding():
    """Failed grounding must fail closed without dispatching."""
    controller = PrimitiveExecutionController()
    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="ghost_button", role="button"),
        expected_effect="clicked",
    )
    pre = CurrentStateObservation(observation_id="obs_1")

    # Grounding returns None (unresolved)
    grounding_fn = AsyncMock(return_value=None)
    dispatch_fn = AsyncMock()

    res = await controller.execute_primitive(
        action=action,
        pre_observation=pre,
        objective=StructuredObjective(raw_prompt="click", user_goal="click", end_condition="clicked"),
        grounding_fn=grounding_fn,
        safety_gate_fn=MagicMock(return_value=(True, None)),
        dispatch_fn=dispatch_fn,
        observe_fn=AsyncMock(),
    )
    assert res.should_continue is False
    assert res.execution_outcome.dispatch_success is False
    assert res.execution_outcome.failure_code == "TARGET_GROUNDING_FAILED"
    # Prove executor dispatch was NEVER called
    dispatch_fn.assert_not_called()


@pytest.mark.asyncio
async def test_fail_closed_failed_safety_gate():
    """Failed safety gate must fail closed without dispatching."""
    controller = PrimitiveExecutionController()
    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="dangerous_btn", role="button"),
        expected_effect="clicked",
    )
    pre = CurrentStateObservation(observation_id="obs_1")

    grounding_fn = AsyncMock(return_value=(500, 300))
    safety_fn = MagicMock(return_value=(False, "Safety gate rejected: blocked zone"))
    dispatch_fn = AsyncMock()

    res = await controller.execute_primitive(
        action=action,
        pre_observation=pre,
        objective=StructuredObjective(raw_prompt="click", user_goal="click", end_condition="clicked"),
        grounding_fn=grounding_fn,
        safety_gate_fn=safety_fn,
        dispatch_fn=dispatch_fn,
        observe_fn=AsyncMock(),
    )
    assert res.should_continue is False
    assert res.execution_outcome.dispatch_success is False
    assert res.execution_outcome.failure_code == "SAFETY_GATE_BLOCKED"
    # Prove executor dispatch was NEVER called
    dispatch_fn.assert_not_called()


@pytest.mark.asyncio
async def test_fail_closed_missing_expected_effect():
    """Missing expected effect and outcome contract must fail closed in validator."""
    validator = PrimitiveValidator()
    action = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        parameters={"text": "hello"},
        target=SemanticTarget(name="box", role="edit"),
        outcome_contract=None,
        expected_effect="",
    )
    val_res = validator.validate_action(action)
    assert val_res.is_valid is False
    assert val_res.failure_code == ActionValidationFailureCode.MISSING_OUTCOME_CONTRACT


# ==============================================================================
# PART 6: VERIFIER AUDIT TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_verifier_stale_screenshot_fails_verification():
    """Stale screenshot (identical observation IDs) must fail verification."""
    verifier = MultiEvidenceActionVerifier()
    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="btn", role="button"),
        expected_effect="dialog_open",
    )
    obs = CurrentStateObservation(observation_id="same_id", active_window_title="App")
    res = await verifier.verify_action_effect(action=action, pre_obs=obs, post_obs=obs)
    assert res.is_verified is False
    assert res.outcome_status == OutcomeStatus.EFFECT_UNVERIFIED
    assert "STALE_OBSERVATION_CHECK" in res.evidence_sources


@pytest.mark.asyncio
async def test_verifier_unrelated_visual_change_or_background_animation_does_not_verify_click():
    """Unrelated visual change / observation advancement alone must NOT verify arbitrary clicks."""
    verifier = MultiEvidenceActionVerifier()
    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="save_button", role="button"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="save_dialog_open"),
    )
    pre = CurrentStateObservation(observation_id="obs_pre", active_window_title="Editor", perceived_elements_count=5)
    # Different ID (observation advanced), but active window, UI elements, and OCR remain identical
    post = CurrentStateObservation(observation_id="obs_post", active_window_title="Editor", perceived_elements_count=5, ocr_tokens=["Editor", "File"])

    res = await verifier.verify_action_effect(action=action, pre_obs=pre, post_obs=post)
    assert res.is_verified is False
    assert res.outcome_status == OutcomeStatus.EFFECT_UNVERIFIED


@pytest.mark.asyncio
async def test_verifier_subtle_click_with_no_pixel_delta_verifies_via_uia_focus():
    """Subtle click that changes UIA focus without global pixel delta verifies via UIA delta."""
    verifier = MultiEvidenceActionVerifier()
    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="input_box", role="edit"),
        expected_effect="input_box_focused",
    )
    pre = CurrentStateObservation(
        observation_id="obs_pre",
        active_window_title="Form",
        raw_evidence={"focused_element_id": "submit_btn"},
    )
    post = CurrentStateObservation(
        observation_id="obs_post",
        active_window_title="Form",
        raw_evidence={"focused_element_id": "input_box"},
    )

    res = await verifier.verify_action_effect(action=action, pre_obs=pre, post_obs=post)
    assert res.is_verified is True
    assert res.outcome_status == OutcomeStatus.EFFECT_VERIFIED
    assert "UIA_FOCUSED_ELEMENT_DELTA" in res.evidence_sources


@pytest.mark.asyncio
async def test_verifier_wrong_target_click_rejected():
    """Click that fails to trigger expected outcome contract is rejected."""
    verifier = MultiEvidenceActionVerifier()
    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="submit", role="button"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="submission_success"),
    )
    pre = CurrentStateObservation(observation_id="obs_1", active_window_title="App")
    post = CurrentStateObservation(observation_id="obs_2", active_window_title="App", ocr_tokens=["Error", "Try Again"])

    res = await verifier.verify_action_effect(action=action, pre_obs=pre, post_obs=post)
    assert res.is_verified is False
    assert res.outcome_status == OutcomeStatus.EFFECT_UNVERIFIED


@pytest.mark.asyncio
async def test_verifier_drawing_unmodified_canvas_rejected():
    """Drawing that changes pixels outside canvas but leaves canvas blank is rejected."""
    verifier = MultiEvidenceActionVerifier()
    action = AbstractAction(
        action_type=AbstractActionType.DRAW_STROKES,
        parameters={"shape": "cube"},
        target=SemanticTarget(name="canvas", role="canvas"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="cube_drawn"),
    )
    pre = CurrentStateObservation(observation_id="obs_1", canvas_status="BLANK")
    # Even if observation advanced, canvas remains BLANK
    post = CurrentStateObservation(observation_id="obs_2", canvas_status="BLANK")

    res = await verifier.verify_action_effect(action=action, pre_obs=pre, post_obs=post)
    assert res.is_verified is False
    assert res.outcome_status == OutcomeStatus.EFFECT_UNVERIFIED


# ==============================================================================
# PART 7: PROVIDER SEMANTIC COMPATIBILITY TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_provider_availability_does_not_imply_excel_semantic_feasibility():
    """CSV provider availability must NOT imply that an operation requiring Excel-specific behavior is feasible."""
    registry = EnvironmentProviderRegistry()
    csv_provider = CsvSpreadsheetProvider()
    # Register ONLY CSV provider
    registry.register(AbstractActionType.SPREADSHEET_WRITE, csv_provider, priority=100)

    evaluator = RuntimeFeasibilityEvaluator(check_network=False)
    world = AgentWorldModel()

    # 1. Plain tabular CSV operation is feasible
    plain_sub = SubObjective(title="write data to spreadsheet", description="export rows to data.csv")
    plain_res = await evaluator.evaluate(sub_objective=plain_sub, world_model=world, provider_registry=registry)
    assert plain_res.is_feasible is True

    # 2. Excel-specific macro / formula calculation operation is NOT feasible with only CSV provider
    excel_sub = SubObjective(
        title="create workbook with excel formula",
        description="insert formula calculation =SUM(A1:A10) and execute vba macro",
    )
    excel_res = await evaluator.evaluate(sub_objective=excel_sub, world_model=world, provider_registry=registry)
    assert excel_res.is_feasible is False
    assert "requires Excel-specific functionality" in excel_res.blocking_reason
    assert "excel_native_provider" in excel_res.missing_resources
