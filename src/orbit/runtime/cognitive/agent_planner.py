"""Agent Planner with Semantic Feasibility Ordering.

INVARIANT (ASTRA Dimension 3 & 5): AgentPlanner produces candidate plans, evaluates them
via SemanticFeasibilityEvaluator, and emits an authoritative PlanDirective ONLY if a candidate
is semantically feasible.

Ordering:
  Preflight (RuntimeFeasibility)
    ↓
  AgentPlanner (Candidate Generation)
    ↓
  SemanticFeasibility (Evaluation & Scoring)
    ↓
  Select Best Plan
    ↓
  PlanDirective Emission
    ↓
  PrimitiveComposer
    ↓
  PrimitiveValidator
    ↓
  PrimitiveExecutionController
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from orbit.runtime.agent.contracts import (
    AbstractActionType,
    ActionOutcomeContract,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.cognitive.models import (
    CurrentStateObservation,
    StructuredObjective,
    SubObjective,
)
from orbit.runtime.cognitive.plan_directive import PlanDirective
from orbit.runtime.cognitive.semantic_feasibility import (
    CandidatePlan,
    SemanticFeasibilityEvaluator,
    SemanticFeasibilityReport,
)
from orbit.runtime.world_model.model import AgentWorldModel

logger = logging.getLogger(__name__)


class AgentPlanner:
    """Produces candidate plans for sub-objectives, enforces semantic feasibility ordering, and emits PlanDirectives."""

    def __init__(
        self,
        feasibility_evaluator: Optional[SemanticFeasibilityEvaluator] = None,
        model_client: Optional[Any] = None,
    ) -> None:
        self._feasibility = feasibility_evaluator or SemanticFeasibilityEvaluator()
        self._model_client = model_client

    def generate_candidate_plans(
        self,
        objective: StructuredObjective,
        subgoal: SubObjective,
        world_model: AgentWorldModel,
        observation: Optional[CurrentStateObservation] = None,
    ) -> List[CandidatePlan]:
        """Synthesize candidate execution strategies for the active subgoal."""
        candidates: List[CandidatePlan] = []
        text = f"{subgoal.title} {subgoal.description}".lower()

        # 1. Canvas / Drawing candidate
        shape = str(objective.parameters.get("shape", "")).lower()
        if (
            any(w in text for w in ("draw", "sketch", "paint canvas", "strokes", "illustration", "cube", "square", "rectangle", "circle", "shape"))
            or objective.parameters.get("action_type") == "draw"
            or bool(shape)
        ):
            # Extract strokes from parameters or creative payload
            strokes = objective.parameters.get("strokes") or [
                [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8), (0.2, 0.2)]
            ]
            candidates.append(
                CandidatePlan(
                    subgoal_id=subgoal.sub_id,
                    intent_strategy="CANVAS_RENDERING",
                    proposed_primitives=[AbstractActionType.DRAW_STROKES],
                    targets=[
                        SemanticTarget(
                            name=subgoal.target_entity or "Paint",
                            role="canvas",
                            context="mspaint",
                        )
                    ],
                    expected_outcome=ActionOutcomeContract(
                        expected_state_transition="Drawing strokes rendered on canvas",
                        verification_strategy=VerificationStrategy.CANVAS_CHANGE,
                    ),
                    estimated_complexity=3,
                    creative_payload={
                        "strokes": strokes,
                        "shape": shape,
                        "raw_prompt": objective.raw_prompt,
                    },
                    rationale="Render vector strokes directly onto targeted canvas",
                )
            )

        # 2. Application launch candidate
        elif any(w in text for w in ("open", "launch", "start")) and any(
            app in text for app in ("notepad", "paint", "calculator", "calc", "word", "excel", "browser")
        ):
            app_name = subgoal.target_entity or "notepad"
            candidates.append(
                CandidatePlan(
                    subgoal_id=subgoal.sub_id,
                    intent_strategy="GUI_INTERACTIVE",
                    proposed_primitives=[AbstractActionType.LAUNCH_APPLICATION],
                    targets=[SemanticTarget(name=app_name, role="window")],
                    expected_outcome=ActionOutcomeContract(
                        expected_state_transition=f"{app_name} application window opened and focused",
                        verification_strategy=VerificationStrategy.WINDOW_FOCUS,
                    ),
                    estimated_complexity=1,
                    rationale=f"Launch and focus target application {app_name}",
                )
            )

        # 3. Text composition candidate
        elif any(w in text for w in ("type", "write", "enter text", "compose")):
            text_to_type = objective.parameters.get("text") or "Hello ORBIT"
            candidates.append(
                CandidatePlan(
                    subgoal_id=subgoal.sub_id,
                    intent_strategy="GUI_INTERACTIVE",
                    proposed_primitives=[AbstractActionType.TYPE_TEXT],
                    targets=[
                        SemanticTarget(
                            name=subgoal.target_entity or "Active Document",
                            role="edit",
                            context="foreground_window",
                        )
                    ],
                    expected_outcome=ActionOutcomeContract(
                        expected_state_transition="Text entered into document edit control",
                        verification_strategy=VerificationStrategy.OCR_TEXT,
                    ),
                    estimated_complexity=2,
                    creative_payload={"text": text_to_type},
                    rationale="Enter textual deliverable into foreground edit control",
                )
            )

        # 4. Generic UI Click / Focus fallback candidate
        else:
            target_name = subgoal.target_entity or "Main Window"
            candidates.append(
                CandidatePlan(
                    subgoal_id=subgoal.sub_id,
                    intent_strategy="GUI_INTERACTIVE",
                    proposed_primitives=subgoal.preferred_primitives or [AbstractActionType.CLICK],
                    targets=[SemanticTarget(name=target_name, role="control")],
                    expected_outcome=ActionOutcomeContract(
                        expected_state_transition=f"Interacted with {target_name}",
                        verification_strategy=VerificationStrategy.AUTO_ROUTED,
                    ),
                    estimated_complexity=2,
                    rationale=f"Interact with control '{target_name}'",
                )
            )

        return candidates

    def plan_subgoal(
        self,
        objective: StructuredObjective,
        subgoal: SubObjective,
        world_model: AgentWorldModel,
        observation: Optional[CurrentStateObservation] = None,
    ) -> Tuple[Optional[PlanDirective], SemanticFeasibilityReport]:
        """Formulate a PlanDirective for the active subgoal strictly enforcing Semantic Feasibility ordering."""
        # 1. Generate candidate plans
        candidates = self.generate_candidate_plans(
            objective=objective,
            subgoal=subgoal,
            world_model=world_model,
            observation=observation,
        )

        # 2. Evaluate candidate plans through SemanticFeasibilityEvaluator
        best_candidate, report = self._feasibility.select_feasible_plan(
            candidates=candidates,
            world_model=world_model,
        )

        if not best_candidate or not report.is_feasible:
            reasons = list(report.rejection_reasons)
            if not reasons or reasons == ["No candidate plans provided by planner"]:
                shape = str(objective.parameters.get("shape", "")).lower()
                reasons = [f"Goal is NOT FEASIBLY EXECUTABLE (unsupported complex drawing shape '{shape or 'complex'}' or missing primitives)"]
                report = report.model_copy(update={"rejection_reasons": reasons})
            logger.warning(
                "Subgoal '%s' has no semantically feasible plan candidates: %s",
                subgoal.sub_id,
                report.rejection_reasons,
            )
            return None, report

        # 3. Formulate authoritative PlanDirective
        directive = PlanDirective(
            objective_id=objective.objective_id,
            subgoal_id=subgoal.sub_id,
            subgoal_title=subgoal.title,
            intent_strategy=best_candidate.intent_strategy,
            candidate_plan_id=best_candidate.candidate_id,
            semantic_targets=best_candidate.targets,
            constraints=subgoal.constraints,
            preferred_primitives=best_candidate.proposed_primitives,
            expected_outcome=best_candidate.expected_outcome,
            feasibility_score=report.best_score,
            creative_payload=best_candidate.creative_payload,
        )

        logger.info(
            "Emitted PlanDirective '%s' for subgoal '%s' with feasibility score %.2f",
            directive.directive_id,
            subgoal.sub_id,
            directive.feasibility_score,
        )
        return directive, report


__all__ = [
    "AgentPlanner",
]
