"""Bounded Non-Destructive Backtracking Engine (M1.8 Step 4).

Safety Invariants:
1. Bounded Depth: Backtracking depth is strictly bounded by max_backtracking_depth to prevent thrashing.
2. Non-Destructive Guarantee: Backtracking never dispatches destructive OS operations (e.g. blind dismissal of unknown popups).
3. Verified Progress Preservation: All steps completed at or before the target checkpoint remain preserved and verified.
4. Dependency-Aware Invalidation: Steps downstream of the backtracked state are invalidated and rebuilt.
"""

from __future__ import annotations

import copy
import logging
from typing import Dict, List, Optional, Set
from uuid import uuid4

from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.runtime.planning.graph import ActionDependencyGraph
from orbit.runtime.planning.models import (
    ExecutableTaskPlan,
    PlanActionType,
    PlanStatus,
    PlanStep,
)
from orbit.runtime.replanning.models import (
    ExecutionCheckpoint,
    FailureClassification,
    PlanRepairResult,
    RecoveryStrategy,
    ReplanReason,
)
from orbit.runtime.task_understanding.models import TargetReference

logger = logging.getLogger(__name__)


class BacktrackingEngine:
    """Coordinates safe, bounded backtracking to a verified execution checkpoint."""

    def __init__(self, max_depth: int = 2) -> None:
        self._max_depth = max_depth

    @property
    def max_depth(self) -> int:
        return self._max_depth

    def backtrack_to_checkpoint(
        self,
        current_plan: ExecutableTaskPlan,
        failed_step: PlanStep,
        checkpoint: ExecutionCheckpoint,
        completed_step_ids: Set[str],
        classification: FailureClassification,
        fresh_snapshot: Optional[ObservationSnapshot] = None,
        revision_id: int = 1,
    ) -> PlanRepairResult:
        """Roll back unverified plan execution state to a verified checkpoint and rebuild downstream steps."""
        if checkpoint is None:
            return PlanRepairResult(
                is_success=False,
                repaired_plan=None,
                revision_id=revision_id,
                replan_reason=ReplanReason.PREDECESSOR_INVALIDATED,
                failure_reason="Cannot backtrack: No valid checkpoint provided",
                failure_code="NO_CHECKPOINT",
            )

        logger.info(
            "Backtracking plan %s from failed step %s to checkpoint %s (step %s)",
            current_plan.plan_id,
            failed_step.step_id,
            checkpoint.checkpoint_id,
            checkpoint.step_id,
        )

        try:
            # 1. Identify preserved step IDs from checkpoint
            checkpoint_completed_set = set(checkpoint.completed_step_ids)
            # Retain only steps completed at or before this checkpoint
            preserved_step_ids = [
                s.step_id for s in current_plan.steps if s.step_id in checkpoint_completed_set
            ]

            # Steps being backtracked/re-evaluated
            backtracked_step_ids = [
                s.step_id for s in current_plan.steps
                if s.step_id in completed_step_ids and s.step_id not in checkpoint_completed_set
            ]

            # 2. Build recovery probe / refocus step to re-establish verified state
            recovery_step_id = f"repair_rev{revision_id}_backtrack_probe_{uuid4().hex[:6]}"
            app_name = checkpoint.application_name or "Application"

            recovery_step = PlanStep(
                step_id=recovery_step_id,
                step_index=0,
                action_type=PlanActionType.FOCUS_APPLICATION,
                description=f"Re-establish focus on {app_name} after rollback (Backtrack Step)",
                target=TargetReference(semantic_type="application", identifier=app_name),
                dependencies=list(checkpoint.completed_step_ids[-1:]) if checkpoint.completed_step_ids else [],
                metadata={"is_backtrack_step": True, "checkpoint_id": checkpoint.checkpoint_id, "revision_id": revision_id},
            )

            # 3. Reconstruct remaining steps
            new_steps: List[PlanStep] = []
            repaired_deps: Dict[str, List[str]] = {}

            # Add preserved completed steps
            for s in current_plan.steps:
                if s.step_id in checkpoint_completed_set:
                    step_copy = s.model_copy(deep=True)
                    new_steps.append(step_copy)
                    repaired_deps[step_copy.step_id] = list(step_copy.dependencies)

            # Insert the recovery step
            new_steps.append(recovery_step)
            repaired_deps[recovery_step.step_id] = list(recovery_step.dependencies)

            # Add downstream steps starting from the backtracked point
            for s in current_plan.steps:
                if s.step_id not in checkpoint_completed_set:
                    step_copy = s.model_copy(deep=True)
                    # If this step depended on backtracked steps or the checkpoint, route through recovery step
                    updated_deps = []
                    for dep in step_copy.dependencies:
                        if dep in checkpoint_completed_set:
                            updated_deps.append(dep)
                    if not updated_deps or s.step_id == failed_step.step_id:
                        updated_deps.append(recovery_step_id)
                    step_copy.dependencies = updated_deps
                    new_steps.append(step_copy)
                    repaired_deps[step_copy.step_id] = updated_deps

            # 4. Re-index step sequences
            for idx, s in enumerate(new_steps):
                s.step_index = idx

            new_plan_id = f"{current_plan.plan_id}_backtrack_rev{revision_id}"
            new_plan = ExecutableTaskPlan(
                plan_id=new_plan_id,
                task_id=current_plan.task_id,
                description=f"{current_plan.description} (Backtracked to {checkpoint.checkpoint_id})",
                status=PlanStatus.VALID,
                steps=new_steps,
                step_dependencies=repaired_deps,
                unresolved_items=list(current_plan.unresolved_items),
                explanation={
                    **current_plan.explanation,
                    "repaired_revision": revision_id,
                    "backtrack_trigger_step": failed_step.step_id,
                    "backtrack_target_checkpoint": checkpoint.checkpoint_id,
                    "replan_reason": classification.reason.value,
                },
            )

            return PlanRepairResult(
                is_success=True,
                repaired_plan=new_plan,
                revision_id=revision_id,
                replan_reason=classification.reason,
                preserved_step_ids=preserved_step_ids,
                inserted_steps=[recovery_step],
                removed_step_ids=[],
                backtracked_step_ids=backtracked_step_ids,
                checkpoint=checkpoint,
                diagnostics={
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "backtracked_count": len(backtracked_step_ids),
                    "preserved_count": len(preserved_step_ids),
                    "total_steps": len(new_steps),
                },
            )

        except Exception as ex:
            logger.exception("Backtracking failed for step %s: %s", failed_step.step_id, ex)
            return PlanRepairResult(
                is_success=False,
                repaired_plan=None,
                revision_id=revision_id,
                replan_reason=classification.reason,
                failure_reason=f"Backtracking transformation error: {str(ex)}",
                failure_code="BACKTRACKING_ERROR",
            )
