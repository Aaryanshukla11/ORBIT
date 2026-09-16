"""Integration tests for Phase 1 Foundation components wired into AgentExecutionLoop."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.task_completion.models import TaskCompletionStatus
from orbit.runtime.world_model.model import AgentWorldModel


@pytest.mark.asyncio
async def test_phase1_runtime_feasibility_gate_blocks_locked_desktop():
    # Mock observer returning observation
    mock_obs = CurrentStateObservation(
        active_process_name="explorer.exe",
        active_window_title="Desktop",
    )
    mock_observer = MagicMock()
    mock_observer.capture_observation = AsyncMock(return_value=mock_obs)
    mock_observer.observe = AsyncMock(return_value=mock_obs)

    # World model with locked desktop
    locked_wm = AgentWorldModel(is_desktop_locked=True)

    loop = AgentExecutionLoop(
        observer=mock_observer,
        world_model=locked_wm,
    )
    # Ensure world_model retains locked state when run() starts
    loop._runtime_feasibility_evaluator._check_network = False

    # Force world_model to stay locked by monkeypatching or testing evaluator
    res = await loop.run(prompt="Open notepad and type hello")

    # Should be rejected cleanly
    assert res.is_success is False
    assert res.final_status == TaskCompletionStatus.UNSUPPORTED


@pytest.mark.asyncio
async def test_phase1_captcha_detection_blocks_execution():
    # Mock observer returning captcha in OCR
    captcha_obs = CurrentStateObservation(
        ocr_tokens=["Please", "verify", "you", "are", "human"],
    )
    mock_observer = MagicMock()
    mock_observer.capture_observation = AsyncMock(return_value=captcha_obs)
    mock_observer.observe = AsyncMock(return_value=captcha_obs)

    loop = AgentExecutionLoop(
        observer=mock_observer,
    )
    loop._runtime_feasibility_evaluator._check_network = False

    res = await loop.run(prompt="Complete registration form")

    assert res.is_success is False
    assert res.failure_code == "RUNTIME_ENVIRONMENT_INFEASIBLE"
    assert "CAPTCHA" in res.failure_reason


@pytest.mark.asyncio
async def test_phase1_progress_graph_dag_and_world_model_integration():
    """Integration: ProgressGraph DAG coordinates multi-milestone plan and updates WorldModel projection."""
    from orbit.runtime.cognitive.models import ProgressGraph, SubObjective, SubgoalStatus
    from orbit.runtime.world_model.model import AgentWorldModel

    sub1 = SubObjective(sub_id="s1", title="Initialize Paint Canvas", dependencies=[])
    sub2 = SubObjective(sub_id="s2", title="Draw Blue Rectangle", dependencies=["s1"])
    sub3 = SubObjective(sub_id="s3", title="Save Artwork", dependencies=["s2"])

    graph = ProgressGraph([sub1, sub2, sub3])
    wm = AgentWorldModel()

    # Step 1: Initial state
    wm.update_progress_snapshot(graph.get_snapshot())
    assert wm.progress_snapshot.ready_subgoals == ["s1"]
    assert len(wm.progress_snapshot.pending_subgoals) == 2

    # Step 2: Progress through s1
    graph.start_subgoal("s1")
    graph.complete_subgoal("s1")
    wm.update_progress_snapshot(graph.get_snapshot())
    assert "s1" in wm.progress_snapshot.completed_subgoals
    assert wm.progress_snapshot.ready_subgoals == ["s2"]

    # Step 3: Progress through s2 and s3
    graph.start_subgoal("s2")
    graph.complete_subgoal("s2")
    graph.start_subgoal("s3")
    graph.complete_subgoal("s3")

    wm.update_progress_snapshot(graph.get_snapshot())
    assert wm.progress_snapshot.is_fully_completed is True
    assert wm.progress_snapshot.is_failed is False
    assert len(wm.progress_snapshot.completed_subgoals) == 3


@pytest.mark.asyncio
async def test_phase1_task_scoped_memory_and_secret_isolation_integration():
    """Integration: TaskScopedMemory isolates variables and credentials during execution and purges cleanly."""
    from orbit.runtime.memory.task_memory import TaskScopedMemory

    mem = TaskScopedMemory(task_id="integration_task_42")

    # Ephemeral variables
    mem.set_variable("current_step", "step_02")
    mem.set_variable("doc_name", "annual_report.docx")

    # Secret isolation
    token = mem.secret_store.store_secret("db_pass", "super_secret_db_pass_123")
    assert mem.secret_store.resolve_secret(token) == "super_secret_db_pass_123"

    # Masking in telemetry
    log_msg = f"Connecting to DB with password super_secret_db_pass_123 on port 5432"
    masked = mem.secret_store.mask_text(log_msg)
    assert "super_secret_db_pass_123" not in masked
    assert "***REDACTED***" in masked

    # Task completion lifecycle wipe
    mem.wipe()
    assert mem.is_wiped is True
    assert mem.secret_store.resolve_secret("db_pass") is None


@pytest.mark.asyncio
async def test_phase1_clarification_blocks_ambiguous_intent_without_physical_dispatch():
    """Integration: Ambiguous intent triggers ClarificationManager, halting physical execution."""
    from orbit.runtime.cognitive.clarification import (
        ClarificationManager,
        TaskUnderstandingResult,
        TaskUnderstandingStatus,
    )

    mgr = ClarificationManager()

    ambig_res = TaskUnderstandingResult(
        status=TaskUnderstandingStatus.AMBIGUOUS,
        unresolved_constraints=["Ambiguous control reference 'it'"],
        diagnostic_messages=["Target has no locator or application context"],
    )

    assert mgr.is_clarification_needed(ambig_res) is True
    req = mgr.generate_clarification_request("task_test_ambig", "Click it", ambig_res)
    assert len(req.clarification_questions) > 0
    assert any("Ambiguous control reference" in q for q in req.clarification_questions)

