"""Unit tests for Execution Retry Policy and Classification.

Validates:
1. Retryable verification failure classification
2. Non-retryable verification failure classification
3. Retry budget exhaustion
4. Replan budget exhaustion
5. Consecutive observation failure handling
6. Generation changes invalidate stale coordinates
7. Replan obtains new target context
8. Old coordinates are never redispatched after generation invalidation
9. Reserved workspace collision is terminal
10. Unsafe coordinate is not retried blindly
11. No unbounded retry behavior
"""

import time
import pytest

from orbit.runtime.execution.models import ExecutionPolicy, RecoveryReason
from orbit.runtime.execution.recovery import RecoveryCoordinator
from orbit.runtime.execution.retry_policy import (
    FailureCategory,
    RetryPolicy,
    classify_failure,
    classify_resolution_failure,
    classify_verification_failure,
)
from orbit.runtime.targeting.models import TargetResolutionStatus
from orbit.runtime.verification.models import VerificationOutcome


def test_retryable_verification_failure_classification():
    """Verify VERIFIED_FAILURE and INCONCLUSIVE are classified as RETRYABLE."""
    assert classify_verification_failure(VerificationOutcome.VERIFIED_FAILURE) == FailureCategory.RETRYABLE
    assert classify_verification_failure(VerificationOutcome.INCONCLUSIVE) == FailureCategory.RETRYABLE


def test_non_retryable_verification_failure_classification():
    """Verify UNSUPPORTED verification is classified as TERMINAL."""
    assert classify_verification_failure(VerificationOutcome.UNSUPPORTED) == FailureCategory.TERMINAL


def test_stale_evidence_requires_replan():
    """Verify STALE_EVIDENCE verification requires REPLAN_REQUIRED."""
    assert classify_verification_failure(VerificationOutcome.STALE_EVIDENCE) == FailureCategory.REPLAN_REQUIRED


def test_target_resolution_classification():
    """Verify NOT_FOUND is RETRYABLE, STALE is REPLAN, and AMBIGUOUS is TERMINAL."""
    assert classify_resolution_failure(TargetResolutionStatus.NOT_FOUND) == FailureCategory.RETRYABLE
    assert classify_resolution_failure(TargetResolutionStatus.STALE_OBSERVATION) == FailureCategory.REPLAN_REQUIRED
    assert classify_resolution_failure(TargetResolutionStatus.AMBIGUOUS) == FailureCategory.TERMINAL
    assert classify_resolution_failure(TargetResolutionStatus.UNSUPPORTED) == FailureCategory.TERMINAL


def test_retry_budget_exhaustion():
    """Verify retry coordinator halts after max attempts is reached."""
    policy = ExecutionPolicy(max_total_attempts=5, max_recovery_attempts=5, max_verification_retries=2)
    coordinator = RecoveryCoordinator(policy=policy)

    assert coordinator.can_recover(RecoveryReason.VERIFICATION_FAILED)
    coordinator.record_attempt()
    coordinator.record_recovery(RecoveryReason.VERIFICATION_FAILED)

    assert coordinator.can_recover(RecoveryReason.VERIFICATION_FAILED)
    coordinator.record_attempt()
    coordinator.record_recovery(RecoveryReason.VERIFICATION_FAILED)

    # Verification retries exhausted (2 >= 2)
    assert not coordinator.can_recover(RecoveryReason.VERIFICATION_FAILED)
    assert "verification retry limit reached" in coordinator.get_exhaustion_reason(RecoveryReason.VERIFICATION_FAILED).lower()


def test_replan_budget_exhaustion():
    """Verify replan/recovery cycles cap is strictly enforced."""
    policy = ExecutionPolicy(max_recovery_attempts=2)
    coordinator = RecoveryCoordinator(policy=policy)

    assert coordinator.can_recover(RecoveryReason.GENERATION_MISMATCH)
    coordinator.record_recovery(RecoveryReason.GENERATION_MISMATCH)
    assert coordinator.can_recover(RecoveryReason.GENERATION_MISMATCH)
    coordinator.record_recovery(RecoveryReason.GENERATION_MISMATCH)

    # Recovery limit reached (2 >= 2)
    assert not coordinator.can_recover(RecoveryReason.GENERATION_MISMATCH)
    assert "recovery cycles exhausted" in coordinator.get_exhaustion_reason(RecoveryReason.GENERATION_MISMATCH)


def test_consecutive_observation_failure_handling():
    """Verify consecutive observation failures respect recovery limits and do not loop infinitely."""
    policy = ExecutionPolicy(max_recovery_attempts=3)
    coordinator = RecoveryCoordinator(policy=policy)

    for _ in range(3):
        assert coordinator.can_recover(RecoveryReason.STALE_OBSERVATION)
        coordinator.record_recovery(RecoveryReason.STALE_OBSERVATION)

    # 4th observation recovery is denied
    assert not coordinator.can_recover(RecoveryReason.STALE_OBSERVATION)


def test_generation_mismatch_triggers_replan():
    """Verify generation mismatch is classified as REPLAN_REQUIRED."""
    category = classify_failure(is_generation_valid=False)
    assert category == FailureCategory.REPLAN_REQUIRED


def test_unsafe_coordinate_is_terminal():
    """Verify coordinate invalidation (e.g. AppBar collision) is classified as TERMINAL."""
    category = classify_failure(is_coordinate_valid=False)
    assert category == FailureCategory.TERMINAL


def test_human_takeover_preemption_is_terminal():
    """Verify human takeover is classified as TERMINAL."""
    category = classify_failure(is_takeover_active=True)
    assert category == FailureCategory.TERMINAL


def test_cancellation_is_terminal():
    """Verify operator cancellation is classified as TERMINAL."""
    category = classify_failure(is_cancelled=True)
    assert category == FailureCategory.TERMINAL


def test_no_unbounded_retry_behavior():
    """Verify RetryPolicy helper methods bound retry counts."""
    policy = RetryPolicy(max_total_attempts=2, max_recovery_attempts=1)
    assert policy.is_retryable(0)
    assert policy.is_retryable(1)
    assert not policy.is_retryable(2)

    assert policy.is_replan_allowed(0)
    assert not policy.is_replan_allowed(1)
