"""Explicit retry policy and failure classification for closed-loop execution.

Enforces:
- Hard attempt caps
- Replan limits
- Failure classification: RETRYABLE, REPLAN_REQUIRED, TERMINAL
- No unbounded execution / while-True loops
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from orbit.runtime.execution.models import ExecutionPolicy, RecoveryReason
from orbit.runtime.targeting.models import TargetResolutionStatus
from orbit.runtime.verification.models import VerificationOutcome


class FailureCategory(str, Enum):
    """Classification of failure for recovery and retry decisions."""

    RETRYABLE = "RETRYABLE"              # Transient failure eligible for bounded retry
    REPLAN_REQUIRED = "REPLAN_REQUIRED"  # Context/generation changed, requires re-observe and re-plan
    TERMINAL = "TERMINAL"                # Non-recoverable failure; must fail closed immediately


class RetryPolicy(ExecutionPolicy):
    """Configurable, strongly-typed retry and replan policy."""

    max_action_attempts: int = 3
    max_replans: int = 2
    max_consecutive_failures: int = 3

    def is_retryable(self, attempt_count: int) -> bool:
        """Check if an action attempt is within retry limits."""
        return attempt_count < self.max_total_attempts

    def is_replan_allowed(self, replan_count: int) -> bool:
        """Check if a replan cycle is within limits."""
        return replan_count < self.max_recovery_attempts


def classify_verification_failure(outcome: VerificationOutcome) -> FailureCategory:
    """Classify verification outcome for retry/recovery decision."""
    if outcome == VerificationOutcome.VERIFIED_SUCCESS:
        return FailureCategory.RETRYABLE
    if outcome == VerificationOutcome.INCONCLUSIVE:
        return FailureCategory.RETRYABLE
    if outcome == VerificationOutcome.VERIFIED_FAILURE:
        return FailureCategory.RETRYABLE
    if outcome == VerificationOutcome.STALE_EVIDENCE:
        return FailureCategory.REPLAN_REQUIRED
    if outcome == VerificationOutcome.UNSUPPORTED:
        return FailureCategory.TERMINAL
    return FailureCategory.TERMINAL


def classify_resolution_failure(status: TargetResolutionStatus) -> FailureCategory:
    """Classify target resolution status for recovery decision."""
    if status == TargetResolutionStatus.RESOLVED:
        return FailureCategory.RETRYABLE
    if status == TargetResolutionStatus.NOT_FOUND:
        return FailureCategory.RETRYABLE
    if status == TargetResolutionStatus.STALE_OBSERVATION:
        return FailureCategory.REPLAN_REQUIRED
    if status == TargetResolutionStatus.AMBIGUOUS:
        return FailureCategory.TERMINAL
    if status == TargetResolutionStatus.UNSUPPORTED or status == TargetResolutionStatus.INVALID_REQUEST:
        return FailureCategory.TERMINAL
    return FailureCategory.TERMINAL


def classify_failure(
    verification_outcome: Optional[VerificationOutcome] = None,
    resolution_status: Optional[TargetResolutionStatus] = None,
    is_coordinate_valid: bool = True,
    is_generation_valid: bool = True,
    is_takeover_active: bool = False,
    is_cancelled: bool = False,
) -> FailureCategory:
    """Comprehensive failure classifier enforcing safety rules."""
    if is_takeover_active or is_cancelled:
        return FailureCategory.TERMINAL
    if not is_generation_valid:
        return FailureCategory.REPLAN_REQUIRED
    if not is_coordinate_valid:
        return FailureCategory.TERMINAL
    if resolution_status is not None and resolution_status != TargetResolutionStatus.RESOLVED:
        return classify_resolution_failure(resolution_status)
    if verification_outcome is not None and verification_outcome != VerificationOutcome.VERIFIED_SUCCESS:
        return classify_verification_failure(verification_outcome)
    return FailureCategory.TERMINAL
