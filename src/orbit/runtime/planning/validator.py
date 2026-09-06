"""Plan validation and epistemic status determination for task planning."""

from __future__ import annotations

from typing import List, Tuple
from orbit.runtime.planning.graph import ActionDependencyGraph
from orbit.runtime.planning.models import (
    ExecutableTaskPlan,
    PlanActionType,
    PlanStatus,
    PlanStep,
)
from orbit.runtime.task_understanding.models import (
    TaskUnderstandingResult,
    TaskUnderstandingStatus,
)


class PlanValidator:
    """Validates structural integrity, dependency safety, and constraint invariants for task plans."""

    def validate_plan(
        self,
        task_id: str,
        description: str,
        graph: ActionDependencyGraph,
        understanding: TaskUnderstandingResult,
    ) -> ExecutableTaskPlan:
        """Validate candidate plan graph and construct final ExecutableTaskPlan."""
        unresolved: List[str] = list(understanding.unresolved_constraints)
        diagnostics: List[str] = list(understanding.diagnostic_messages)

        # 1. Check graph integrity
        is_graph_valid, graph_errors = graph.validate()
        if not is_graph_valid:
            unresolved.extend(graph_errors)
            return ExecutableTaskPlan(
                task_id=task_id,
                description=description,
                status=PlanStatus.FAILED,
                steps=list(graph.steps.values()),
                step_dependencies=graph.get_dependencies_map(),
                unresolved_items=unresolved,
            )

        # 2. Sort topologically
        try:
            sorted_steps = graph.topological_sort()
        except ValueError as e:
            unresolved.append(str(e))
            return ExecutableTaskPlan(
                task_id=task_id,
                description=description,
                status=PlanStatus.FAILED,
                steps=list(graph.steps.values()),
                step_dependencies=graph.get_dependencies_map(),
                unresolved_items=unresolved,
            )

        # 3. Check for empty plan
        if not sorted_steps:
            return ExecutableTaskPlan(
                task_id=task_id,
                description=description,
                status=PlanStatus.INVALID,
                steps=[],
                step_dependencies={},
                unresolved_items=["Plan contains zero executable steps"],
            )

        # 4. Check negative constraints invariant
        # If user explicitly requested NOT to do an action, ensure no active positive step exists
        for step in sorted_steps:
            if step.is_negated and step.action_type not in {
                PlanActionType.ENTER_TEXT,
                PlanActionType.SAVE_DOCUMENT,
                PlanActionType.UNSUPPORTED_ACTION,
            }:
                unresolved.append(f"Negated step '{step.action_type.value}' has no defined negation handler")

        # 5. Check unsupported / ambiguous steps
        has_unsupported = False
        has_ambiguous = False
        supported_count = 0

        for step in sorted_steps:
            if step.action_type == PlanActionType.UNSUPPORTED_ACTION:
                has_unsupported = True
                msg = step.unresolved_reason or f"Step '{step.description}' is unsupported"
                unresolved.append(msg)
            elif step.is_ambiguous:
                has_ambiguous = True
                msg = step.unresolved_reason or f"Step '{step.description}' contains unresolved ambiguity"
                unresolved.append(msg)
            else:
                supported_count += 1

        # 6. Assign status
        if understanding.status == TaskUnderstandingStatus.INVALID:
            status = PlanStatus.INVALID
        elif has_unsupported and supported_count == 0:
            status = PlanStatus.UNSUPPORTED
        elif has_unsupported and supported_count > 0:
            status = PlanStatus.PARTIALLY_PLANNED
        elif has_ambiguous and supported_count == 0:
            status = PlanStatus.AMBIGUOUS
        elif has_ambiguous and supported_count > 0:
            status = PlanStatus.PARTIALLY_PLANNED
        else:
            status = PlanStatus.VALID

        return ExecutableTaskPlan(
            task_id=task_id,
            description=description,
            status=status,
            steps=sorted_steps,
            step_dependencies=graph.get_dependencies_map(),
            unresolved_items=unresolved,
        )
