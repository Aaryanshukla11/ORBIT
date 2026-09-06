"""ORBIT Closed-Loop Execution Subsystem."""

from orbit.runtime.execution.engine import ClosedLoopExecutionEngine
from orbit.runtime.execution.models import (
    ClosedLoopExecutionResult,
    ExecutionAttemptRecord,
    ExecutionPolicy,
    ExecutionState,
    RecoveryReason,
)
from orbit.runtime.execution.recovery import RecoveryCoordinator
from orbit.runtime.execution.retry_policy import (
    FailureCategory,
    RetryPolicy,
    classify_failure,
    classify_resolution_failure,
    classify_verification_failure,
)
from orbit.runtime.execution.context import (
    CancellationReason,
    DispatchStage,
    ExecutionContext,
    PreemptionRecord,
)
from orbit.runtime.execution.safety_gate import (
    AutonomousDispatchGate,
    PreemptionSafetyError,
)
from orbit.runtime.execution.state_machine import ClosedLoopStateMachine

__all__ = [
    "AutonomousDispatchGate",
    "CancellationReason",
    "DispatchStage",
    "ExecutionContext",
    "PreemptionRecord",
    "PreemptionSafetyError",
    "ClosedLoopExecutionEngine",
    "ClosedLoopStateMachine",
    "ClosedLoopExecutionResult",
    "ExecutionAttemptRecord",
    "ExecutionPolicy",
    "ExecutionState",
    "FailureCategory",
    "RecoveryCoordinator",
    "RecoveryReason",
    "RetryPolicy",
    "classify_failure",
    "classify_resolution_failure",
    "classify_verification_failure",
]
