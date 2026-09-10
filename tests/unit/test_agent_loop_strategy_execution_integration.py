"""Negative and boundary integration tests verifying StrategyExecutionEngine is unreachable from AgentExecutionLoop (Phase 0 Rules #3, #14, #15)."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from orbit.runtime.capabilities.execution.contracts import (
    CapabilityExecutionResult,
    StageOutcomeStatus,
)
from orbit.runtime.capabilities.execution.executor_registry import CapabilityExecutorRegistry
from orbit.runtime.capabilities.execution.strategy_execution_engine import (
    StrategyExecutionEngine,
    StrategyExecutionResult,
)
from orbit.runtime.capabilities.feasibility import FeasibilityAnalyzer
from orbit.runtime.capabilities.models import (
    FeasibilityAssessment,
    FeasibilityStatus,
    StrategyOption,
    StrategyStage,
)
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.task_completion.models import TaskCompletionStatus


@pytest.mark.asyncio
async def test_agent_loop_never_dispatches_to_strategy_execution_engine():
    """Prove that StrategyExecutionEngine cannot be reached from production AgentLoop (Phase 0 Rule #3 & #15)."""
    # 1. Prepare Mock Strategy & Feasibility
    strategy = StrategyOption(
        strategy_id="STRAT_COMPOSITE_TEST",
        name="Composite Generation & Insertion",
        description="Composite workflow",
        required_capabilities=["IMAGE_GENERATE_AND_INSERT"],
        stages=[
            StrategyStage(
                stage_index=0,
                name="GENERATE_AND_INSERT",
                capability_id="IMAGE_GENERATE_AND_INSERT",
                description="Generate image and insert into Paint",
                expected_outcome="image_in_paint",
            ),
        ],
        semantic_goal_coverage=0.95,
        estimated_success_probability=0.90,
        is_available=True,
    )

    feasibility_analyzer = MagicMock()
    feasibility_analyzer.evaluate_feasibility.return_value = FeasibilityAssessment(
        is_feasible=True,
        status=FeasibilityStatus.FEASIBLE,
        matched_strategy=strategy,
        explanation="Composite workflow is viable",
    )

    # 2. Mock Strategy Execution Engine
    strat_exec_engine = MagicMock()
    strat_exec_engine.can_execute_strategy.return_value = True
    strat_exec_engine.execute_strategy = AsyncMock()

    # 3. Mock Observer & Goal Verifier
    obs = CurrentStateObservation(observation_id="obs_0")
    observer = MagicMock()
    observer.observe = AsyncMock(return_value=obs)

    goal_verifier = MagicMock()
    goal_verifier.verify_goal_achievement = AsyncMock(
        return_value=MagicMock(is_satisfied=False, status=TaskCompletionStatus.FAILED)
    )

    loop = AgentExecutionLoop(
        feasibility_analyzer=feasibility_analyzer,
        strategy_execution_engine=strat_exec_engine,
        observer=observer,
        goal_verifier=goal_verifier,
    )
    loop._planner = MagicMock()
    loop._planner.synthesize_candidate_plans = AsyncMock(return_value=[])

    # Run loop with context requesting authoritative strategy execution
    result = await loop.run(
        prompt="Open Paint and draw a portrait of a boy",
        context={"authoritative_strategy_execution": True},
    )

    # CRITICAL: StrategyExecutionEngine was NOT invoked. It is completely unreachable.
    strat_exec_engine.execute_strategy.assert_not_called()
    assert strat_exec_engine.can_execute_strategy.call_count == 0


@pytest.mark.asyncio
async def test_agent_loop_strategy_execution_engine_is_not_an_execution_authority():
    """Prove that passing strategy_execution_engine to AgentExecutionLoop does not create an execution authority."""
    strat_exec_engine = MagicMock()
    strat_exec_engine.execute_strategy = AsyncMock()

    obs = CurrentStateObservation(observation_id="obs_0")
    observer = MagicMock()
    observer.observe = AsyncMock(return_value=obs)

    loop = AgentExecutionLoop(
        strategy_execution_engine=strat_exec_engine,
        observer=observer,
    )

    # Run loop
    await loop.run(
        prompt="Arbitrary user instruction",
        context={"authoritative_strategy_execution": True},
    )

    # The engine must never be called
    strat_exec_engine.execute_strategy.assert_not_called()

