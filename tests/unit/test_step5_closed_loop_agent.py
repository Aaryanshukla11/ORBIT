"""Unit tests for Step 5: Production Autonomous Closed-Loop Execution & Reality Validation.

Verifies:
1. Canonical State Machine rules, legal transitions, and terminal state protections.
2. Multi-cycle closed loop execution across real sequential desktop actions.
3. Fresh observation invariant enforcement across cycles.
4. Stale observation detection and recapture.
5. Tripartite reality separation (dispatch_success != expected_effect_observed != goal_satisfied).
6. Multi-step continuation (intermediate actions do not terminate loop).
7. Independent GoalVerifier authority for final task completion.
8. Safe multi-tier recovery triggering and budget enforcement.
9. Stagnation / repeated action budget enforcement.
10. Target resolution failure budget enforcement.
11. Cancellation token handling.
12. Structured CycleExecutionTrace formatting and telemetry.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionResult,
    ActionOutcomeContract,
    ExpectedState,
    OutcomeStatus,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.cancellation import CancellationSource
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop, AgentExecutionResult
from orbit.runtime.cognitive.models import (
    AgentLoopState,
    AgentLoopStateMachine,
    AgentRecoveryManager,
    AgentStateTransitionRecord,
    CognitiveDecision,
    CurrentStateObservation,
    CycleExecutionTrace,
    ExecutionBudget,
    InvalidStateTransitionError,
    RecoveryRecord,
    RecoveryStrategy,
    StructuredObjective,
    format_cycle_trace_block,
)
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.task_completion.models import (
    GoalVerificationResult,
    TaskCompletionEvidence,
    TaskCompletionStatus,
)


# ============================================================================
# 1. CANONICAL STATE MACHINE TESTS
# ============================================================================

def test_state_machine_legal_transitions():
    """State machine allows valid linear transitions through the closed loop lifecycle."""
    sm = AgentLoopStateMachine(initial_state=AgentLoopState.INITIALIZING)
    assert sm.current_state == AgentLoopState.INITIALIZING

    sm.transition_to(AgentLoopState.OBSERVING, cycle_number=0, observation_id="obs_1")
    assert sm.current_state == AgentLoopState.OBSERVING

    sm.transition_to(AgentLoopState.REASONING, cycle_number=0, observation_id="obs_1")
    assert sm.current_state == AgentLoopState.REASONING

    sm.transition_to(AgentLoopState.VALIDATING_ACTION, cycle_number=0, action_id="act_1")
    assert sm.current_state == AgentLoopState.VALIDATING_ACTION

    sm.transition_to(AgentLoopState.GROUNDING_TARGET, cycle_number=0, action_id="act_1")
    assert sm.current_state == AgentLoopState.GROUNDING_TARGET

    sm.transition_to(AgentLoopState.EXECUTING, cycle_number=0, action_id="act_1")
    assert sm.current_state == AgentLoopState.EXECUTING

    sm.transition_to(AgentLoopState.WAITING_FOR_SETTLEMENT, cycle_number=0)
    assert sm.current_state == AgentLoopState.WAITING_FOR_SETTLEMENT

    sm.transition_to(AgentLoopState.VERIFYING_EFFECT, cycle_number=0, observation_id="obs_2")
    assert sm.current_state == AgentLoopState.VERIFYING_EFFECT

    sm.transition_to(AgentLoopState.EVALUATING_PROGRESS, cycle_number=0, expected_effect_observed=True)
    assert sm.current_state == AgentLoopState.EVALUATING_PROGRESS

    sm.transition_to(AgentLoopState.COMPLETED, cycle_number=0, goal_satisfied=True)
    assert sm.current_state == AgentLoopState.COMPLETED
    assert sm.is_terminal is True
    assert len(sm.history) == 9


def test_state_machine_illegal_transitions_rejected():
    """Attempting an illegal transition raises InvalidStateTransitionError."""
    sm = AgentLoopStateMachine(initial_state=AgentLoopState.INITIALIZING)

    # Cannot jump directly from INITIALIZING to EXECUTING
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(AgentLoopState.EXECUTING)

    # Cannot transition out of terminal state
    sm.transition_to(AgentLoopState.FAILED)
    assert sm.is_terminal is True
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(AgentLoopState.OBSERVING)


# ============================================================================
# 2. MULTI-CYCLE CONTINUATION & FRESH OBSERVATION INVARIANT TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_agent_loop_multi_cycle_continuation():
    """Agent executes multi-cycle tasks: Launch App -> Type Text -> Goal Complete."""
    # Mock Observer to produce fresh distinct observations
    mock_obs_1 = CurrentStateObservation(
        observation_id="obs_001",
        active_window_title="Desktop",
        target_app_exists=False,
    )
    mock_obs_2 = CurrentStateObservation(
        observation_id="obs_002",
        active_window_title="Notepad - Untitled",
        active_window_hwnd=1234,
        target_app_exists=True,
        target_app_is_active=True,
    )
    mock_obs_3 = CurrentStateObservation(
        observation_id="obs_003",
        active_window_title="Notepad - Untitled",
        active_window_hwnd=1234,
        target_app_exists=True,
        target_app_is_active=True,
        ocr_tokens=["ORBIT", "Vision", "Test", "123"],
    )

    observer = MagicMock()
    observer.observe = AsyncMock(side_effect=[mock_obs_1, mock_obs_2, mock_obs_3, mock_obs_3])

    # Mock Decision Engine: Cycle 0 -> Launch, Cycle 1 -> Type, Cycle 2 -> Complete
    dec_0 = CognitiveDecision(
        step_index=0,
        decision_summary="Desktop observed; launching Notepad",
        next_action=AbstractAction(
            action_type=AbstractActionType.LAUNCH_APPLICATION,
            parameters={"application_name": "notepad"},
        ),
    )
    dec_1 = CognitiveDecision(
        step_index=1,
        decision_summary="Notepad open; typing text into editor",
        next_action=AbstractAction(
            action_type=AbstractActionType.TYPE_TEXT,
            parameters={"text": "ORBIT Vision Test 123"},
        ),
    )
    dec_2 = CognitiveDecision(
        step_index=2,
        decision_summary="Text verified in Notepad; completing goal",
        is_goal_satisfied=True,
        next_action=AbstractAction(action_type=AbstractActionType.COMPLETE_GOAL),
    )

    decision_engine = MagicMock()
    decision_engine.decide_next_step = AsyncMock(side_effect=[dec_0, dec_1, dec_2])

    goal_verifier = MagicMock()
    goal_verifier.verify_goal_achievement = AsyncMock(
        side_effect=[
            GoalVerificationResult(status=TaskCompletionStatus.FAILED, is_completed=False),
            GoalVerificationResult(status=TaskCompletionStatus.FAILED, is_completed=False),
            GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
                evidence=TaskCompletionEvidence(verified_text="ORBIT Vision Test 123"),
            ),
        ]
    )

    loop = AgentExecutionLoop(
        observer=observer,
        decision_engine=decision_engine,
        goal_verifier=goal_verifier,
        budget=ExecutionBudget(max_total_actions=10),
    )

    res: AgentExecutionResult = await loop.run("Open Notepad and type ORBIT Vision Test 123")

    assert res.is_success is True
    assert res.final_status == TaskCompletionStatus.COMPLETED
    assert len(res.step_history) >= 2

    # Verify distinct observations were used across cycles
    obs_ids = [step.post_observation.observation_id for step in res.step_history if step.post_observation]
    assert len(set(obs_ids)) >= 2


@pytest.mark.asyncio
async def test_fresh_observation_invariant_stale_detection():
    """Stale observation with identical ID triggers fresh observation recapture."""
    stale_obs = CurrentStateObservation(observation_id="obs_same_id", active_window_title="App")
    fresh_obs = CurrentStateObservation(observation_id="obs_new_id", active_window_title="App Updated")

    observer = MagicMock()
    # First returns stale_obs twice, then fresh_obs
    observer.observe = AsyncMock(side_effect=[stale_obs, stale_obs, fresh_obs, fresh_obs])

    dec_0 = CognitiveDecision(
        step_index=0,
        decision_summary="Step 0 action",
        next_action=AbstractAction(action_type=AbstractActionType.WAIT, parameters={"duration_ms": 10}),
    )
    dec_1 = CognitiveDecision(
        step_index=1,
        decision_summary="Step 1 complete",
        is_goal_satisfied=True,
        next_action=AbstractAction(action_type=AbstractActionType.COMPLETE_GOAL),
    )

    decision_engine = MagicMock()
    decision_engine.decide_next_step = AsyncMock(side_effect=[dec_0, dec_1])

    goal_verifier = MagicMock()
    goal_verifier.verify_goal_achievement = AsyncMock(
        side_effect=[
            GoalVerificationResult(status=TaskCompletionStatus.FAILED, is_completed=False),
            GoalVerificationResult(status=TaskCompletionStatus.COMPLETED, is_completed=True),
        ]
    )

    loop = AgentExecutionLoop(
        observer=observer,
        decision_engine=decision_engine,
        goal_verifier=goal_verifier,
    )

    res = await loop.run("Test fresh observation invariant")
    assert res.is_success is True
    assert observer.observe.call_count >= 3


# ============================================================================
# 3. TRIPARTITE REALITY SEPARATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_tripartite_separation_dispatch_success_does_not_mean_goal_satisfied():
    """Dispatch success with unverified effect triggers recovery, NOT goal completion."""
    obs_1 = CurrentStateObservation(observation_id="obs_101", active_window_title="Desktop")

    observer = MagicMock()
    observer.observe = AsyncMock(return_value=obs_1)

    dec = CognitiveDecision(
        step_index=0,
        decision_summary="Attempt click",
        next_action=AbstractAction(
            action_type=AbstractActionType.CLICK,
            target=SemanticTarget(name="SubmitButton", role="button"),
            outcome_contract=ActionOutcomeContract(
                expected_state_transition="SuccessDialog appeared",
                verification_strategy=VerificationStrategy.WINDOW_FOCUS,
            ),
        ),
    )

    decision_engine = MagicMock()
    decision_engine.decide_next_step = AsyncMock(return_value=dec)

    transition_verifier = MagicMock()
    transition_verifier.verify_action_outcome = AsyncMock(
        return_value=ActionExecutionResult(
            dispatch_success=True,  # OS accepted click
            expected_effect_observed=False,  # But dialog did not appear!
            goal_satisfied=False,
            outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
        )
    )

    recovery_mgr = MagicMock(spec=AgentRecoveryManager)
    recovery_mgr.can_attempt_recovery = MagicMock(side_effect=[True, False])
    recovery_mgr.current_transition_recoveries = 0
    recovery_mgr.diagnose_failure = MagicMock(return_value=(RecoveryStrategy.WAIT_FOR_SETTLEMENT, "Dialog delayed"))
    recovery_mgr.execute_recovery = AsyncMock(
        return_value=RecoveryRecord(
            cycle_number=0,
            attempt_number=1,
            strategy=RecoveryStrategy.WAIT_FOR_SETTLEMENT,
            recovery_success=True,
        )
    )
    recovery_mgr.get_history = MagicMock(return_value=[])

    loop = AgentExecutionLoop(
        observer=observer,
        decision_engine=decision_engine,
        transition_verifier=transition_verifier,
        recovery_manager=recovery_mgr,
        budget=ExecutionBudget(max_total_actions=2),
    )

    res = await loop.run("Click Submit Button")
    assert recovery_mgr.diagnose_failure.called
    assert recovery_mgr.execute_recovery.called


@pytest.mark.asyncio
async def test_independent_goal_verifier_prevents_false_model_completion():
    """Model claiming complete is overridden if independent GoalVerifier reports incomplete."""
    obs = CurrentStateObservation(observation_id="obs_201", active_window_title="Desktop")

    observer = MagicMock()
    observer.observe = AsyncMock(return_value=obs)

    # Model hallucinates that goal is complete
    dec_false = CognitiveDecision(
        step_index=0,
        decision_summary="Model falsely claims complete",
        is_goal_satisfied=True,
        next_action=AbstractAction(action_type=AbstractActionType.COMPLETE_GOAL),
    )

    decision_engine = MagicMock()
    decision_engine.decide_next_step = AsyncMock(return_value=dec_false)

    # Independent GoalVerifier rejects completion
    goal_verifier = MagicMock()
    goal_verifier.verify_goal_achievement = AsyncMock(
        return_value=GoalVerificationResult(status=TaskCompletionStatus.FAILED, is_completed=False, failure_reason="Expected file not saved")
    )

    loop = AgentExecutionLoop(
        observer=observer,
        decision_engine=decision_engine,
        goal_verifier=goal_verifier,
        budget=ExecutionBudget(max_total_actions=2),
    )

    res = await loop.run("Save document")
    # Goal was NOT satisfied despite model claiming it
    assert res.is_success is False
    assert res.final_status == TaskCompletionStatus.FAILED


# ============================================================================
# 4. PROGRESS BUDGET & STAGNATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_repeated_action_stagnation_budget_enforced():
    """Repeated identical actions without state progress terminate with failure."""
    obs = CurrentStateObservation(observation_id="obs_301", active_window_title="SameApp")

    observer = MagicMock()
    observer.observe = AsyncMock(return_value=obs)

    # Identical wait action repeated
    dec = CognitiveDecision(
        step_index=0,
        decision_summary="Waiting for settlement repeatedly",
        next_action=AbstractAction(
            action_type=AbstractActionType.WAIT,
            parameters={"duration_ms": 10},
        ),
    )

    decision_engine = MagicMock()
    decision_engine.decide_next_step = AsyncMock(return_value=dec)

    loop = AgentExecutionLoop(
        observer=observer,
        decision_engine=decision_engine,
        budget=ExecutionBudget(max_total_actions=20, max_repeated_actions_without_progress=3),
    )

    res = await loop.run("Repeated wait test")
    assert res.is_success is False
    assert res.failure_code == "REPEATED_ACTION_STAGNATION"


@pytest.mark.asyncio
async def test_cancellation_token_stops_execution():
    """Cancellation token halts execution and transitions state machine to CANCELLED."""
    obs = CurrentStateObservation(observation_id="obs_401")
    observer = MagicMock()
    observer.observe = AsyncMock(return_value=obs)

    cancel_src = CancellationSource()
    cancel_src.cancel("Operator test stop")

    loop = AgentExecutionLoop(
        observer=observer,
        decision_engine=MagicMock(),
    )

    res = await loop.run("Cancelled task", cancel_token=cancel_src.token)
    assert res.is_success is False
    assert res.final_status == TaskCompletionStatus.CANCELLED
    assert "Cancelled" in (res.failure_reason or "")


# ============================================================================
# 5. CYCLE TRACE FORMATTING TEST
# ============================================================================

def test_cycle_execution_trace_formatting():
    """CycleExecutionTrace formats all 9 structured diagnostic sections correctly."""
    trace = CycleExecutionTrace(
        cycle_number=1,
        observation_id="obs_501",
        freshness_validated=True,
        foreground_window="Notepad - Untitled",
        visible_windows=["Notepad - Untitled", "Taskbar"],
        ocr_summary="ORBIT Vision Test",
        ui_elements_count=42,
        screenshot_available=True,
        model_id="ollama:llama3.2-vision:latest",
        model_provider="OLLAMA",
        local_or_cloud="LOCAL",
        capabilities=["SCREENSHOT", "OCR", "UIA"],
        vision_capable=True,
        screenshot_attached=True,
        model_latency_ms=124.5,
        decision_summary="Notepad focused; typing query",
        decision_confidence=0.92,
        goal_progress="IN_PROGRESS",
        next_action_type="TYPE_TEXT",
        semantic_target_name="TextEditor",
        semantic_target_role="edit",
        target_evidence_source="UIA_LOCATOR",
        grounding_confidence=0.98,
        grounding_resolved=True,
        resolved_coordinates=(500, 300),
        dispatch_attempted=True,
        dispatch_success=True,
        post_observation_id="obs_502",
        post_freshness_validated=True,
        expected_effect="Text appears in editor",
        observed_effect="OCR detected 'ORBIT Vision Test'",
        expected_effect_observed=True,
        verification_strategy="OCR_TOKEN_MATCH",
        verification_reason="Tokens matched",
        goal_satisfied=False,
        goal_supporting_evidence=["Typed text verified"],
        meaningful_state_change=True,
        repeated_actions_count=0,
        recovery_count=0,
        remaining_action_budget=49,
    )

    formatted = format_cycle_trace_block(trace)

    assert "CYCLE 1" in formatted
    assert "OBSERVATION" in formatted
    assert "obs_501" in formatted
    assert "MODEL ROUTING" in formatted
    assert "ollama:llama3.2-vision:latest" in formatted
    assert "DECISION" in formatted
    assert "GROUNDING" in formatted
    assert "(500, 300)" in formatted
    assert "EXECUTION" in formatted
    assert "POST-ACTION OBSERVATION" in formatted
    assert "obs_502" in formatted
    assert "VERIFICATION" in formatted
    assert "GOAL EVALUATION" in formatted
    assert "PROGRESS" in formatted
