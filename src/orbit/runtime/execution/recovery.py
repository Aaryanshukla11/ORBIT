"""Bounded recovery coordinator enforcing strict attempt limits and backoff policies."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from orbit.runtime.execution.models import ExecutionPolicy, RecoveryReason

logger = logging.getLogger(__name__)


class RecoveryCoordinator:
    """Manages explicit recovery budgets and backoff pacing without infinite loops."""

    def __init__(self, policy: ExecutionPolicy, start_time: Optional[float] = None) -> None:
        self._policy = policy
        self._start_time = start_time if start_time is not None else time.perf_counter()
        self._total_attempts = 0
        self._target_resolution_attempts = 0
        self._verification_retries = 0
        self._recovery_attempts = 0
        self._recovery_log: List[Dict[str, Any]] = []

    @property
    def policy(self) -> ExecutionPolicy:
        return self._policy

    @property
    def total_attempts(self) -> int:
        return self._total_attempts

    @property
    def target_resolution_attempts(self) -> int:
        return self._target_resolution_attempts

    @property
    def verification_retries(self) -> int:
        return self._verification_retries

    @property
    def recovery_attempts(self) -> int:
        return self._recovery_attempts

    @property
    def elapsed_seconds(self) -> float:
        return time.perf_counter() - self._start_time

    @property
    def is_timed_out(self) -> bool:
        return self.elapsed_seconds >= self._policy.execution_timeout_seconds

    def record_attempt(self) -> None:
        """Record an action dispatch attempt."""
        self._total_attempts += 1

    def can_recover(self, reason: RecoveryReason) -> bool:
        """Determine if a bounded recovery cycle is authorized by policy."""
        if self.is_timed_out:
            logger.warning("Recovery denied: overall execution timeout expired (%.2fs >= %.2fs)",
                           self.elapsed_seconds, self._policy.execution_timeout_seconds)
            return False

        if self._total_attempts >= self._policy.max_total_attempts:
            logger.warning("Recovery denied: max total attempts exhausted (%d >= %d)",
                           self._total_attempts, self._policy.max_total_attempts)
            return False

        if self._recovery_attempts >= self._policy.max_recovery_attempts:
            logger.warning("Recovery denied: max recovery attempts exhausted (%d >= %d)",
                           self._recovery_attempts, self._policy.max_recovery_attempts)
            return False

        if reason in {RecoveryReason.TARGET_NOT_FOUND, RecoveryReason.TARGET_AMBIGUOUS}:
            if self._target_resolution_attempts >= self._policy.max_target_resolution_attempts:
                logger.warning("Recovery denied: target resolution attempts exhausted (%d >= %d)",
                               self._target_resolution_attempts, self._policy.max_target_resolution_attempts)
                return False

        if reason == RecoveryReason.VERIFICATION_FAILED:
            if self._verification_retries >= self._policy.max_verification_retries:
                logger.warning("Recovery denied: verification retries exhausted (%d >= %d)",
                               self._verification_retries, self._policy.max_verification_retries)
                return False

        return True

    def record_recovery(
        self,
        reason: RecoveryReason,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a recovery event and consume relevant budget."""
        self._recovery_attempts += 1

        if reason in {RecoveryReason.TARGET_NOT_FOUND, RecoveryReason.TARGET_AMBIGUOUS}:
            self._target_resolution_attempts += 1

        if reason == RecoveryReason.VERIFICATION_FAILED:
            self._verification_retries += 1

        entry = {
            "recovery_index": self._recovery_attempts,
            "reason": reason.value,
            "timestamp_s": time.perf_counter() - self._start_time,
            "total_attempts": self._total_attempts,
            "details": details or {},
        }
        self._recovery_log.append(entry)
        logger.info("Recorded recovery #%d for reason %s: %s", self._recovery_attempts, reason.value, details)

    def compute_backoff_delay(self) -> float:
        """Compute conservative bounded backoff delay in seconds."""
        if self._policy.retry_backoff_base_ms <= 0:
            return 0.0
        exponent = max(0, self._recovery_attempts - 1)
        delay_ms = min(self._policy.retry_backoff_base_ms * (2 ** exponent), 2000.0)
        return delay_ms / 1000.0

    def get_exhaustion_reason(self, reason: RecoveryReason) -> str:
        """Provide a descriptive diagnostic message for budget exhaustion."""
        if self.is_timed_out:
            return f"Execution timeout exceeded ({self.elapsed_seconds:.2f}s >= {self._policy.execution_timeout_seconds:.2f}s)"
        if self._total_attempts >= self._policy.max_total_attempts:
            return f"Max total action dispatch attempts exhausted ({self._total_attempts}/{self._policy.max_total_attempts})"
        if self._recovery_attempts >= self._policy.max_recovery_attempts:
            return f"Max recovery cycles exhausted ({self._recovery_attempts}/{self._policy.max_recovery_attempts})"
        if reason in {RecoveryReason.TARGET_NOT_FOUND, RecoveryReason.TARGET_AMBIGUOUS}:
            return f"Target resolution retry limit reached ({self._target_resolution_attempts}/{self._policy.max_target_resolution_attempts})"
        if reason == RecoveryReason.VERIFICATION_FAILED:
            return f"Verification retry limit reached ({self._verification_retries}/{self._policy.max_verification_retries})"
        return f"Recovery policy denied retry for reason: {reason.value}"

    def get_diagnostic_summary(self) -> Dict[str, Any]:
        return {
            "total_attempts": self._total_attempts,
            "recovery_attempts": self._recovery_attempts,
            "target_resolution_attempts": self._target_resolution_attempts,
            "verification_retries": self._verification_retries,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "log": list(self._recovery_log),
        }
