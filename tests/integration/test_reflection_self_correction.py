"""Integration test for Autonomous Reflection and Self-Correction (Phase 3F)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest

from orbit.contracts.capabilities import KeyboardCapability, PointerCapability, WorkspaceCapability
from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    OutcomeStatus,
    SemanticTarget,
)
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CognitiveStepResult,
    CurrentStateObservation,
    ExecutionBudget,
    StructuredObjective,
)
from orbit.runtime.cognitive.reflection import (
    CorrectionPlan,
    FailureRootCause,
    SelfCorrectionReflectionEngine,
)
from orbit.runtime.targeting.models import TargetResolutionResult, TargetResolutionStatus
from orbit.runtime.task_completion.models import (
    GoalVerificationResult,
    TaskCompletionEvidence,
    TaskCompletionStatus,
)


class ReflectiveDecisionEngine:
    """Decision engine that invokes SelfCorrectionReflectionEngine when action fails."""

    def __init__(self, reflection_engine: SelfCorrectionReflectionEngine) -> None:
        self.reflection_engine = reflection_engine
        self.correction_plan: CorrectionPlan | None = None

    async def decide_next_step(
        self,
        objective: StructuredObjective,
        observation: CurrentStateObservation,
        step_history: list[CognitiveStepResult],
        step_index: int,
        **kwargs,
    ) -> CognitiveDecision:
        # Check if last step failed
        if step_history and step_history[-1].execution_result and not step_history[-1].execution_result.expected_effect_observed:
            # Trigger deep reflection
            self.correction_plan = self.reflection_engine.diagnose_and_reflect(
                objective=objective,
                failed_step=step_history[-1],
                step_history=step_history,
                current_observation=observation,
            )
            # Dispatch top alternate action from correction plan
            alt_action = self.correction_plan.alternate_actions[0]
            return CognitiveDecision(
                decision_summary=f"Self-correction: {self.correction_plan.root_cause_explanation} -> Switching to {alt_action.action_type.value}",
                is_goal_satisfied=False,
                decision_confidence=0.95,
                next_action=alt_action,
            )

        if step_index == 0:
            # Step 0: Try standard GUI Click on Save
            return CognitiveDecision(
                decision_summary="Attempting GUI Click on Save button",
                is_goal_satisfied=False,
                decision_confidence=0.85,
                next_action=AbstractAction(
                    action_type=AbstractActionType.CLICK,
                    target=SemanticTarget(name="Save Document Button"),
                    expected_effect="Save completed",
                ),
            )

        # Step 2: Goal satisfied
        return CognitiveDecision(
            decision_summary="Objective fully accomplished",
            is_goal_satisfied=True,
            decision_confidence=1.0,
            next_action=AbstractAction(
                action_type=AbstractActionType.COMPLETE_GOAL,
                target=SemanticTarget(name="Done"),
                expected_effect="Task finished",
            ),
        )


@pytest.mark.asyncio
async def test_reflection_self_correction_closed_loop():
    """Verify that failure triggers reflection diagnosis and switches to verified alternate action."""
    reflection_engine = SelfCorrectionReflectionEngine()
    decision_engine = ReflectiveDecisionEngine(reflection_engine=reflection_engine)

    ws = MagicMock(spec=WorkspaceCapability)
    ws.set_focus_window = AsyncMock(return_value=True)

    kb = MagicMock(spec=KeyboardCapability)
    kb.press_key = AsyncMock()
    kb.release_key = AsyncMock()
    ptr = MagicMock(spec=PointerCapability)
    ptr.click = AsyncMock()

    from orbit.runtime.targeting.models import ResolvedTarget, SafeActionPoint, TargetBoundingBox, TargetEvidence

    bbox = TargetBoundingBox(left=100, top=50, right=200, bottom=90)
    safe_pt = SafeActionPoint(x=150, y=70, bounding_box=bbox, desktop_generation_id=1)
    res = ResolvedTarget(
        target_id="tgt_save_btn",
        bounding_box=bbox,
        safe_point=safe_pt,
        confidence=0.95,
        evidence=TargetEvidence(source="UIA", identifier="save_btn", name="Save Document Button"),
        observation_id="obs_1",
        desktop_generation_id=1,
    )
    target_locator = MagicMock()
    target_locator.locate_target = AsyncMock(return_value=TargetResolutionResult(status=TargetResolutionStatus.RESOLVED, target=res))

    call_count = [0]
    def _create_obs(*args, **kwargs):
        call_count[0] += 1
        return CurrentStateObservation(
            observation_id=f"obs_refl_{call_count[0]}",
            active_window_hwnd=555,
            active_window_title="Text Editor",
            ocr_tokens=["File", "Edit", "Save"],
        )

    obs_mock = MagicMock()
    obs_mock.observe = AsyncMock(side_effect=_create_obs)

    # Transition verifier: fails initial GUI Click, succeeds subsequent hotkey
    async def _mock_trans_verify(action, **kwargs):
        if action.action_type == AbstractActionType.CLICK:
            return ActionExecutionOutcome(
                action_id=action.action_id,
                dispatch_success=True,
                expected_effect_observed=False,
                goal_satisfied=False,
                outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
                error_message="Click on Save Document Button had no effect",
            )
        # Hotkey Ctrl+S succeeds
        return ActionExecutionOutcome(
            action_id=action.action_id,
            dispatch_success=True,
            expected_effect_observed=True,
            goal_satisfied=False,
            outcome_status=OutcomeStatus.EFFECT_VERIFIED,
        )

    trans_verifier = MagicMock()
    trans_verifier.verify_action_outcome = AsyncMock(side_effect=_mock_trans_verify)

    async def _mock_verify_goal(task_id, objective, current_observation, step_history, **kwargs):
        if len(step_history) >= 2:
            return GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
                evidence=TaskCompletionEvidence(application_name="editor", application_is_open=True),
            )
        return GoalVerificationResult(status=TaskCompletionStatus.PARTIALLY_COMPLETED, is_completed=False)

    goal_verifier = MagicMock()
    goal_verifier.verify_goal_achievement = AsyncMock(side_effect=_mock_verify_goal)

    loop = AgentExecutionLoop(
        decision_engine=decision_engine,
        workspace=ws,
        keyboard=kb,
        pointer=ptr,
        target_locator=target_locator,
        goal_verifier=goal_verifier,
        observer=obs_mock,
        transition_verifier=trans_verifier,
        budget=ExecutionBudget(max_total_actions=5, timeout_seconds=10.0),
    )

    result = await loop.run("Save active file in editor")

    assert result.is_success is True
    # Verify reflection was executed and diagnosed UNRESPONSIVE_UI
    assert decision_engine.correction_plan is not None
    assert decision_engine.correction_plan.root_cause == FailureRootCause.UNRESPONSIVE_UI
    assert decision_engine.correction_plan.alternate_actions[0].parameters.get("hotkey") == "Ctrl+S"
