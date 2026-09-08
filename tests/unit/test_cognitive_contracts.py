"""Unit tests asserting architectural contracts and safety invariants for the Cognitive Engine."""

import pytest
from pydantic import ValidationError

from orbit.runtime.cognitive.models import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionResult,
    ActionOutcomeContract,
    ExecutionBudget,
    OutcomeStatus,
    SemanticTarget,
)


def test_abstract_action_forbids_physical_coordinates():
    """SAFETY INVARIANT: Cognitive layer must NEVER accept physical screen coordinates."""
    # Valid semantic action without coordinates
    valid_action = AbstractAction(
        action_type=AbstractActionType.CLICK_ELEMENT,
        target=SemanticTarget(name="Search", role="edit", context="Downloads"),
        parameters={"query": "test_file.txt"},
        outcome_contract=ActionOutcomeContract(expected_state_transition="search_focused"),
    )
    assert valid_action.target is not None
    assert valid_action.target.name == "Search"

    # Attempting to inject physical coordinates 'x' or 'y' must raise ValidationError
    with pytest.raises(ValidationError) as excinfo:
        AbstractAction(
            action_type=AbstractActionType.CLICK_ELEMENT,
            target=SemanticTarget(name="Search"),
            parameters={"x": 500, "y": 300},
        )
    assert "Cognitive AbstractAction parameters must NOT contain physical coordinates" in str(excinfo.value)


def test_action_execution_result_tripartite_distinction():
    """Tripartite distinction: Dispatch success != Expected effect observed != Goal achieved."""
    # Case 1: Command dispatched successfully, but expected effect was NOT observed
    res_unverified = ActionExecutionResult(
        dispatch_success=True,
        expected_effect_observed=False,
        outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
        error_message="Focus state unchanged after click",
    )
    assert res_unverified.dispatch_success is True
    assert res_unverified.expected_effect_observed is False
    assert res_unverified.outcome_status == OutcomeStatus.EFFECT_UNVERIFIED

    # Case 2: Command dispatched and effect verified
    res_verified = ActionExecutionResult(
        dispatch_success=True,
        expected_effect_observed=True,
        outcome_status=OutcomeStatus.EFFECT_VERIFIED,
    )
    assert res_verified.expected_effect_observed is True


def test_execution_budget_defaults():
    budget = ExecutionBudget()
    assert budget.max_total_actions == 50
    assert budget.max_repeated_actions_without_progress == 3
    assert budget.no_progress_timeout_sec == 30.0
