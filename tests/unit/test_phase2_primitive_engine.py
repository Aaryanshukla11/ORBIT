"""Unit tests for Phase 2: PrimitiveValidator, PrimitiveComposer, MultiEvidenceActionVerifier, and PrimitiveExecutionController."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionOutcomeContract,
    ActionValidationFailureCode,
    OutcomeStatus,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.cognitive.context_builder import StructuredAgentContext
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective, SubObjective
from orbit.runtime.cognitive.primitive_composer import PrimitiveComposer, ComposedPrimitiveSequence
from orbit.runtime.cognitive.primitive_execution_controller import (
    PrimitiveExecutionController,
    ControllerExecutionResult,
)
from orbit.runtime.cognitive.primitive_validator import PrimitiveValidator, PrimitiveValidationResult
from orbit.runtime.task_completion.multi_evidence_verifier import (
    MultiEvidenceActionVerifier,
    MultiEvidenceVerificationResult,
)


# ==============================================================================
# 1. PRIMITIVE VALIDATOR TESTS
# ==============================================================================

def test_primitive_validator_accepts_valid_canonical_action():
    validator = PrimitiveValidator()
    action = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        parameters={"application_name": "notepad"},
        target=SemanticTarget(name="notepad", role="application"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="notepad_focused"),
        expected_effect="Notepad opened and focused",
    )
    res = validator.validate_action(action)
    assert res.is_valid is True
    assert res.failure_code == ActionValidationFailureCode.VALID


def test_primitive_validator_rejects_physical_coordinates():
    validator = PrimitiveValidator()
    # Direct coordinate attempt in parameters
    action_dict = {
        "action_type": "CLICK",
        "target": {"name": "Submit", "role": "button"},
        "parameters": {"x": 500, "y": 300},
        "outcome_contract": {"expected_state_transition": "submitted"},
    }
    res = validator.validate_action(action_dict)
    assert res.is_valid is False
    assert res.failure_code == ActionValidationFailureCode.COORDINATE_POLICY_VIOLATION


def test_primitive_validator_rejects_interactive_click_without_target():
    validator = PrimitiveValidator()
    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        parameters={},
        target=None,
        outcome_contract=ActionOutcomeContract(expected_state_transition="clicked"),
        expected_effect="Click something",
    )
    res = validator.validate_action(action)
    assert res.is_valid is False
    assert res.failure_code == ActionValidationFailureCode.MISSING_SEMANTIC_TARGET


def test_primitive_validator_rejects_missing_outcome_contract():
    validator = PrimitiveValidator()
    action = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        parameters={"text": "hello"},
        target=SemanticTarget(name="search_input", role="edit"),
        outcome_contract=None,
        expected_effect="",
    )
    res = validator.validate_action(action)
    assert res.is_valid is False
    assert res.failure_code == ActionValidationFailureCode.MISSING_OUTCOME_CONTRACT


# ==============================================================================
# 2. PRIMITIVE COMPOSER TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_primitive_composer_fallback_generates_canonical_primitives():
    composer = PrimitiveComposer()
    obj = StructuredObjective(
        raw_prompt="open notepad and type hello",
        user_goal="open notepad and type hello",
        end_condition="notepad_has_hello",
    )
    context = StructuredAgentContext(active_goal="open notepad and type hello")

    seq: ComposedPrimitiveSequence = await composer.compose(
        objective=obj,
        sub_objective=SubObjective(title="open notepad"),
        context=context,
    )
    assert len(seq.actions) >= 1
    act = seq.actions[0]
    assert act.action_type == AbstractActionType.LAUNCH_APPLICATION
    assert act.parameters["application_name"] == "notepad"
    assert act.outcome_contract is not None


# ==============================================================================
# 3. MULTI-EVIDENCE VERIFIER TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_multi_evidence_verifier_verifies_window_launch():
    verifier = MultiEvidenceActionVerifier()
    action = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        parameters={"application_name": "notepad"},
        target=SemanticTarget(name="notepad", role="application"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="notepad_active"),
    )
    pre = CurrentStateObservation(observation_id="obs_1", active_window_title="Desktop")
    post = CurrentStateObservation(observation_id="obs_2", active_window_title="Notepad - Untitled")

    res: MultiEvidenceVerificationResult = await verifier.verify_action_effect(action, pre, post)
    assert res.is_verified is True
    assert res.outcome_status == OutcomeStatus.EFFECT_VERIFIED
    assert "WIN32_FOREGROUND" in res.evidence_sources


@pytest.mark.asyncio
async def test_multi_evidence_verifier_rejects_unobserved_text():
    verifier = MultiEvidenceActionVerifier()
    action = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        parameters={"text": "ConfidentialPassword123"},
        target=SemanticTarget(name="password_box", role="edit"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="password_entered"),
    )
    pre = CurrentStateObservation(observation_id="obs_1")
    post = CurrentStateObservation(observation_id="obs_2", ocr_tokens=["Username", "Submit"])

    res: MultiEvidenceVerificationResult = await verifier.verify_action_effect(action, pre, post)
    assert res.is_verified is False
    assert res.outcome_status == OutcomeStatus.EFFECT_UNVERIFIED


# ==============================================================================
# 4. PRIMITIVE EXECUTION CONTROLLER TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_execution_controller_enforces_single_path_and_closed_loop():
    controller = PrimitiveExecutionController()

    action = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        parameters={"application_name": "calc"},
        target=SemanticTarget(name="calc", role="application"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="calculator_open"),
    )
    pre_obs = CurrentStateObservation(observation_id="obs_pre", active_window_title="Desktop")
    post_obs = CurrentStateObservation(observation_id="obs_post", active_window_title="Calculator")

    grounding_mock = AsyncMock(return_value=None)
    safety_mock = MagicMock(return_value=(True, None))
    dispatch_mock = AsyncMock(return_value=(True, None))
    observe_mock = AsyncMock(return_value=post_obs)

    result: ControllerExecutionResult = await controller.execute_primitive(
        action=action,
        pre_observation=pre_obs,
        objective=StructuredObjective(raw_prompt="open calc", user_goal="open calc", end_condition="calc_open"),
        grounding_fn=grounding_mock,
        safety_gate_fn=safety_mock,
        dispatch_fn=dispatch_mock,
        observe_fn=observe_mock,
    )

    assert result.should_continue is True
    assert result.execution_outcome.dispatch_success is True
    assert result.execution_outcome.expected_effect_observed is True
    assert result.post_observation.active_window_title == "Calculator"


@pytest.mark.asyncio
async def test_execution_controller_stops_sequence_if_verification_fails():
    controller = PrimitiveExecutionController()

    action = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        parameters={"application_name": "calc"},
        target=SemanticTarget(name="calc", role="application"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="calculator_open"),
    )
    pre_obs = CurrentStateObservation(observation_id="obs_pre", active_window_title="Desktop")
    # Observation does NOT show Calculator
    post_obs = CurrentStateObservation(observation_id="obs_post", active_window_title="Desktop")

    grounding_mock = AsyncMock(return_value=None)
    safety_mock = MagicMock(return_value=(True, None))
    dispatch_mock = AsyncMock(return_value=(True, None))
    observe_mock = AsyncMock(return_value=post_obs)

    result: ControllerExecutionResult = await controller.execute_primitive(
        action=action,
        pre_observation=pre_obs,
        objective=StructuredObjective(raw_prompt="open calc", user_goal="open calc", end_condition="calc_open"),
        grounding_fn=grounding_mock,
        safety_gate_fn=safety_mock,
        dispatch_fn=dispatch_mock,
        observe_fn=observe_mock,
    )

    # Guardrail 6: If verification fails, stop sequence (should_continue is False)
    assert result.should_continue is False
    assert result.execution_outcome.expected_effect_observed is False
    assert result.failure_report is not None
    assert result.failure_report["phase"] == "VERIFICATION"
