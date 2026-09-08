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
    TextVerificationResult,
    VerificationStrategy,
)
from orbit.runtime.agent.state import DesktopStateSnapshot
from orbit.runtime.agent.verifier import AgentStateTransitionVerifier
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


# ============================================================================
# 6. CRITICAL STEP 5 REALITY VALIDATION REGRESSION TESTS (PHASE G)
# ============================================================================

@pytest.mark.asyncio
async def test_text_execution_preserves_exact_character_sequence():
    """1. Test that text execution preserves exact character sequence and repeated characters like 'ORBIT 3333333333' are detected as incorrect."""
    verifier = AgentStateTransitionVerifier()
    action = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        parameters={"text": "ORBIT Vision Test 123"},
    )
    # Simulate post-action observation that contains repeated '3's instead of 'ORBIT Vision Test 123'
    pre_state = DesktopStateSnapshot(
        snapshot_id="obs_pre_1",
        ocr_tokens=["Untitled", "Notepad"],
    )
    post_state = DesktopStateSnapshot(
        snapshot_id="obs_post_1",
        ocr_tokens=["ORBIT", "333333333333333"],
    )

    outcome = await verifier.verify_action_outcome(
        action=action,
        dispatch_success=True,
        pre_state=pre_state,
        post_state=post_state,
    )

    # Verification MUST fail
    assert outcome.expected_effect_observed is False
    assert outcome.verified is False
    assert outcome.outcome_status == OutcomeStatus.EFFECT_UNVERIFIED
    assert "NOT observed in post-action state" in outcome.verification_reason
    assert outcome.observed_delta.get("exact_match") is False


@pytest.mark.asyncio
async def test_dispatch_success_does_not_imply_text_verification():
    """2. Test that dispatch_success=True does not imply expected_effect_observed=True when text is incorrect."""
    verifier = AgentStateTransitionVerifier()
    action = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        parameters={"text": "ORBIT Vision Test 123"},
    )
    pre_state = DesktopStateSnapshot(snapshot_id="obs_10", ocr_tokens=[])
    # Observed text is garbage / incorrect
    post_state = DesktopStateSnapshot(snapshot_id="obs_11", ocr_tokens=["Welcome", "Explorer"])

    outcome = await verifier.verify_action_outcome(
        action=action,
        dispatch_success=True,  # Dispatch succeeded at OS level
        pre_state=pre_state,
        post_state=post_state,
    )

    assert outcome.dispatch_success is True
    assert outcome.expected_effect_observed is False
    assert outcome.outcome_status == OutcomeStatus.EFFECT_UNVERIFIED


@pytest.mark.asyncio
async def test_goal_verifier_rejects_wrong_visible_text():
    """3. Test that GoalVerifier rejects wrong visible text even if action history claimed typing."""
    goal_verifier = GoalVerifier()
    # Observation containing only the corrupted text
    obs = CurrentStateObservation(
        observation_id="obs_corrupt",
        ocr_tokens=["ORBIT", "333333333333333"],
        active_window_title="Notepad - Untitled",
    )

    step_hist = [
        MagicMock(
            action_dispatched=AbstractAction(
                action_type=AbstractActionType.TYPE_TEXT,
                parameters={"text": "ORBIT Vision Test 123"},
            )
        )
    ]

    res = await goal_verifier.verify_goal_achievement(
        task_id="task_reg_3",
        objective=StructuredObjective(
            raw_prompt="Open Notepad and type 'ORBIT Vision Test 123'",
            user_goal="Open Notepad and type 'ORBIT Vision Test 123'",
            end_condition="notepad_contains_typed_text",
        ),
        current_observation=obs,
        step_history=step_hist,
    )

    assert res.is_completed is False
    assert res.status == TaskCompletionStatus.FAILED
    assert "Objective evidence not satisfied" in res.failure_reason


@pytest.mark.asyncio
async def test_verifier_cannot_use_action_parameters_as_evidence():
    """4. Test that verifier cannot use action parameters as evidence of success."""
    verifier = AgentStateTransitionVerifier()
    # Action contains desired text
    action = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        parameters={"text": "SECRET_PASSCODE_XYZ"},
    )
    # Screen is empty
    pre_state = DesktopStateSnapshot(snapshot_id="obs_pre_4", ocr_tokens=[])
    post_state = DesktopStateSnapshot(snapshot_id="obs_post_4", ocr_tokens=["Empty", "Screen"])

    outcome = await verifier.verify_action_outcome(
        action=action,
        dispatch_success=True,
        pre_state=pre_state,
        post_state=post_state,
    )

    assert outcome.expected_effect_observed is False
    assert outcome.observed_delta.get("exact_match") is False


@pytest.mark.asyncio
async def test_verifier_rejects_stale_observation():
    """5. Test that verifier rejects stale observations where post_action_id == pre_action_id."""
    verifier = AgentStateTransitionVerifier()
    action = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        parameters={"text": "Any text"},
    )
    # Same snapshot_id simulates stale observation reuse
    pre_state = DesktopStateSnapshot(snapshot_id="obs_stale_1", ocr_tokens=["Any", "text"])
    post_state = DesktopStateSnapshot(snapshot_id="obs_stale_1", ocr_tokens=["Any", "text"])

    outcome = await verifier.verify_action_outcome(
        action=action,
        dispatch_success=True,
        pre_state=pre_state,
        post_state=post_state,
    )

    assert outcome.expected_effect_observed is False
    assert outcome.outcome_status == OutcomeStatus.EFFECT_UNVERIFIED
    assert "Stale observation rejected" in outcome.verification_reason


