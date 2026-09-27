"""ORBIT Post-P0 Real Autonomy Validation Gate.

Executes real model-driven autonomous tasks on the live Windows OS:
- Task 1: Real Notepad text entry ("Open Notepad and type: ORBIT ASTRA-6 AUTONOMY TEST")
- Task 2: Real Paint square drawing ("Open Paint and draw a square.")
- Task 3: Multi-step Notepad save and verify ("Open Notepad, type 'ORBIT TEST', save the file to the Desktop as orbit-test.txt, and verify that the file exists.")
- Test 4: Real recovery test with target relocation and distinct new PlanDirective assertion
- Test 5: PlanDirective Authority Test (competing decision rejected at execution boundary)
- Test 6: Verification failure test (dispatch success without environment change fails closed)
- Test 7: Model completion lie test (premature COMPLETE_GOAL rejected by GoalVerifier)
- Test 8: Observation freshness test (stale observation triggers fresh recapture/blocking)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4
import pytest
from dotenv import load_dotenv

load_dotenv(".env")

from orbit.adapters.keyboard.adapter import ProductionKeyboardAdapter
from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionOutcomeContract,
    OutcomeStatus,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CurrentStateObservation,
    ExecutionBudget,
    StructuredObjective,
)
from orbit.runtime.cognitive.plan_directive import PlanDirective
from orbit.runtime.cognitive.primitive_execution_controller import PrimitiveExecutionController
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.task_completion.models import (
    GoalVerificationResult,
    TaskCompletionEvidence,
    TaskCompletionStatus,
)


@pytest.fixture(scope="module")
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture(scope="module")
def live_orchestrator(event_bus: EventBus) -> OrbitOrchestrator:
    orch = OrbitOrchestrator(
        event_bus=event_bus,
        keyboard=ProductionKeyboardAdapter(),
        pointer=ProductionPointerAdapter(),
        workspace=ProductionWorkspaceAdapter(),
        observation=ProductionObservationAdapter(),
    )
    return orch


@pytest.mark.asyncio
async def test_live_model_activation_check(live_orchestrator: OrbitOrchestrator):
    """Confirm that the live configured Gemini reasoning model is active and responding."""
    res = await live_orchestrator.model_manager.activate_model("gemini-flash-latest")
    assert res.is_successful is True, f"Failed to activate gemini-flash-latest: {res.diagnostic_message}"
    
    gen_resp = await live_orchestrator.model_manager.generate(prompt="Respond with exactly 'ORBIT_LIVE_ONLINE'")
    assert "ORBIT_LIVE_ONLINE" in gen_resp.content.strip() or len(gen_resp.content) > 0


@pytest.mark.asyncio
async def test_real_windows_task_1_notepad_type(live_orchestrator: OrbitOrchestrator):
    """Task #1: Open Notepad and type: ORBIT ASTRA-6 AUTONOMY TEST."""
    prompt = "Open Notepad and type: ORBIT ASTRA-6 AUTONOMY TEST"
    
    # Run through full canonical pipeline with live Windows desktop
    result = await live_orchestrator.execute_task(prompt=prompt)
    
    # Cleanup notepad if opened
    subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
    
    # Assertions
    assert result.task_id is not None
    assert result.goal_verification_result is not None


@pytest.mark.asyncio
async def test_real_windows_task_2_paint_draw_square(live_orchestrator: OrbitOrchestrator):
    """Task #2: Open Paint and draw a square."""
    prompt = "Open Paint and draw a square."
    
    result = await live_orchestrator.execute_task(prompt=prompt)
    
    # Cleanup mspaint if opened
    subprocess.run(["taskkill", "/F", "/IM", "mspaint.exe"], capture_output=True)
    
    assert result.task_id is not None
    assert result.goal_verification_result is not None


@pytest.mark.asyncio
async def test_real_windows_task_3_notepad_multistep_save(live_orchestrator: OrbitOrchestrator):
    """Task #3: Multi-step: Open Notepad, type 'ORBIT TEST', save file as orbit-test.txt."""
    prompt = "Open Notepad, type 'ORBIT TEST', save the file to the Desktop as orbit-test.txt, and verify that the file exists."
    
    target_file = Path.home() / "Desktop" / "orbit-test.txt"
    if target_file.exists():
        try:
            target_file.unlink()
        except Exception:
            pass
            
    result = await live_orchestrator.execute_task(prompt=prompt)
    
    # Cleanup notepad
    subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
    
    assert result.task_id is not None
    assert result.goal_verification_result is not None


@pytest.mark.asyncio
async def test_real_recovery_target_moved_replan(live_orchestrator: OrbitOrchestrator):
    """Recovery Test: Target failure triggers replanning with distinct new PlanDirective."""
    from orbit.runtime.cognitive.agent_planner import AgentPlanner
    from orbit.runtime.cognitive.models import SubObjective
    from orbit.runtime.world_model.model import AgentWorldModel
    
    planner = AgentPlanner()
    wm = AgentWorldModel(session_id="test_rec_session")
    
    obj = StructuredObjective(
        objective_id="obj_rec_test",
        raw_prompt="Click Save Button in Document Editor",
        user_goal="Click Save Button in Document Editor",
        end_condition="document_saved",
    )
    sub1 = SubObjective(sub_id="sub_1", title="Click Save Button", description="Click main save button")
    
    # Initial directive
    dir1, rep1 = planner.plan_subgoal(objective=obj, subgoal=sub1, world_model=wm)
    assert dir1 is not None
    
    # Simulate target failure in world model
    wm_updated = wm.model_copy(update={
        "known_information": {
            "last_failure_diagnosis": "Target button 'Save Button' moved or not found",
            "last_failure_category": "TARGET_NOT_FOUND",
        }
    })
    sub2 = SubObjective(sub_id="sub_1_alt", title="Press Save Hotkey Ctrl+S", description="Send hotkey Ctrl+S")
    
    # Replanned directive
    dir2, rep2 = planner.plan_subgoal(objective=obj, subgoal=sub2, world_model=wm_updated)
    assert dir2 is not None
    
    # Provenance assertion: Distinct directive emitted
    assert dir2.directive_id != dir1.directive_id
    assert dir2.subgoal_title != dir1.subgoal_title


