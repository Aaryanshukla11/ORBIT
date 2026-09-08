"""Core planning engine constructing validated, dependency-aware execution graphs from task understanding."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.runtime.planning.explainability import PlanExplainer
from orbit.runtime.planning.graph import ActionDependencyGraph
from orbit.runtime.planning.llm_synthesizer import LLMPlanSynthesizer
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
    Operates 100% locally and deterministically with optional Cognitive LLM Synthesis for complex workflows.
    """

    def __init__(
        self,
        rule_registry: Optional[PlanningRuleRegistry] = None,
        validator: Optional[PlanValidator] = None,
        explainer: Optional[PlanExplainer] = None,
        understanding_engine: Optional[TaskUnderstandingEngine] = None,
        llm_synthesizer: Optional[LLMPlanSynthesizer] = None,
    ):
        self._rules = rule_registry or PlanningRuleRegistry()
        self._validator = validator or PlanValidator()
        self._explainer = explainer or PlanExplainer()
        self._understanding_engine = understanding_engine or TaskUnderstandingEngine()
        self._synthesizer = llm_synthesizer or LLMPlanSynthesizer()

    def set_model_session_manager(self, msm: Any) -> None:
        """Bind active model session manager to underlying LLM plan synthesizer."""
        if self._synthesizer is not None:
            self._synthesizer.set_model_session_manager(msm)

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

    async def plan_task_async(
        self,
        understanding: Union[TaskUnderstandingResult, str],
        task_id: Optional[str] = None,
        snapshot: Optional[ObservationSnapshot] = None,
    ) -> ExecutableTaskPlan:
        """Asynchronously generate a plan, seamlessly falling back to LLM Plan Synthesis for complex/unsupported tasks."""
        if isinstance(understanding, str):
            if hasattr(self._understanding_engine, "understand_async"):
                understanding_result = await self._understanding_engine.understand_async(understanding, snapshot=snapshot)
            else:
                understanding_result = self._understanding_engine.understand(understanding)
            resolved_task_id = task_id or understanding_result.request_id
        else:
            understanding_result = understanding
            resolved_task_id = task_id or understanding_result.request_id

        # 1. Try deterministic planning first
        plan = self.plan_task(understanding_result, task_id=resolved_task_id)

        # If deterministic plan is valid and ready, return it
        if plan.is_valid and plan.status == PlanStatus.VALID and len(plan.steps) > 0:
            return plan

        # If task or plan is explicitly AMBIGUOUS, fail closed immediately
        if plan.status == PlanStatus.AMBIGUOUS or understanding_result.status == TaskUnderstandingStatus.AMBIGUOUS:
            return plan

        # 2. If deterministic planning failed or is unsupported, attempt LLM Plan Synthesis
        if self._synthesizer is not None:

            synthesized_steps = await self._synthesizer.synthesize_plan(
                understanding=understanding_result,
                task_id=resolved_task_id,
                snapshot=snapshot,
            )

            if synthesized_steps:
                graph = ActionDependencyGraph()
                for step in synthesized_steps:
                    graph.add_step(step)

                synth_plan = self._validator.validate_plan(
                    task_id=resolved_task_id,
                    description=f"AI-Synthesized plan for: '{understanding_result.raw_request.raw_text}'",
                    graph=graph,
                    understanding=understanding_result,
                )
                synth_plan.explanation = self._explainer.explain_plan(synth_plan)
                return synth_plan

        return plan

    plan = plan_task

