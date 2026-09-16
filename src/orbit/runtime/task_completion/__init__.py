"""Task Completion and Action Verification subsystem for ORBIT."""

from orbit.runtime.task_completion.evidence import CompletionEvidenceCollector
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.task_completion.models import (
    GoalVerificationResult,
    TaskCompletionEvidence,
    TaskCompletionStatus,
    TaskExecutionResult,
)
from orbit.runtime.task_completion.multi_evidence_verifier import (
    MultiEvidenceActionVerifier,
    MultiEvidenceVerificationResult,
)

__all__ = [
    "CompletionEvidenceCollector",
    "GoalVerifier",
    "GoalVerificationResult",
    "MultiEvidenceActionVerifier",
    "MultiEvidenceVerificationResult",
    "TaskCompletionEvidence",
    "TaskCompletionStatus",
    "TaskExecutionResult",
]