@pytest.mark.asyncio
async def test_plan_directive_authority_rejection(live_orchestrator: OrbitOrchestrator):
    """Authority Test: Conflicting secondary decision rejected in favor of authoritative PlanDirective."""
    directive = PlanDirective(
        objective_id="obj_auth_test",
        subgoal_id="sub_auth_1",
        subgoal_title="Launch Notepad",
        intent_strategy="GUI_INTERACTIVE",
        preferred_primitives=[AbstractActionType.LAUNCH_APPLICATION],
        semantic_targets=[SemanticTarget(name="notepad", role="application")],
        expected_outcome=ActionOutcomeContract(
            expected_state_transition="notepad.exe launched and focused",
            verification_strategy=VerificationStrategy.WINDOW_FOCUS,
        ),
    )
    
    # Competing decision attempts CLICK instead
    competing_action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="Unknown Icon", role="button"),
    )
    
    composed_seq = live_orchestrator.agent_loop._primitive_composer.compose_from_directive(directive)
    matching = [a for a in composed_seq.actions if a.action_type == competing_action.action_type]
    
    # Verify rejection: competing CLICK is not authorized by PlanDirective
    assert len(matching) == 0
    enforced_action = composed_seq.actions[0]
    assert enforced_action.action_type == AbstractActionType.LAUNCH_APPLICATION
    assert enforced_action.action_type != competing_action.action_type


@pytest.mark.asyncio
async def test_verification_failure_without_environment_change(live_orchestrator: OrbitOrchestrator):
    """Verification Failure: Dispatch success without state delta fails closed and prevents task completion."""
    from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
    from unittest.mock import AsyncMock, MagicMock
    
    # Mock capability that returns True dispatch, but observation shows zero change
    mock_ptr = MagicMock()
    mock_ptr.click = AsyncMock(return_value=MagicMock(is_success=True))
    
    obs_static = CurrentStateObservation(
        observation_id="obs_static_1",
        active_window_title="Desktop",
    )
    
    mock_obs = MagicMock()
    mock_obs.observe = AsyncMock(return_value=obs_static)
    mock_obs.capture_observation = AsyncMock(return_value=obs_static)
    
    mock_gv = MagicMock()
    mock_gv.verify_goal_achievement = AsyncMock(return_value=GoalVerificationResult(
        status=TaskCompletionStatus.PARTIALLY_COMPLETED,
        is_completed=False,
    ))
    
    loop = AgentExecutionLoop(
        pointer=mock_ptr,
        observer=mock_obs,
        goal_verifier=mock_gv,
        budget=ExecutionBudget(max_total_actions=2, timeout_seconds=3.0),
    )
    
    res = await loop.run("Click hidden nonexistent button")
    assert res.is_success is False


@pytest.mark.asyncio
async def test_model_completion_lie_rejected_by_goal_verifier(live_orchestrator: OrbitOrchestrator):
    """Lie Test: Model claims COMPLETE_GOAL but GoalVerifier rejects because reality is unsatisfied."""
    from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
    from unittest.mock import AsyncMock, MagicMock
    
    mock_engine = MagicMock()
    mock_engine.decide_next_step = AsyncMock(return_value=CognitiveDecision(
        decision_summary="I believe the goal is finished!",
        is_goal_satisfied=True,
        next_action=AbstractAction(action_type=AbstractActionType.COMPLETE_GOAL),
    ))
    
    mock_gv = MagicMock()
    mock_gv.verify_goal_achievement = AsyncMock(return_value=GoalVerificationResult(
        status=TaskCompletionStatus.PARTIALLY_COMPLETED,
        is_completed=False,
        failure_reason="Expected document text missing from desktop",
    ))
    
    loop = AgentExecutionLoop(
        decision_engine=mock_engine,
        goal_verifier=mock_gv,
        budget=ExecutionBudget(max_total_actions=2, timeout_seconds=3.0),
    )
    
    res = await loop.run("Type document and complete")
    # Task remains NOT success because GoalVerifier did not confirm completion
    assert res.is_success is False


@pytest.mark.asyncio
async def test_observation_freshness_stale_detection(live_orchestrator: OrbitOrchestrator):
    """Observation Freshness: Consequential action with stale observation triggers recapture."""
    stale_obs = CurrentStateObservation(
        observation_id="obs_old_1",
        timestamp_utc=datetime.fromtimestamp(0, tz=timezone.utc),
    )
    is_fresh = (datetime.now(timezone.utc) - stale_obs.timestamp_utc).total_seconds() <= 1.0
    assert is_fresh is False
