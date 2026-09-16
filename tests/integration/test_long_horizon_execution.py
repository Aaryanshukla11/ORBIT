"""Integration test for long-horizon 10-30+ step execution stability and checkpointing (Phase 2G.1)."""

import asyncio
import pytest
from typing import Any, Dict, List, Optional

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionOutcomeContract,
    SemanticTarget,
)
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop, AgentExecutionResult
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CognitiveStepResult,
    CurrentStateObservation,
    ExecutionBudget,
    StructuredObjective,
)
from orbit.runtime.perception.models import DesktopObservation, WindowObservation
from orbit.models.common import BoundingBox


class LongHorizonMockDecisionEngine:
    """Simulates a 15-step sequence with milestones, text entry, and conclusion."""

    def __init__(self, target_steps: int = 15) -> None:
        self.target_steps = target_steps
        self.current_step = 0

    async def decide_next_step(
        self,
        objective: StructuredObjective,
        observation: CurrentStateObservation,
        step_history: List[CognitiveStepResult],
        step_index: int,
        task_context: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> CognitiveDecision:
        self.current_step = step_index
        if step_index >= self.target_steps:
            return CognitiveDecision(
                decision_summary=f"Reached target {self.target_steps} steps. Completing task.",
                is_goal_satisfied=True,
                decision_confidence=1.0,
                next_action=AbstractAction(
                    action_type=AbstractActionType.COMPLETE_GOAL,
                    target=SemanticTarget(name="Done"),
                    parameters={},
                    expected_effect="Task completed",
                ),
            )

        # Emit sequential steps (launch, typing, navigating)
        act_type = AbstractActionType.TYPE_TEXT if step_index > 0 else AbstractActionType.LAUNCH_APPLICATION
        t_name = f"Field_{step_index}" if step_index > 0 else "notepad"
        return CognitiveDecision(
            decision_summary=f"Executing long-horizon step {step_index}",
            is_goal_satisfied=False,
            decision_confidence=0.9,
            next_action=AbstractAction(
                action_type=act_type,
                target=SemanticTarget(name=t_name, role="edit" if step_index > 0 else "app"),
                parameters={"text": f"Line {step_index}\n"} if step_index > 0 else {"application_name": "notepad"},
                expected_effect=f"Step {step_index} effect",
            ),
        )


from unittest.mock import AsyncMock, MagicMock
from orbit.contracts.capabilities import KeyboardCapability, PointerCapability, WorkspaceCapability
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
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


@pytest.mark.asyncio
async def test_long_horizon_15_step_execution_and_checkpoint_cadence():
    """Verify that a 15-step execution produces valid checkpoints, compactions, and trajectory logs."""
    budget = ExecutionBudget(max_total_actions=20, timeout_seconds=30.0)
    mock_engine = LongHorizonMockDecisionEngine(target_steps=12)

    ws = MagicMock(spec=WorkspaceCapability)
    ws.launch_process = AsyncMock(return_value={"pid": 1234})
    ws.set_focus_window = AsyncMock(return_value=True)

    kb = MagicMock(spec=KeyboardCapability)
    kb.type_text = AsyncMock()
    kb.press_key = AsyncMock()
    kb.release_key = AsyncMock()

    ptr = MagicMock(spec=PointerCapability)
    ptr.move_to = AsyncMock()
    ptr.click = AsyncMock()

    bbox = TargetBoundingBox(left=100, top=100, right=200, bottom=150)
    safe_pt = SafeActionPoint(x=150, y=125, bounding_box=bbox, desktop_generation_id=1)
    ev = TargetEvidence(source="UI_AUTOMATION", identifier="field_1", name="Field")
    resolved = ResolvedTarget(
        target_id="tgt_1",
        bounding_box=bbox,
        safe_point=safe_pt,
        confidence=0.95,
        evidence=ev,
        observation_id="obs_1",
        desktop_generation_id=1,
    )
    locator = MagicMock(spec=EvidenceBasedTargetLocator)
    locator.locate_target = AsyncMock(
        return_value=TargetResolutionResult(
            status=TargetResolutionStatus.RESOLVED,
            target=resolved,
        )
    )

    async def _mock_verify_goal(task_id, objective, current_observation, step_history, **kwargs):
        if len(step_history) >= 12:
            return GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
                evidence=TaskCompletionEvidence(application_name="notepad", application_is_open=True),
            )
        return GoalVerificationResult(
            status=TaskCompletionStatus.PARTIALLY_COMPLETED,
            is_completed=False,
        )

    goal_verifier = MagicMock()
    goal_verifier.verify_goal_achievement = AsyncMock(side_effect=_mock_verify_goal)

    from uuid import uuid4
    def _create_fresh_obs(*args, **kwargs):
        return CurrentStateObservation(
            observation_id=f"obs_{uuid4().hex[:8]}",
            target_app_exists=True,
            target_app_is_active=True,
            active_window_title="Notepad",
            screen_summary="Notepad Active",
        )

    obs_mock = MagicMock()
    obs_mock.observe = AsyncMock(side_effect=_create_fresh_obs)

    trans_verifier = MagicMock()
    trans_verifier.verify_action_outcome = AsyncMock(
        return_value=ActionExecutionOutcome(
            action_id="act_test",
            dispatch_success=True,
            expected_effect_observed=True,
            goal_satisfied=False,
            observed_delta={},
        )
    )

    loop = AgentExecutionLoop(
        decision_engine=mock_engine,
        workspace=ws,
        keyboard=kb,
        pointer=ptr,
        target_locator=locator,
        goal_verifier=goal_verifier,
        observer=obs_mock,
        transition_verifier=trans_verifier,
        budget=budget,
    )

    result = await loop.run("Execute 12-step long-horizon data logging workflow")

    assert result.is_success is True
    assert result.total_steps == 12  # 12 long-horizon action steps

    # Verify Checkpoint Manager captured checkpoints on cadence
    chk_count = loop.checkpoint_manager.checkpoint_count
    assert chk_count >= 2  # Cadence every 5 steps: step 5, step 10
    latest_chk = loop.checkpoint_manager.get_latest_checkpoint()
    assert latest_chk is not None
    assert latest_chk.step_index >= 10

    # Verify Trajectory Memory recorded all steps without false loop alerts
    assert loop.trajectory_memory.total_steps_recorded == 12
    is_loop, _ = loop.trajectory_memory.is_looping_detected()
    assert is_loop is False

    # Verify Context Compactor bounded history length
    compaction = loop.context_compactor.compact_history(
        step_history=result.step_history,
        current_step=12,
    )
    assert compaction.total_steps == 12
    assert compaction.compacted_steps_count == 8  # 12 - 4 = 8 compacted older steps
    assert compaction.detailed_steps_count == 4
    assert compaction.char_count < 3000
