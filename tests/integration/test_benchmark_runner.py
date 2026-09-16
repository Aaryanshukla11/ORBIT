"""Integration test for Phase 2G Benchmark Runner and Verifier Harness."""

import asyncio
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock

from benchmark.runner import BenchmarkRunner
from benchmark.schema import BenchmarkCategory, BenchmarkSplit, BenchmarkTask, TaskExpectation
from benchmark.taxonomy import FailureTaxonomy
from orbit.runtime.cognitive.agent_loop import AgentExecutionResult
from orbit.runtime.cognitive.engine import OrbitDecisionEngine
from orbit.runtime.cognitive.models import (
    AbstractAction,
    AbstractActionType,
    CognitiveDecision,
    CognitiveStepResult,
    CurrentStateObservation,
    SemanticTarget,
    StructuredObjective,
)


@pytest.fixture
def mock_decision_engine():
    model = MagicMock(spec=OrbitDecisionEngine)
    decision = CognitiveDecision(
        decision_summary="Test launch",
        decision_confidence=1.0,
        evidence_used=["test"],
        expected_state_transition="app_open",
        is_goal_satisfied=True,
        next_action=AbstractAction(
            action_type=AbstractActionType.LAUNCH_APPLICATION,
            target=SemanticTarget(name="notepad", role="application"),
            parameters={"application_name": "notepad"},
        ),
    )
    model.decide_next_step = AsyncMock(return_value=decision)
    return model


@pytest.mark.asyncio
async def test_benchmark_runner_task_execution_flow(tmp_path, mock_decision_engine):
    runner = BenchmarkRunner(results_dir=tmp_path, decision_engine=mock_decision_engine)

    # 1. Create a lightweight test task
    task = BenchmarkTask(
        task_id="test_task_001",
        title="Test Launch Notepad",
        split=BenchmarkSplit.DEVELOPMENT,
        category=BenchmarkCategory.APPLICATION_LAUNCH,
        natural_language_goal="Open Notepad",
        expectations=TaskExpectation(
            expected_window_title="Notepad",
            expected_process_name="notepad.exe",
            require_app_open=True,
        ),
        timeout_sec=10.0,
        max_steps=3,
    )

    # 2. Execute task
    record = await runner.execute_task(task)

    assert record.task_id == "test_task_001"
    assert record.split == BenchmarkSplit.DEVELOPMENT
    assert record.duration_sec >= 0.0
    assert record.total_steps >= 0

    # 3. Verify output files written
    result_file = tmp_path / "test_task_001_result.json"
    assert result_file.exists()


@pytest.mark.asyncio
async def test_benchmark_runner_metrics_aggregation(tmp_path):
    runner = BenchmarkRunner(results_dir=tmp_path)
    tasks = runner.load_tasks(split=BenchmarkSplit.DEVELOPMENT)
    assert len(tasks) == 25

    unseen_tasks = runner.load_tasks(split=BenchmarkSplit.UNSEEN)
    assert len(unseen_tasks) == 25
