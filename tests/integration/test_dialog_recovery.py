"""Integration test for modal dialog trap detection and closed-loop recovery (Phase 2G.2)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from typing import Any, Dict, List, Optional

from orbit.contracts.capabilities import KeyboardCapability, PointerCapability, WorkspaceCapability
from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
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
from orbit.runtime.cognitive.models import OutcomeStatus


class DialogRecoveryMockDecisionEngine:
    """Decision engine that attempts a save, encounters collision, and finishes."""

    def __init__(self) -> None:
        self.step = 0

    async def decide_next_step(
        self,
        objective: StructuredObjective,
        observation: CurrentStateObservation,
        step_history: List[CognitiveStepResult],
        step_index: int,
        task_context: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> CognitiveDecision:
        self.step = step_index
        # If goal satisfied
        if step_index >= 2:
            return CognitiveDecision(
                decision_summary="Save confirmed and modal cleared. Concluding task.",
                is_goal_satisfied=True,
                decision_confidence=1.0,
                next_action=AbstractAction(
                    action_type=AbstractActionType.COMPLETE_GOAL,
                    target=SemanticTarget(name="Done"),
                    parameters={},
                    expected_effect="Task completed",
                ),
            )

        # Step 0: Type filename
        return CognitiveDecision(
            decision_summary="Typing filename into save dialog",
            is_goal_satisfied=False,
            decision_confidence=0.9,
            next_action=AbstractAction(
                action_type=AbstractActionType.TYPE_TEXT,
                target=SemanticTarget(name="File name:", role="edit"),
                parameters={"text": "existing_file.txt\n"},
                expected_effect="File saved to disk",
            ),
        )


@pytest.mark.asyncio
async def test_dialog_recovery_closed_loop_resolves_save_collision():
    """Verify that when a Save As collision dialog appears, recovery resolves it via DialogTrapHandler."""
    budget = ExecutionBudget(max_total_actions=10, timeout_seconds=20.0)
    mock_engine = DialogRecoveryMockDecisionEngine()

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
    ev = TargetEvidence(source="UI_AUTOMATION", identifier="btn_yes", name="Yes")
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

    call_count = [0]
    def _create_obs(*args, **kwargs):
        call_count[0] += 1
        # Step 0 pre-obs: Save dialog
        if call_count[0] <= 1:
            return CurrentStateObservation(
                observation_id=f"obs_{uuid4().hex[:8]}",
                active_window_hwnd=100,
                active_window_title="Save As",
                active_window_class="#32770",
                visible_windows=[{"hwnd": 100, "title": "Save As", "class_name": "#32770"}],
            )
        # Step 0 post-obs: Collision Dialog appeared!
        elif call_count[0] == 2:
            return CurrentStateObservation(
                observation_id=f"obs_{uuid4().hex[:8]}",
                active_window_hwnd=200,
                active_window_title="Confirm Save As",
                active_window_class="#32770",
                ocr_tokens=["existing_file.txt", "already exists.", "Do you want to replace it?", "Yes", "No"],
                visible_windows=[
                    {"hwnd": 200, "title": "Confirm Save As", "class_name": "#32770"},
                    {"hwnd": 100, "title": "Save As", "class_name": "#32770"},
                ],
            )
        # Subsequent obs: Collision resolved, back to main editor
        return CurrentStateObservation(
            observation_id=f"obs_{uuid4().hex[:8]}",
            active_window_hwnd=300,
            active_window_title="existing_file.txt - Notepad",
            active_window_class="Notepad",
            visible_windows=[{"hwnd": 300, "title": "existing_file.txt - Notepad", "class_name": "Notepad"}],
        )

    obs_mock = MagicMock()
    obs_mock.observe = AsyncMock(side_effect=_create_obs)

    # Transition verifier: fails initial save because collision dialog appeared; succeeds recovery
    async def _mock_verify_transition(action, dispatch_success, pre_state, post_state, **kwargs):
        if action.action_type == AbstractActionType.TYPE_TEXT and "existing_file.txt" in action.parameters.get("text", ""):
            # Collision dialog opened instead of clean save
            return ActionExecutionOutcome(
                action_id=action.action_id,
                dispatch_success=True,
                expected_effect_observed=False,
                goal_satisfied=False,
                error_message="Collision dialog opened",
            )
        # Recovery action (CLICK 'Yes' / replace) succeeds
        return ActionExecutionOutcome(
            action_id=action.action_id,
            dispatch_success=True,
            expected_effect_observed=True,
            goal_satisfied=False,
        )

    trans_verifier = MagicMock()
    trans_verifier.verify_action_outcome = AsyncMock(side_effect=_mock_verify_transition)

    async def _mock_verify_goal(task_id, objective, current_observation, step_history, **kwargs):
        if len(step_history) >= 2:
            return GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
                evidence=TaskCompletionEvidence(application_name="notepad", application_is_open=True),
            )
        return GoalVerificationResult(status=TaskCompletionStatus.PARTIALLY_COMPLETED, is_completed=False)

    goal_verifier = MagicMock()
    goal_verifier.verify_goal_achievement = AsyncMock(side_effect=_mock_verify_goal)

    async def _mock_me_verify(action, pre_obs, post_obs, **kwargs):
        if action.action_type == AbstractActionType.TYPE_TEXT and "existing_file.txt" in action.parameters.get("text", ""):
            return MagicMock(is_verified=False, outcome_status=OutcomeStatus.EFFECT_UNVERIFIED, verification_reason="Collision dialog opened")
        return MagicMock(is_verified=True, outcome_status=OutcomeStatus.EFFECT_VERIFIED, verification_reason="Action effect verified")

    me_verifier = MagicMock()
    me_verifier.verify_action_effect = AsyncMock(side_effect=_mock_me_verify)

    loop = AgentExecutionLoop(
        decision_engine=mock_engine,
        workspace=ws,
        keyboard=kb,
        pointer=ptr,
        target_locator=locator,
        goal_verifier=goal_verifier,
        observer=obs_mock,
        transition_verifier=trans_verifier,
        multi_evidence_verifier=me_verifier,
        budget=budget,
    )

    result = await loop.run("Save document to existing_file.txt in Notepad")

    assert result.is_success is True
    # Verify that recovery occurred and recorded the dialog recovery
    rec_history = loop.recovery_records
    assert len(rec_history) >= 1
    assert rec_history[0].strategy.value == "OVERWRITE_FILE_COLLISION"
    assert rec_history[0].recovery_success is True
