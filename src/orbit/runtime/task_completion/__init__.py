"""Task Completion Verification subsystem for ORBIT (M1.8 Step 5)."""

from orbit.runtime.task_completion.completion_engine import TaskCompletionEngine
from orbit.runtime.task_completion.evidence import CompletionEvidenceCollector
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.task_completion.models import (
    GoalVerificationResult,
    TaskCompletionEvidence,
    TaskCompletionStatus,
    TaskExecutionResult,
)

__all__ = [
    "CompletionEvidenceCollector",
    "GoalVerifier",
    "GoalVerificationResult",
    "TaskCompletionEngine",
    "TaskCompletionEvidence",
    "TaskCompletionStatus",
    "TaskExecutionResult",
]
