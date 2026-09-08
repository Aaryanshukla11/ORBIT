"""Core planning engine constructing validated, dependency-aware execution graphs from task understanding."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from orbit.runtime.planning.explainability import PlanExplainer
from orbit.runtime.planning.graph import ActionDependencyGraph
from orbit.runtime.planning.models import (
    ExecutableTaskPlan,
    PlanStatus,
    PlanStep,
)
from orbit.runtime.planning.policies import PlanningRuleRegistry
from orbit.runtime.planning.validator import PlanValidator
from orbit.runtime.task_understanding.engine import TaskUnderstandingEngine
from orbit.runtime.task_understanding.models import (
    TaskUnderstandingResult,
    TaskUnderstandingStatus,
)


class TaskPlanningEngine:
    """Core facade for ORBIT Task Planning (M1.8 Step 2).

    Transforms structured intent sequences into validated, dependency-aware execution plans.
    Operates 100% locally and deterministically with zero external LLM dependencies and zero OS side-effects.
    """

    def __init__(
        self,
        rule_registry: Optional[PlanningRuleRegistry] = None,
        validator: Optional[PlanValidator] = None,
        explainer: Optional[PlanExplainer] = None,
        understanding_engine: Optional[TaskUnderstandingEngine] = None,
    ):
        self._rules = rule_registry or PlanningRuleRegistry()
        self._validator = validator or PlanValidator()
        self._explainer = explainer or PlanExplainer()
        self._understanding_engine = understanding_engine or TaskUnderstandingEngine()

    def plan_task(
        self,
        understanding: Union[TaskUnderstandingResult, str],
        task_id: Optional[str] = None,
    ) -> ExecutableTaskPlan:
        """Generate a validated ExecutableTaskPlan from a TaskUnderstandingResult or raw prompt."""
        if isinstance(understanding, str):
            understanding_result = self._understanding_engine.understand(understanding)
            resolved_task_id = task_id or understanding_result.request_id
        else:
            understanding_result = understanding
            resolved_task_id = task_id or understanding_result.request_id

        description = f"Execution plan for: '{understanding_result.raw_request.raw_text}'"

        # Handle empty/invalid input
        if understanding_result.status == TaskUnderstandingStatus.INVALID or not understanding_result.intents:
            return ExecutableTaskPlan(
                task_id=resolved_task_id,
                description=description,
                status=PlanStatus.INVALID,
                steps=[],
                step_dependencies={},
                unresolved_items=understanding_result.unresolved_constraints or ["Invalid or empty task"],
            )

        # 1. Generate plan steps and dependency graph
        graph = ActionDependencyGraph()
        last_step_id: Optional[str] = None
        context_app: Optional[str] = None

        for intent in understanding_result.intents:
            if intent.constraints.application_name:
                context_app = intent.constraints.application_name

            intent_steps = self._rules.generate_steps_for_intent(
                intent=intent,
                preceding_step_id=last_step_id,
                context_app=context_app,
            )

            for step in intent_steps:
                graph.add_step(step)
                last_step_id = step.step_id

        # 2. Validate plan and dependencies
        plan = self._validator.validate_plan(
            task_id=resolved_task_id,
            description=description,
            graph=graph,
            understanding=understanding_result,
        )

        # 3. Attach deterministic explainability
        plan.explanation = self._explainer.explain_plan(plan)

        return plan

    plan = plan_task