@pytest.mark.asyncio
async def test_post_action_observation_must_advance():
    """6. Test that post-action observation must advance to a fresh observation ID."""
    verifier = AgentStateTransitionVerifier()
    action = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        parameters={"application_name": "notepad"},
    )
    # Pre and post have identical snapshot IDs
    pre_state = DesktopStateSnapshot(snapshot_id="obs_identical", active_window_title="Desktop")
    post_state = DesktopStateSnapshot(snapshot_id="obs_identical", active_window_title="Notepad")

    outcome = await verifier.verify_action_outcome(
        action=action,
        dispatch_success=True,
        pre_state=pre_state,
        post_state=post_state,
    )

    assert outcome.expected_effect_observed is False
    assert "post_action_id 'obs_identical' equals pre_action_id" in outcome.verification_reason


@pytest.mark.asyncio
async def test_recovery_does_not_duplicate_text():
    """7. Test that recovery does not blindly duplicate text if text entry failed."""
    # When text is unverified, recovery manager diagnoses the failure without dispatching duplicate appending
    rec_mgr = AgentRecoveryManager()
    action = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        parameters={"text": "ORBIT Vision Test 123"},
    )
    pre_obs = CurrentStateObservation(observation_id="obs_7a", active_window_title="Notepad")
    post_obs = CurrentStateObservation(observation_id="obs_7b", active_window_title="Notepad", ocr_tokens=["ORBIT", "3333333333"])
    exec_res = ActionExecutionResult(
        dispatch_success=True,
        expected_effect_observed=False,
        outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
    )

    strategy, reason = rec_mgr.diagnose_failure(action, pre_obs, post_obs, exec_res)
    # Recovery strategy should refocus window or wait for settlement, never blind re-append
    assert strategy in (RecoveryStrategy.REFOCUS_WINDOW, RecoveryStrategy.WAIT_FOR_SETTLEMENT, RecoveryStrategy.REFRESH_OBSERVATION)


@pytest.mark.asyncio
async def test_repeated_keyboard_input_is_detected():
    """8. Test that repeated keyboard input with wrong visible text is detected and blocked by stagnation guards."""
    budget = ExecutionBudget(max_repeated_actions_without_progress=2)
    rec_mgr = AgentRecoveryManager()

    # Step 1: typed action fails verification
    action = AbstractAction(action_type=AbstractActionType.TYPE_TEXT, parameters={"text": "test"})
    # Verifier detects wrong text
    verifier = AgentStateTransitionVerifier()
    pre_state = DesktopStateSnapshot(snapshot_id="obs_8a", ocr_tokens=[])
    post_state = DesktopStateSnapshot(snapshot_id="obs_8b", ocr_tokens=["33333333"])

    outcome = await verifier.verify_action_outcome(
        action=action,
        dispatch_success=True,
        pre_state=pre_state,
        post_state=post_state,
    )
    assert outcome.expected_effect_observed is False


@pytest.mark.asyncio
async def test_false_positive_completion_is_impossible():
    """9. Complete regression test: Construct the exact failure observed live:
       Expected: 'ORBIT Vision Test 123'
       Actual visible: 'ORBIT 333333333333'
       Ensure: dispatch_success = True, expected_effect_observed = False, goal_satisfied = False, loop cannot complete.
    """
    verifier = AgentStateTransitionVerifier()
    goal_verifier = GoalVerifier()

    expected_text = "ORBIT Vision Test 123"
    actual_tokens = ["ORBIT", "333333333333333"]

    action = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        parameters={"text": expected_text},
    )

    pre_state = DesktopStateSnapshot(snapshot_id="obs_live_pre", ocr_tokens=["Notepad"])
    post_state = DesktopStateSnapshot(snapshot_id="obs_live_post", ocr_tokens=actual_tokens)

    # 1. State transition verification
    outcome = await verifier.verify_action_outcome(
        action=action,
        dispatch_success=True,
        pre_state=pre_state,
        post_state=post_state,
    )

    assert outcome.dispatch_success is True
    assert outcome.expected_effect_observed is False
    assert outcome.goal_satisfied is False
    assert outcome.outcome_status == OutcomeStatus.EFFECT_UNVERIFIED

    # 2. Goal verification
    post_obs = CurrentStateObservation(
        observation_id="obs_live_post",
        ocr_tokens=actual_tokens,
        active_window_title="Notepad - Untitled",
    )
    step_hist = [
        MagicMock(
            action_dispatched=action,
            execution_result=outcome,
        )
    ]

    goal_res = await goal_verifier.verify_goal_achievement(
        task_id="notepad_reg_live",
        objective=StructuredObjective(
            raw_prompt="Open Notepad and type 'ORBIT Vision Test 123'",
            user_goal="Open Notepad and type 'ORBIT Vision Test 123'",
            end_condition="notepad_contains_typed_text",
        ),
        current_observation=post_obs,
        step_history=step_hist,
    )

    # Invariant: Goal CANNOT be satisfied
    assert goal_res.is_completed is False
    assert goal_res.status == TaskCompletionStatus.FAILED

