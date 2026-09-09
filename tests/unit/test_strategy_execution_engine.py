"""Unit tests for StrategyExecutionEngine (M1.9 Component 3)."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from orbit.runtime.capabilities.execution.contracts import (
    CapabilityExecutionRequest,
    CapabilityExecutionResult,
    CapabilityExecutor,
    StageOutcomeStatus,
)
from orbit.runtime.capabilities.execution.executor_registry import CapabilityExecutorRegistry
from orbit.runtime.capabilities.execution.strategy_execution_engine import (
    StrategyExecutionEngine,
)
from orbit.runtime.capabilities.models import (
    Capability,
    CapabilityCategory,
    StrategyOption,
    StrategyStage,
)
from orbit.runtime.capabilities.registry import CapabilityRegistry
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective


class MockStepExecutor(CapabilityExecutor):
    def __init__(self, cid: str, produces_output: dict = None, should_succeed: bool = True) -> None:
        super().__init__(capability_id=cid)
        self.produces_output = produces_output or {}
        self.should_succeed = should_succeed
        self.execution_calls = []

    def is_available(self) -> bool:
        return True

    def validate_inputs(self, parameters):
        return True, None

    async def execute(self, request: CapabilityExecutionRequest) -> CapabilityExecutionResult:
        self.execution_calls.append(request)
        if not self.should_succeed:
            return CapabilityExecutionResult(
                capability_id=self.capability_id,
                stage_index=request.stage_index,
                dispatch_success=False,
                execution_success=False,
                stage_status=StageOutcomeStatus.FAILED,
                failure_code="MOCK_EXEC_FAILED",
                failure_reason="Deliberate mock failure",
            )
        return CapabilityExecutionResult(
            capability_id=self.capability_id,
            stage_index=request.stage_index,
            dispatch_success=True,
            execution_success=True,
            stage_status=StageOutcomeStatus.EFFECT_VERIFIED,
            output=dict(self.produces_output),
        )


@pytest.mark.asyncio
async def test_strategy_engine_sequential_stages_and_output_binding():
    """Engine executes stages sequentially and passes Stage 0 outputs to Stage 1."""
    cap_reg = CapabilityRegistry(register_defaults=False)
    cap_reg.register(Capability(capability_id="STAGE_A", name="A", description="A", category=CapabilityCategory.DESKTOP_CONTROL, is_available=True))
    cap_reg.register(Capability(capability_id="STAGE_B", name="B", description="B", category=CapabilityCategory.INPUT, is_available=True))

    exec_reg = CapabilityExecutorRegistry(capability_registry=cap_reg)
    exec_a = MockStepExecutor("STAGE_A", produces_output={"artifact": "file_123.png"})
    exec_b = MockStepExecutor("STAGE_B", produces_output={"result": "done"})
    exec_reg.register_executor(exec_a)
    exec_reg.register_executor(exec_b)

    # Mock Observer
    observer = MagicMock()
    obs = CurrentStateObservation(observation_id="obs_test")
    observer.observe = AsyncMock(return_value=obs)

    engine = StrategyExecutionEngine(executor_registry=exec_reg, observer=observer)

    strategy = StrategyOption(
        strategy_id="STRAT_TEST",
        name="Sequential Test Strategy",
        description="Test",
        stages=[
            StrategyStage(
                stage_index=0,
                name="EXECUTE_A",
                capability_id="STAGE_A",
                description="Step A",
                expected_outcome="outcome_a",
                parameters={"init_key": "val"},
            ),
            StrategyStage(
                stage_index=1,
                name="EXECUTE_B",
                capability_id="STAGE_B",
                description="Step B",
                expected_outcome="outcome_b",
                parameters={"consumed_artifact": "{{stage_0.artifact}}"},
            ),
        ],
    )

    objective = StructuredObjective(raw_prompt="Test", user_goal="Test pipeline", end_condition="Done")

    result = await engine.execute_strategy(strategy=strategy, objective=objective)

    assert result.is_success is True
    assert result.completed_stages_count == 2
    assert len(result.stage_results) == 2

    # Verify Stage B received bound output from Stage A
    assert len(exec_b.execution_calls) == 1
    passed_params = exec_b.execution_calls[0].parameters
    assert passed_params["consumed_artifact"] == "file_123.png"


@pytest.mark.asyncio
async def test_strategy_engine_fails_closed_on_stage_failure():
    """If an intermediate stage fails, execution halts and returns failure status."""
    cap_reg = CapabilityRegistry(register_defaults=False)
    cap_reg.register(Capability(capability_id="STEP_1", name="1", description="1", category=CapabilityCategory.DESKTOP_CONTROL, is_available=True))
    cap_reg.register(Capability(capability_id="STEP_2", name="2", description="2", category=CapabilityCategory.INPUT, is_available=True))

    exec_reg = CapabilityExecutorRegistry(capability_registry=cap_reg)
    exec_1 = MockStepExecutor("STEP_1", should_succeed=False)
    exec_2 = MockStepExecutor("STEP_2", should_succeed=True)
    exec_reg.register_executor(exec_1)
    exec_reg.register_executor(exec_2)

    engine = StrategyExecutionEngine(executor_registry=exec_reg)

    strategy = StrategyOption(
        strategy_id="FAILING_STRAT",
        name="Failing Strategy",
        description="Fails at step 1",
        stages=[
            StrategyStage(stage_index=0, name="S1", capability_id="STEP_1", description="1", expected_outcome="1"),
            StrategyStage(stage_index=1, name="S2", capability_id="STEP_2", description="2", expected_outcome="2"),
        ],
    )

    objective = StructuredObjective(raw_prompt="Test fail closed", user_goal="Test fail closed", end_condition="Done")
    result = await engine.execute_strategy(strategy=strategy, objective=objective)

    assert result.is_success is False
    assert result.completed_stages_count == 0
    assert result.failure_code == "MOCK_EXEC_FAILED"
    # Step 2 was never executed
    assert len(exec_2.execution_calls) == 0
