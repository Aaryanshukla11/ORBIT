"""Integration test for Dynamic Subgoal DAG Execution and Branching (Phase 3B)."""

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
    CurrentStateObservation,
    ExecutionBudget,
    StructuredObjective,
)
from orbit.runtime.cognitive.subgoal_planner import DynamicSubgoalPlanner
from orbit.runtime.targeting.models import (
    ResolvedTarget,
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
    TargetResolutionResult,
    TargetResolutionStatus,
)
from orbit.runtime.task_completion.models import (
    GoalVerificationResult,
    TaskCompletionEvidence,
    TaskCompletionStatus,
)


class SubgoalPlannerMockEngine:
    """Decision engine driven by DynamicSubgoalPlanner with automatic branching."""

    def __init__(self, planner: DynamicSubgoalPlanner) -> None:
        self.planner = planner
        self.attempt = 0

    async def decide_next_step(
        self,
        objective: StructuredObjective,
        observation: CurrentStateObservation,
        step_history: list,
        step_index: int,
        **kwargs,
    ) -> CognitiveDecision:
        schedulable = self.planner.get_schedulable_subgoals(observation)
        if not schedulable:
            if self.planner.is_all_completed():
                return CognitiveDecision(
                    decision_summary="All subgoals satisfied. Concluding task.",
                    is_goal_satisfied=True,
                    decision_confidence=1.0,
                    next_action=AbstractAction(
                        action_type=AbstractActionType.COMPLETE_GOAL,
                        target=SemanticTarget(name="Done"),
                        expected_effect="Goal accomplished",
                    ),
                )
            # Replan or fail
            return CognitiveDecision(
                decision_summary="No schedulable subgoals remaining.",
                is_goal_satisfied=False,
                decision_confidence=0.5,
                next_action=AbstractAction(
                    action_type=AbstractActionType.WAIT,
                    parameters={"duration": 0.5},
                    expected_effect="Wait for UI update",
                ),
            )

        curr_node = schedulable[0]
        self.planner.mark_in_progress(curr_node.node_id)

        if curr_node.branch_id == "main":
            # Main branch action
            return CognitiveDecision(
                decision_summary=f"Executing main branch subgoal: {curr_node.title}",
                is_goal_satisfied=False,
                decision_confidence=0.9,
                next_action=AbstractAction(
                    action_type=AbstractActionType.CLICK,
                    target=SemanticTarget(name="Toolbar Save Button"),
                    expected_effect="File saved via toolbar button",
                ),
            )
        else:
            # Fallback branch action (Hotkey Ctrl+S)
            return CognitiveDecision(
                decision_summary=f"Executing fallback branch subgoal: {curr_node.title}",
                is_goal_satisfied=False,
                decision_confidence=0.95,
                next_action=AbstractAction(
                    action_type=AbstractActionType.SEND_HOTKEY,
                    parameters={"hotkey": "Ctrl+S"},
                    expected_effect="File saved via hotkey fallback",
                ),
            )


@pytest.mark.asyncio
async def test_dynamic_subgoal_branching_and_execution():
    """Verify that a subgoal execution failure triggers rollback and switches to fallback branch."""
    planner = DynamicSubgoalPlanner()

    # Step 1: Open Document (shared root)
    n_root = planner.create_node(title="Open Editor", branch_id="main")
    # Step 2: Main branch (Toolbar Save - fails)
    n_main_save = planner.create_node(
        title="Toolbar Save",
        dependencies=[n_root.node_id],
        branch_id="main",
        max_retries=1,
    )
    # Step 2 alt: Fallback branch (Hotkey Save - succeeds)
    n_fall_save = planner.create_node(
        title="Hotkey Save",
        dependencies=[n_root.node_id],
        branch_id="fallback_hotkey",
        is_alternate_branch=True,
    )

    decision_engine = SubgoalPlannerMockEngine(planner=planner)

    ws = MagicMock(spec=WorkspaceCapability)
    ws.launch_process = AsyncMock(return_value={"pid": 1111})
    ws.set_focus_window = AsyncMock(return_value=True)

    kb = MagicMock(spec=KeyboardCapability)
    kb.press_key = AsyncMock()
    kb.release_key = AsyncMock()
    ptr = MagicMock(spec=PointerCapability)
    ptr.move_to = AsyncMock()
    ptr.click = AsyncMock()

    # Locating targets
    bbox = TargetBoundingBox(left=10, top=10, right=50, bottom=50)
    safe_pt = SafeActionPoint(x=30, y=30, bounding_box=bbox, desktop_generation_id=1)
    res = ResolvedTarget(
        target_id="tgt_btn",
        bounding_box=bbox,
        safe_point=safe_pt,
        confidence=0.9,
        evidence=TargetEvidence(source="UIA", identifier="save_btn", name="Toolbar Save Button"),
        observation_id="obs_1",
        desktop_generation_id=1,
    )
    target_locator = MagicMock()
    target_locator.locate_target = AsyncMock(return_value=TargetResolutionResult(status=TargetResolutionStatus.RESOLVED, target=res))

    call_count = [0]
    def _create_obs(*args, **kwargs):
        call_count[0] += 1
        return CurrentStateObservation(
            observation_id=f"obs_step_{call_count[0]}",
            active_window_hwnd=888,
            active_window_title="Text Editor",
            ocr_tokens=["Text", "Editor"],
        )

    obs_mock = MagicMock()
    obs_mock.observe = AsyncMock(side_effect=_create_obs)

    # Transition verifier: Step 0 (root) completes, Step 1 (Toolbar Save) fails, Step 2 (Hotkey Save) succeeds
    step_num = [0]
    async def _mock_trans_verify(action, **kwargs):
        step_num[0] += 1
        if action.action_type == AbstractActionType.CLICK and action.target and action.target.name == "Toolbar Save Button":
            # Toolbar button fails
            planner.mark_failed_and_rollback(n_main_save.node_id, failure_reason="Button disabled", fallback_branch_id="fallback_hotkey")
            return ActionExecutionOutcome(
                action_id=action.action_id,
                dispatch_success=True,
                expected_effect_observed=False,
                goal_satisfied=False,
                outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
            )
        elif action.action_type == AbstractActionType.SEND_HOTKEY:
            # Hotkey succeeds
            planner.mark_completed(n_fall_save.node_id)
            return ActionExecutionOutcome(
                action_id=action.action_id,
                dispatch_success=True,
                expected_effect_observed=True,
                goal_satisfied=False,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
            )
        # Root step
        planner.mark_completed(n_root.node_id)
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
        if planner.is_all_completed():
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
        budget=ExecutionBudget(max_total_actions=8, timeout_seconds=10.0),
    )

    result = await loop.run("Save document with fallback hotkey")

    assert result.is_success is True
    # Verify fallback branch is active and hotkey was completed
    assert planner.active_branch == "fallback_hotkey"
    assert n_fall_save.status.value == "COMPLETED"
