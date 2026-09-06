"""Audit history tracker, budget limiter, and loop detector for dynamic replanning (M1.8 Step 4).

Safety Invariants:
1. Strict Budget Bounds: Enforce global and per-step retry limits fail-closed.
2. Cycle/Loop Detection: Detect repeating failure signatures across plan revisions and fail closed immediately.
3. Immutable Audit Trail: Every replan event is preserved in structured history records.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Dict, List, Optional, Set

from orbit.runtime.planning.models import PlanStep
from orbit.runtime.replanning.models import (
    FailureClassification,
    FailureSignature,
    ReplanBudget,
    ReplanHistoryRecord,
    ReplanReason,
    ReplanStatus,
)

logger = logging.getLogger(__name__)


class ReplanHistoryTracker:
    """Tracks plan replan history, budget consumption, and prevents cyclic execution loops."""

    def __init__(self, budget: Optional[ReplanBudget] = None) -> None:
        self._budget = budget or ReplanBudget()
        self._records: List[ReplanHistoryRecord] = []
        self._step_replan_counts: Dict[str, int] = {}
        self._seen_signatures: List[FailureSignature] = []
        self._start_time_perf = time.perf_counter()

    @property
    def budget(self) -> ReplanBudget:
        return self._budget

    @property
    def total_replans(self) -> int:
        return len(self._records)

    @property
    def successful_replans(self) -> int:
        return sum(1 for r in self._records if r.status == ReplanStatus.RESUMED)

    @property
    def records(self) -> List[ReplanHistoryRecord]:
        return list(self._records)

    def get_step_replan_count(self, step_id: str) -> int:
        return self._step_replan_counts.get(step_id, 0)

    def is_budget_exhausted(self, step_id: Optional[str] = None) -> bool:
        """Check if global or per-step replan limits have been exceeded."""
        if self.successful_replans >= self._budget.max_global_replans:
            logger.warning("Global replan budget exhausted (%d >= %d)", self.successful_replans, self._budget.max_global_replans)
            return True

        if step_id is not None:
            count = self.get_step_replan_count(step_id)
            if count >= self._budget.max_step_replans:
                logger.warning("Step %s replan budget exhausted (%d >= %d)", step_id, count, self._budget.max_step_replans)
                return True

        elapsed_ms = (time.perf_counter() - self._start_time_perf) * 1000.0
        if elapsed_ms > self._budget.max_total_elapsed_ms:
            logger.warning("Replan time budget exhausted (%.1fms > %.1fms)", elapsed_ms, self._budget.max_total_elapsed_ms)
            return True

        return False

    def create_signature(
        self,
        step: PlanStep,
        classification: FailureClassification,
        desktop_generation_id: Optional[int] = None,
    ) -> FailureSignature:
        """Generate a deterministic FailureSignature from step and classification."""
        target_id = None
        if step.target:
            target_id = step.target.identifier or step.target.semantic_type
        elif step.deferred_grounding:
            target_id = step.deferred_grounding.target_reference.identifier

        return FailureSignature(
            step_id=step.step_id,
            action_type=step.action_type,
            reason=classification.reason,
            failure_code=classification.failure_code,
            target_identifier=target_id,
            desktop_generation_id=desktop_generation_id,
        )

    def is_cyclic_loop(self, signature: FailureSignature) -> bool:
        """Check if the exact same failure signature has recurred without progress."""
        sig_key = signature.signature_key()
        occurrences = sum(1 for s in self._seen_signatures if s.signature_key() == sig_key)
        if occurrences >= 1:
            logger.warning("Cyclic failure loop detected for signature: %s (occurred %d times)", sig_key, occurrences + 1)
            return True
        return False

    def record_replan(
        self,
        step: PlanStep,
        classification: FailureClassification,
        repaired_plan_id: Optional[str] = None,
        preserved_step_ids: Optional[List[str]] = None,
        inserted_step_ids: Optional[List[str]] = None,
        removed_step_ids: Optional[List[str]] = None,
        desktop_generation_id: Optional[int] = None,
        status: ReplanStatus = ReplanStatus.RESUMED,
        metadata: Optional[Dict] = None,
    ) -> ReplanHistoryRecord:
        """Record an immutable replan event in history and update metrics."""
        step_id = step.step_id
        signature = self.create_signature(step, classification, desktop_generation_id)
        self._seen_signatures.append(signature)

        self._step_replan_counts[step_id] = self._step_replan_counts.get(step_id, 0) + 1
        revision_id = len(self._records) + 1

        record = ReplanHistoryRecord(
            revision_id=revision_id,
            trigger_step_id=step_id,
            classification=classification,
            signature=signature,
            repaired_plan_id=repaired_plan_id,
            preserved_step_ids=preserved_step_ids or [],
            inserted_step_ids=inserted_step_ids or [],
            removed_step_ids=removed_step_ids or [],
            timestamp_utc=datetime.now(timezone.utc),
            elapsed_duration_ms=(time.perf_counter() - self._start_time_perf) * 1000.0,
            status=status,
            metadata=metadata or {},
        )
        self._records.append(record)
        return record
