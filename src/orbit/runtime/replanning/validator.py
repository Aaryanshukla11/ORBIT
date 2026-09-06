"""Validation engine for dynamic repaired execution plans (M1.8 Step 4).

Safety Invariants:
1. Strict DAG Acyclicity: Repaired plans MUST be valid directed acyclic graphs.
2. Completed Step Preservation Gate: All previously SUCCEEDED steps must be preserved.
3. Dependency Integrity: Every step's dependency list must only reference existing step IDs.
4. Fail-Closed Validation: Reject malformed repaired plans before execution dispatch.
"""

from __future__ import annotations

import logging
from typing import Optional, Set

from orbit.runtime.plan_execution.validator import (
    PlanExecutionValidationResult,
    PlanExecutionValidator,
)
from orbit.runtime.planning.graph import ActionDependencyGraph
from orbit.runtime.planning.models import ExecutableTaskPlan, PlanStatus

logger = logging.getLogger(__name__)


class RepairedPlanValidator:
    """Validates structural and safety integrity of repaired plans before resumption."""

    def __init__(self, base_validator: Optional[PlanExecutionValidator] = None) -> None:
        self._base_validator = base_validator or PlanExecutionValidator()

    def validate_repaired_plan(
        self,
        repaired_plan: ExecutableTaskPlan,
        completed_step_ids: Set[str],
    ) -> PlanExecutionValidationResult:
        """Validate that a repaired plan is structurally sound and preserves completed progress."""
        # 1. Base Structural Validation
        base_res = self._base_validator.validate(repaired_plan, allow_draft=False)
        if not base_res.is_valid:
            return PlanExecutionValidationResult(
                is_valid=False,
                error_code=base_res.error_code or "REPAIRED_PLAN_INVALID",
                error_message=f"Repaired plan failed base validation: {base_res.error_message}",
                diagnostics={"base_diagnostics": base_res.diagnostics},
            )

        # 2. Check Completed Steps Preservation
        repaired_step_ids = {s.step_id for s in repaired_plan.steps}
        missing_completed = completed_step_ids - repaired_step_ids
        if missing_completed:
            return PlanExecutionValidationResult(
                is_valid=False,
                error_code="COMPLETED_STEPS_DROPPED",
                error_message=f"Repaired plan dropped previously completed steps: {missing_completed}",
                diagnostics={"missing_completed": list(missing_completed)},
            )

        # 3. Verify Graph Acyclicity
        try:
            dag = ActionDependencyGraph.from_plan(repaired_plan)
            if dag.has_cycles():
                cycle_path = dag.find_cycle_path()
                return PlanExecutionValidationResult(
                    is_valid=False,
                    error_code="REPAIRED_PLAN_CYCLE_DETECTED",
                    error_message=f"Repaired plan contains cyclic dependency: {cycle_path}",
                    diagnostics={"cycle_path": cycle_path},
                )
        except Exception as ex:
            return PlanExecutionValidationResult(
                is_valid=False,
                error_code="REPAIRED_PLAN_GRAPH_ERROR",
                error_message=f"Failed to verify DAG for repaired plan: {ex}",
                diagnostics={"exception": str(ex)},
            )

        return PlanExecutionValidationResult(
            is_valid=True,
            diagnostics={
                "total_steps": len(repaired_plan.steps),
                "preserved_completed_count": len(completed_step_ids),
                "plan_id": repaired_plan.plan_id,
            },
        )
