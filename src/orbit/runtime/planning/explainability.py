"""Deterministic plan explainability generator answering provenance and dependency questions."""

from __future__ import annotations

from typing import Any, Dict, List
from orbit.runtime.planning.models import ExecutableTaskPlan, PlanStep


class PlanExplainer:
    """Generates machine-readable, deterministic explanations for planned steps and dependencies."""

    def explain_plan(self, plan: ExecutableTaskPlan) -> Dict[str, Any]:
        """Produce a complete explainability dictionary for an ExecutableTaskPlan."""
        step_map = {step.step_id: step for step in plan.steps}
        step_explanations: Dict[str, Any] = {}
        deferred_count = 0
        negated_count = 0
        ambiguous_count = 0

        for step in plan.steps:
            dep_descs = [
                f"[{step_map[d].step_index}] {step_map[d].description}"
                for d in step.dependencies
                if d in step_map
            ]

            deferred_info = None
            if step.deferred_grounding:
                deferred_count += 1
                deferred_info = {
                    "strategy_preferences": [
                        s.value for s in step.deferred_grounding.strategy_preferences
                    ],
                    "target_semantic_type": step.deferred_grounding.target_reference.semantic_type,
                    "target_identifier": step.deferred_grounding.target_reference.identifier,
                    "grounding_notes": step.deferred_grounding.grounding_notes,
                }

            if step.is_negated:
                negated_count += 1
            if step.is_ambiguous:
                ambiguous_count += 1

            step_explanations[step.step_id] = {
                "step_index": step.step_index,
                "action_type": step.action_type.value,
                "description": step.description,
                "why_created": step.evidence,
                "must_execute_after": dep_descs,
                "preconditions": [p.model_dump() for p in step.preconditions],
                "postconditions": [p.model_dump() for p in step.postconditions],
                "deferred_runtime_perception": deferred_info,
                "is_negated": step.is_negated,
                "is_ambiguous": step.is_ambiguous,
                "unresolved_reason": step.unresolved_reason,
            }

        return {
            "plan_id": plan.plan_id,
            "task_id": plan.task_id,
            "status": plan.status.value,
            "total_steps": len(plan.steps),
            "deferred_perception_steps": deferred_count,
            "negated_steps": negated_count,
            "ambiguous_steps": ambiguous_count,
            "steps": step_explanations,
        }
