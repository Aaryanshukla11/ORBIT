"""Integration tests for authoritative strategy execution within AgentExecutionLoop (M1.9 Component 6)."""

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
async def test_agent_loop_authoritatively_executes_strategy_via_engine():
    """When a viable strategy requires authoritative execution, StrategyExecutionEngine drives it."""
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
    strat_exec_engine.execute_strategy = AsyncMock(
        return_value=StrategyExecutionResult(
            strategy_id=strategy.strategy_id,
            strategy_name=strategy.name,
            is_success=True,
            total_stages=1,
            completed_stages_count=1,
            stage_results=[
                CapabilityExecutionResult(
                    capability_id="IMAGE_GENERATE_AND_INSERT",
                    stage_index=0,
                    dispatch_success=True,
                    execution_success=True,
                    stage_status=StageOutcomeStatus.EFFECT_VERIFIED,
                    output={"image_path": "C:\\test.png"},
                )
            ],
            final_stage_status=StageOutcomeStatus.EFFECT_VERIFIED,
        )
    )

    # 3. Mock Observer & Goal Verifier
    observer = MagicMock()
    observer.observe = AsyncMock(return_value=CurrentStateObservation(observation_id="obs_final"))

    goal_verifier = MagicMock()
    goal_verifier.verify_goal_achievement = AsyncMock(
        return_value=MagicMock(is_satisfied=True, status=TaskCompletionStatus.COMPLETED)
    )

    loop = AgentExecutionLoop(
        feasibility_analyzer=feasibility_analyzer,
        strategy_execution_engine=strat_exec_engine,
        observer=observer,
        goal_verifier=goal_verifier,
    )

    # Run loop
    result = await loop.run(
        prompt="Open Paint and draw a portrait of a boy",
        context={"authoritative_strategy_execution": True},
    )

    assert result.is_success is True
    assert result.final_status == TaskCompletionStatus.COMPLETED
    # Strategy engine was directly invoked
    strat_exec_engine.execute_strategy.assert_called_once()
    # Goal verifier checked final reality
    goal_verifier.verify_goal_achievement.assert_called_once()


@pytest.mark.asyncio
async def test_agent_loop_strategy_failure_halts_closed():
    """If StrategyExecutionEngine reports failure, loop returns FAILED without false success."""
    strategy = StrategyOption(
        strategy_id="STRAT_COMPOSITE_TEST",
        name="Composite Strategy",
        description="Fails",
        stages=[StrategyStage(stage_index=0, name="S1", capability_id="C1", description="1", expected_outcome="1")],
        is_available=True,
    )

    feasibility_analyzer = MagicMock()
    feasibility_analyzer.evaluate_feasibility.return_value = FeasibilityAssessment(
        is_feasible=True,
        status=FeasibilityStatus.FEASIBLE,
        matched_strategy=strategy,
        explanation="Strategy viable",
    )

    strat_exec_engine = MagicMock()
    strat_exec_engine.can_execute_strategy.return_value = True
    strat_exec_engine.execute_strategy = AsyncMock(
        return_value=StrategyExecutionResult(
            strategy_id=strategy.strategy_id,
            strategy_name=strategy.name,
            is_success=False,
            total_stages=1,
            completed_stages_count=0,
            failure_code="STAGE_OUTCOME_UNVERIFIED",
            failure_reason="Canvas did not receive image",
            final_stage_status=StageOutcomeStatus.EFFECT_UNVERIFIED,
        )
    )

    observer = MagicMock()
    observer.observe = AsyncMock(return_value=CurrentStateObservation(observation_id="obs_0"))

    loop = AgentExecutionLoop(
        feasibility_analyzer=feasibility_analyzer,
        strategy_execution_engine=strat_exec_engine,
        observer=observer,
    )

    result = await loop.run(
        prompt="Open Paint and insert art",
        context={"authoritative_strategy_execution": True},
    )

    assert result.is_success is False
    assert result.final_status == TaskCompletionStatus.FAILED
    assert result.failure_code == "STAGE_OUTCOME_UNVERIFIED"
