"""Validation logic for plan execution readiness (M1.8 Step 3).

Ensures plans satisfy epistemic validity, structural DAG constraints, and capability readiness
before any closed-loop execution is attempted.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from orbit.adapters.registry import CapabilityRegistry
from orbit.contracts.capabilities import CapabilityType
from orbit.runtime.planning.graph import ActionDependencyGraph
from orbit.runtime.planning.models import ExecutableTaskPlan, PlanStatus

logger = logging.getLogger(__name__)


class PlanExecutionValidationResult:
    """Result of pre-execution plan validation."""

    def __init__(
        self,
        is_valid: bool,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        diagnostics: Optional[Any] = None,
    ) -> None:
        self.is_valid = is_valid
        self.error_code = error_code
        self.error_message = error_message
        self.diagnostics = diagnostics if diagnostics is not None else []

    def __bool__(self) -> bool:
        return self.is_valid


class PlanExecutionValidator:
    """Validates that an ExecutableTaskPlan is structurally and contextually ready for execution."""

    def validate(
        self,
        plan: ExecutableTaskPlan,
        capability_registry: Optional[CapabilityRegistry] = None,
        allow_draft: bool = False,
    ) -> PlanExecutionValidationResult:
        """Validate plan validity, step count, DAG acyclicity, and required capabilities."""
        diagnostics: List[str] = []

        # 1. Null / Type check
        if plan is None or not isinstance(plan, ExecutableTaskPlan):
            return PlanExecutionValidationResult(
                is_valid=False,
                error_code="INVALID_PLAN_INSTANCE",
                error_message="Plan is None or not an ExecutableTaskPlan instance",
            )

        # 2. Status check
        if plan.status != PlanStatus.VALID and not (allow_draft and plan.status == PlanStatus.DRAFT):
            return PlanExecutionValidationResult(
                is_valid=False,
                error_code=f"PLAN_STATUS_{plan.status.value}",
                error_message=f"Cannot execute plan with status '{plan.status.value}'. Only VALID plans are executable.",
                diagnostics=[f"Unresolved items: {plan.unresolved_items}"],
            )

        # 3. Step count check
        if not plan.steps:
            return PlanExecutionValidationResult(
                is_valid=False,
                error_code="EMPTY_PLAN",
                error_message="Plan contains zero execution steps",
            )

        # 4. DAG Cycle / Topological validation
        graph = ActionDependencyGraph.from_plan(plan)
        if graph.has_cycles():
            cycle_desc = graph.find_cycle_path()
            return PlanExecutionValidationResult(
                is_valid=False,
                error_code="CYCLIC_DEPENDENCY_GRAPH",
                error_message=f"Plan action graph contains cycles: {cycle_desc}",
                diagnostics=[f"Cycles detected: {cycle_desc}"],
            )

        # 5. Dependency reference integrity
        step_ids = {s.step_id for s in plan.steps}
        for step in plan.steps:
            for dep in step.dependencies:
                if dep not in step_ids:
                    return PlanExecutionValidationResult(
                        is_valid=False,
                        error_code="MISSING_DEPENDENCY_REFERENCE",
                        error_message=f"Step '{step.step_id}' references unknown dependency '{dep}'",
                        diagnostics=[f"Missing dependency: {dep}"],
                    )

        # 6. Capability check if registry provided
        if capability_registry is not None:
            if not capability_registry.is_ready(CapabilityType.OBSERVATION):
                diagnostics.append("Warning: OBSERVATION capability is not marked READY in registry")

        return PlanExecutionValidationResult(
            is_valid=True,
            diagnostics=diagnostics,
        )
