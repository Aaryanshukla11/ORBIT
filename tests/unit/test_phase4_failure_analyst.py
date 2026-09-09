"""Unit tests for Phase 4: CognitiveFailureAnalyst (Guardrail 9)."""

import pytest
from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionOutcomeContract,
    OutcomeStatus,
    SemanticTarget,
)
from orbit.runtime.cognitive.failure_analyst import (
    CognitiveFailureAnalyst,
    FailureCategory,
    FailureReport,
)
from orbit.runtime.cognitive.models import CurrentStateObservation


def test_failure_analyst_diagnoses_app_launch_failure():
    analyst = CognitiveFailureAnalyst()
    action = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        parameters={"application_name": "nonexistent_custom_app"},
        target=SemanticTarget(name="nonexistent_custom_app", role="application"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="app_open"),
    )
    pre = CurrentStateObservation(observation_id="obs_1", active_window_title="Desktop")
    post = CurrentStateObservation(observation_id="obs_2", active_window_title="Desktop", visible_windows=[])
    outcome = ActionExecutionOutcome(
        dispatch_success=True,
        expected_effect_observed=False,
        outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
        verification_reason="Application not found in visible windows",
    )

    report: FailureReport = analyst.analyze_failure(action, pre, post, outcome)
    assert report.category == FailureCategory.TARGET_NOT_FOUND
    assert "failed to launch" in report.diagnosis
    assert report.is_transient is False
    assert len(report.suggested_remediation_direction) > 0


def test_failure_analyst_diagnoses_typing_mismatch():
    analyst = CognitiveFailureAnalyst()
    action = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        parameters={"text": "hello_world"},
        target=SemanticTarget(name="search_box", role="edit"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="text_in_search"),
    )
    pre = CurrentStateObservation(observation_id="obs_1", active_window_title="Browser")
    post = CurrentStateObservation(observation_id="obs_2", active_window_title="Browser", ocr_tokens=["Search"])
    outcome = ActionExecutionOutcome(
        dispatch_success=True,
        expected_effect_observed=False,
        outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
        verification_reason="Typed text not found in post-action observation",
    )

    report: FailureReport = analyst.analyze_failure(action, pre, post, outcome)
    assert report.category == FailureCategory.TEXT_ENTRY_MISMATCH
    assert "was not accepted or rendered" in report.diagnosis
    assert report.is_transient is True


def test_failure_analyst_only_diagnoses_does_not_execute():
    """Guardrail 9: Verify FailureReport does NOT contain executable actions."""
    analyst = CognitiveFailureAnalyst()
    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        parameters={},
        target=SemanticTarget(name="LoginButton", role="button"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="logged_in"),
    )
    pre = CurrentStateObservation(observation_id="obs_1")
    post = CurrentStateObservation(observation_id="obs_2")
    outcome = ActionExecutionOutcome(
        dispatch_success=True,
        expected_effect_observed=False,
        outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
    )

    report: FailureReport = analyst.analyze_failure(action, pre, post, outcome)
    # The report must be a pure Pydantic model with diagnostic info, no next_action or executable actions
    assert hasattr(report, "diagnosis")
    assert hasattr(report, "suggested_remediation_direction")
    assert not hasattr(report, "next_action")
    assert not hasattr(report, "execute")
