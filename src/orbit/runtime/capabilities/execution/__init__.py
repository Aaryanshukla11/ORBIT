"""Capability Execution Engine and Runtime Bridge package (M1.9)."""

from orbit.runtime.capabilities.execution.contracts import (
    CapabilityExecutionRequest,
    CapabilityExecutionResult,
    CapabilityExecutor,
    StageOutcomeStatus,
)
from orbit.runtime.capabilities.execution.executor_registry import CapabilityExecutorRegistry
from orbit.runtime.capabilities.execution.image_gen_provider import (
    GeneratedImageResult,
    ImageGenerationProvider,
    NullImageGenerationProvider,
)
from orbit.runtime.capabilities.execution.output_binding import StageOutputBindingError, StageOutputResolver
from orbit.runtime.capabilities.execution.stage_recovery import StageRecoveryManager
from orbit.runtime.capabilities.execution.stage_verifier import StageOutcomeVerifier
from orbit.runtime.capabilities.execution.strategy_execution_engine import (
    StrategyExecutionEngine,
    StrategyExecutionResult,
)

__all__ = [
    "CapabilityExecutionRequest",
    "CapabilityExecutionResult",
    "CapabilityExecutor",
    "StageOutcomeStatus",
    "CapabilityExecutorRegistry",
    "ImageGenerationProvider",
    "GeneratedImageResult",
    "NullImageGenerationProvider",
    "StageOutputResolver",
    "StageOutputBindingError",
    "StageOutcomeVerifier",
    "StageRecoveryManager",
    "StrategyExecutionEngine",
    "StrategyExecutionResult",
]
