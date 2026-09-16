"""Unit integration trace test for Step 2: Full flow from AbstractAction to ResolvedAction to Execution & Verification.

Simulates the exact end-to-end path:
User Prompt: "Open Notepad and type Hello"
1. AbstractAction(LAUNCH_APPLICATION) -> Validated -> Executed -> Verified
2. AbstractAction(TYPE_TEXT) with SemanticTarget -> Validated -> Grounded to ResolvedAction -> Dispatched -> Verified
3. Final Goal Verification.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionOutcomeContract,
    ActionValidationFailureCode,
    ActionValidationResult,
    AgentActionValidator,
    OutcomeStatus,
    ResolvedAction,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.agent.state import DesktopStateSnapshot
from orbit.runtime.agent.verifier import AgentStateTransitionVerifier
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop, AgentExecutionResult
from orbit.runtime.cognitive.models import (
    CurrentStateObservation,
    ExecutionBudget,
    StructuredObjective,
)
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.targeting.models import (
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
    TargetIntent,
    TargetResolutionResult,
    TargetResolutionStatus,
    ResolvedTarget,
)
from orbit.runtime.task_completion.models import TaskCompletionStatus


@pytest.mark.asyncio
async def test_step2_end_to_end_trace_flow():
    """Trace exact Step 2 flow from AbstractAction to ResolvedAction and Verification."""
    # 1. User Prompt & Objective
    objective = StructuredObjective(
        raw_prompt="Open Notepad and type Hello",
        user_goal="Open Notepad and type Hello",
        end_condition="notepad_contains_hello",
        target_entities=["notepad", "editor"],
        parameters={"app_name": "notepad", "text": "Hello"},
    )

    # 2. Step 1: Launch Notepad Abstract Action
    launch_action = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        target=SemanticTarget(name="Notepad", role="application"),
        parameters={"application_name": "notepad.exe"},
        outcome_contract=ActionOutcomeContract(
            expected_state_transition="notepad_launched",
            verification_strategy=VerificationStrategy.WIN32_WINDOW,
            expected_window_title="Notepad",
        ),
    )

    # Validate Launch Action
    val_res = AgentActionValidator.validate(launch_action)
    assert val_res.is_valid is True
    assert val_res.failure_code == ActionValidationFailureCode.VALID

    # Simulate Pre/Post State for Launch Action
    pre_launch_state = DesktopStateSnapshot(
        active_window_title="Desktop",
        active_window_hwnd=10,
        target_app_exists=False,
    )
    post_launch_state = DesktopStateSnapshot(
        active_window_title="Untitled - Notepad",
        active_window_hwnd=200,
        target_app_exists=True,
        visible_windows=[{"title": "Untitled - Notepad", "class_name": "Notepad", "hwnd": 200}],
    )

    verifier = AgentStateTransitionVerifier()
    launch_outcome = await verifier.verify_action_outcome(
        action=launch_action,
        dispatch_success=True,
        pre_state=pre_launch_state,
        post_state=post_launch_state,
    )
    assert launch_outcome.dispatch_success is True
    assert launch_outcome.expected_effect_observed is True
    assert launch_outcome.outcome_status == OutcomeStatus.EFFECT_VERIFIED

    # 3. Step 2: Type Text Abstract Action with Semantic Target
    type_action = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        target=SemanticTarget(
            name="Text Editor",
            role="document",
            application="Notepad",
            context="Untitled - Notepad",
        ),
        parameters={"text": "Hello", "press_enter": True},
        outcome_contract=ActionOutcomeContract(
            expected_state_transition="hello_text_entered",
            verification_strategy=VerificationStrategy.UIA_TEXT,
            expected_text="Hello",
        ),
    )

    # Validate Type Action
    val_type = AgentActionValidator.validate(type_action)
    assert val_type.is_valid is True
    # Ensure NO coordinates in cognitive action
    assert "x" not in type_action.parameters
    assert "y" not in type_action.parameters

    # 4. Target Grounding: AbstractAction -> ResolvedAction (Runtime Generated)
    bbox = TargetBoundingBox(left=100, top=150, right=600, bottom=500)
    safe_pt = SafeActionPoint(x=350, y=325, bounding_box=bbox, desktop_generation_id=1)

    resolved_action = ResolvedAction(
        action_id=type_action.action_id,
        action_type=type_action.action_type,
        resolved_target_id="tgt_notepad_doc_01",
        bounding_box=bbox,
        execution_point=safe_pt,
        parameters=type_action.parameters,
        outcome_contract=type_action.outcome_contract,
        target_hwnd=200,
        resolution_confidence=0.99,
        grounding_source="UI_AUTOMATION",
    )

    assert resolved_action.execution_point.x == 350
    assert resolved_action.execution_point.y == 325
    assert resolved_action.grounding_source == "UI_AUTOMATION"

    # 5. Type Execution & Post State Verification
    post_type_state = DesktopStateSnapshot(
        active_window_title="Untitled - Notepad",
        active_window_hwnd=200,
        target_app_exists=True,
        ocr_tokens=["Untitled", "Notepad", "Hello"],
    )

    type_outcome = await verifier.verify_action_outcome(
        action=type_action,
        dispatch_success=True,
        pre_state=post_launch_state,
        post_state=post_type_state,
    )
    assert type_outcome.dispatch_success is True
    assert type_outcome.expected_effect_observed is True
    assert type_outcome.outcome_status == OutcomeStatus.EFFECT_VERIFIED
    assert type_outcome.observed_delta.get("text_typed_length") == 5

    # 6. Final Goal Verification
    complete_action = AbstractAction(
        action_type=AbstractActionType.COMPLETE_GOAL,
        parameters={"summary": "Notepad launched and text 'Hello' verified"},
    )
    val_comp = AgentActionValidator.validate(complete_action)
    assert val_comp.is_valid is True

    complete_outcome = await verifier.verify_action_outcome(
        action=complete_action,
        dispatch_success=True,
        pre_state=post_type_state,
        post_state=post_type_state,
    )
    assert complete_outcome.goal_satisfied is True
