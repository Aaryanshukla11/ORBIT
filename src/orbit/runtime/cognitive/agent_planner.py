"""Agent Planner with Semantic Feasibility Ordering.

INVARIANT (ORBIT Dimension 3 & 5): AgentPlanner produces candidate plans, evaluates them
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
import re
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

        # 1. File Persistence / Save candidate (Priority when subgoal is save file intent with file target)
        save_match = re.search(r'(?:save|save\s+as|save\s+it\s+as|export\s+as|persist\s+as)\s+["\']?([^"\'\s,]+\.[a-zA-Z0-9]+)["\']?', f"{text} {objective.raw_prompt}", re.IGNORECASE)
        filename = objective.parameters.get("filename") or (save_match.group(1).strip() if save_match else None)
        is_save_subgoal = (
            (bool(filename) and any(w in subgoal.title.lower() for w in ("save", "export", "persist")))
            or any(w in subgoal.title.lower() for w in ("save as", "export as", "persist as"))
            or objective.parameters.get("action_type") == "save"
        ) and not any(w in text for w in ("button", "toolbar", "menu", "hotkey", "shortcut"))
        if is_save_subgoal and not any(w in subgoal.title.lower() for w in ("draw", "sketch")):
            target_fname = filename or "artifact"
            target_dir = objective.parameters.get("target_dir", "desktop" if "desktop" in text else "workspace")
            fmt = objective.parameters.get("format", target_fname.rsplit(".", 1)[-1] if "." in target_fname else "")
            candidates.append(
                CandidatePlan(
                    subgoal_id=subgoal.sub_id,
                    intent_strategy="GUI_INTERACTIVE",
                    proposed_primitives=[AbstractActionType.SAVE_FILE],
                    targets=[
                        SemanticTarget(
                            name=target_fname,
                            role="file",
                            context=target_dir,
                        )
                    ],
                    expected_outcome=ActionOutcomeContract(
                        expected_state_transition=f"File '{target_fname}' saved to {target_dir}",
                        verification_strategy=VerificationStrategy.ARTIFACT_CREATED,
                    ),
                    estimated_complexity=2,
                    creative_payload={
                        "filename": target_fname if filename else "",
                        "target_dir": target_dir,
                        "format": fmt,
                        "target_path": objective.parameters.get("target_path"),
                    },
                    rationale=f"Save artifact '{target_fname}' to {target_dir}",
                )
            )

        # 2. Canvas / Drawing candidate
        if not candidates and (
            any(w in text for w in ("draw", "sketch", "paint canvas", "strokes", "illustration"))
            or objective.parameters.get("action_type") == "draw"
            or bool(objective.parameters.get("strokes"))
        ):
            # Extract strokes from parameters or creative payload supplied by model reasoning
            strokes = objective.parameters.get("strokes") or []
            app_ctx = str(getattr(subgoal, 'target_entity', None) or objective.parameters.get("app_name") or "canvas")
            candidates.append(
                CandidatePlan(
                    subgoal_id=subgoal.sub_id,
                    intent_strategy="CANVAS_RENDERING",
                    proposed_primitives=[AbstractActionType.DRAW_STROKES],
                    targets=[
                        SemanticTarget(
                            name=app_ctx,
                            role="canvas",
                            context=app_ctx,
                        )
                    ],
                    expected_outcome=ActionOutcomeContract(
                        expected_state_transition="Drawing strokes rendered on canvas",
                        verification_strategy=VerificationStrategy.CANVAS_CHANGE,
                    ),
                    estimated_complexity=3,
                    creative_payload={
                        "strokes": strokes,
                        "raw_prompt": objective.raw_prompt,
                    },
                    rationale="Render vector strokes directly onto targeted canvas",
                )
            )

        # 3. Application launch candidate
        elif any(w in text for w in ("open", "launch", "start", "run", "bring up")) and not any(w in text for w in ("search box", "button", "link", "input", "menu", "tab", "file", "canvas", "draw", "portrait", "sketch")):
            from orbit.runtime.capabilities.application_launcher import APPROVED_APPLICATION_REGISTRY
            raw_entity = str(getattr(subgoal, 'target_entity', None) or objective.parameters.get("app_name") or "").strip().lower()
            app_name = None
            if raw_entity in APPROVED_APPLICATION_REGISTRY:
                app_name = raw_entity
            else:
                for app in APPROVED_APPLICATION_REGISTRY:
                    if app in text or app in raw_entity:
                        app_name = app
                        break
            if not app_name:
                m_app = re.search(r"\b(?:open|launch|start|run|bring\s+up)\s+(?:the\s+)?([a-zA-Z0-9_\-]+)", text)
                if m_app:
                    extracted_app = m_app.group(1).strip().lower()
                    if extracted_app not in ("the", "a", "an", "this", "search", "file", "tab", "dialog", "window", "app", "application"):
                        app_name = extracted_app
            app_name = app_name or raw_entity or "application"
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
                    creative_payload={"application_name": app_name, "app_name": app_name},
                    rationale=f"Launch and focus target application {app_name}",
                )
            )

        # 4. Text composition candidate
        elif any(w in text for w in ("type", "write", "enter text", "compose")):
            text_to_type = objective.parameters.get("text") or "Hello ORBIT"
            candidates.append(
                CandidatePlan(
                    subgoal_id=subgoal.sub_id,
                    intent_strategy="GUI_INTERACTIVE",
                    proposed_primitives=[AbstractActionType.TYPE_TEXT],
                    targets=[
                        SemanticTarget(
                            name=getattr(subgoal, 'target_entity', None) or "Active Document",
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

        # 5. Generic UI Click / Focus fallback candidate
        else:
            target_name = getattr(subgoal, 'target_entity', None) or "Main Window"
            proposed = list(getattr(subgoal, 'preferred_primitives', None) or [])
            if not proposed:
                if any(w in text for w in ("hotkey", "shortcut", "key", "ctrl", "alt")):
                    proposed = [AbstractActionType.CLICK, AbstractActionType.SEND_HOTKEY]
                else:
                    proposed = [AbstractActionType.CLICK]
            candidates.append(
                CandidatePlan(
                    subgoal_id=subgoal.sub_id,
                    intent_strategy="GUI_INTERACTIVE",
                    proposed_primitives=proposed,
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
                reasons = [f"Goal is NOT FEASIBLY EXECUTABLE: No viable strategy could achieve user goal (unsupported complex drawing shape '{shape or 'complex'}' exceeds vector stroke drawing capabilities; semantic coverage missing IMAGE_GENERATE_AND_INSERT capability)"]
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
            constraints=getattr(subgoal, "constraints", []),
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

    def replan(
        self,
        objective: StructuredObjective,
        subgoal: SubObjective,
        world_model: AgentWorldModel,
        failure_report: Any,
        failed_directive: Optional[PlanDirective] = None,
        observation: Optional[CurrentStateObservation] = None,
    ) -> Tuple[Optional[PlanDirective], SemanticFeasibilityReport]:
        """Formulate a NEW alternative PlanDirective following an observed failure or loop detection.

        Invariants:
        1. Sole Cognitive Authority: AgentPlanner alone decides the alternative strategy.
        2. Never silently reuses the failed PlanDirective.
        3. Generates candidates with distinct primitives/modalities (e.g. UIA -> physical click -> shortcut).
        """
        failed_primitives = list(failed_directive.preferred_primitives) if failed_directive else []
        failed_strategy = failed_directive.intent_strategy if failed_directive else ""
        category = getattr(failure_report, "category", None)
        cat_val = category.value if hasattr(category, "value") else str(category)

        candidates: List[CandidatePlan] = []
        target_name = (
            failed_directive.semantic_targets[0].name
            if failed_directive and failed_directive.semantic_targets
            else getattr(subgoal, "target_entity", "target") or "target"
        )

        # 1. Fallback for click unresponsiveness / stalled loop / repetitive click: Switch to Keyboard Shortcut or Physical pointer
        if AbstractActionType.CLICK in failed_primitives or any(k in cat_val for k in ("CLICK", "UNRESPONSIVE", "STALLED", "CYCLE", "REPETITIVE", "FAILED_ACTION")):
            # Candidate A: Keyboard Shortcut / Navigation
            hotkey = "enter"
            target_str = str(target_name).lower()
            if any(w in target_str for w in ("save", "file")):
                hotkey = "ctrl+s"
            elif any(w in target_str for w in ("close", "exit")):
                hotkey = "alt+f4"
            elif any(w in target_str for w in ("copy", "duplicate")):
                hotkey = "ctrl+c"
            elif any(w in target_str for w in ("paste", "insert")):
                hotkey = "ctrl+v"

            candidates.append(
                CandidatePlan(
                    subgoal_id=subgoal.sub_id,
                    intent_strategy="KEYBOARD_SHORTCUT",
                    proposed_primitives=[AbstractActionType.SEND_HOTKEY],
                    targets=[SemanticTarget(name=target_name, role="shortcut", text_hint=hotkey)],
                    expected_outcome=ActionOutcomeContract(
                        expected_state_transition=f"Executed hotkey fallback '{hotkey}' for {target_name}",
                        verification_strategy=VerificationStrategy.AUTO_ROUTED,
                    ),
                    estimated_complexity=2,
                    creative_payload={"hotkey": hotkey, "fallback_mode": "KEYBOARD_SHORTCUT"},
                    rationale=f"Fallback from failed click to keyboard shortcut '{hotkey}'",
                )
            )

            # Candidate B: Physical coordinate click with settle pause
            candidates.append(
                CandidatePlan(
                    subgoal_id=subgoal.sub_id,
                    intent_strategy="PHYSICAL_POINTER_ACTUATION",
                    proposed_primitives=[AbstractActionType.CLICK],
                    targets=[SemanticTarget(name=target_name, role="physical_control", context="grounded_screen")],
                    expected_outcome=ActionOutcomeContract(
                        expected_state_transition=f"Physical click dispatched on {target_name}",
                        verification_strategy=VerificationStrategy.AUTO_ROUTED,
                    ),
                    estimated_complexity=2,
                    creative_payload={"interaction_modality": "PHYSICAL_POINTER", "fallback_mode": "PHYSICAL_CLICK"},
                    rationale=f"Fallback from UIA to physical pointer click on '{target_name}'",
                )
            )

        # 2. Fallback for Dead Window / Lost Focus / Process Crash
        elif any(k in cat_val for k in ("DEAD_WINDOW", "WINDOW_NOT_FOCUSED", "APPLICATION_CRASHED")):
            candidates.append(
                CandidatePlan(
                    subgoal_id=subgoal.sub_id,
                    intent_strategy="WINDOW_MANAGEMENT",
                    proposed_primitives=[AbstractActionType.FOCUS_WINDOW, AbstractActionType.CLICK],
                    targets=[SemanticTarget(name=target_name, role="window")],
                    expected_outcome=ActionOutcomeContract(
                        expected_state_transition=f"Re-focused window '{target_name}'",
                        verification_strategy=VerificationStrategy.WINDOW_FOCUS,
                    ),
                    estimated_complexity=2,
                    creative_payload={"fallback_mode": "REFOCUS_WINDOW"},
                    rationale=f"Refocus active window before interacting with '{target_name}'",
                )
            )

        # 3. Fallback for Text Entry Mismatch
        elif "TEXT" in cat_val:
            text_to_type = objective.parameters.get("text") or "Hello ORBIT"
            candidates.append(
                CandidatePlan(
                    subgoal_id=subgoal.sub_id,
                    intent_strategy="CLIPBOARD_INJECTION",
                    proposed_primitives=[AbstractActionType.FOCUS_WINDOW, AbstractActionType.TYPE_TEXT],
                    targets=[SemanticTarget(name=target_name, role="edit", context="foreground_window")],
                    expected_outcome=ActionOutcomeContract(
                        expected_state_transition="Text injected via focused edit control",
                        verification_strategy=VerificationStrategy.OCR_TEXT,
                    ),
                    estimated_complexity=2,
                    creative_payload={"text": text_to_type, "clear_before_type": True, "fallback_mode": "FOCUS_AND_TYPE"},
                    rationale="Focus and clear edit control before typing text",
                )
            )

        # 4. Generic fallback if no specific rule matched
        if not candidates:
            std_candidates = self.generate_candidate_plans(objective, subgoal, world_model, observation)
            for cand in std_candidates:
                if cand.proposed_primitives != failed_primitives or cand.intent_strategy != failed_strategy:
                    candidates.append(cand)
            if not candidates:
                candidates.append(
                    CandidatePlan(
                        subgoal_id=subgoal.sub_id,
                        intent_strategy="ALTERNATIVE_KEYBOARD_PATHWAY",
                        proposed_primitives=[AbstractActionType.SEND_HOTKEY],
                        targets=[SemanticTarget(name=target_name, role="control")],
                        expected_outcome=ActionOutcomeContract(
                            expected_state_transition="Dispatched alternative navigation key",
                            verification_strategy=VerificationStrategy.AUTO_ROUTED,
                        ),
                        estimated_complexity=2,
                        creative_payload={"hotkey": "enter", "fallback_mode": "ALTERNATIVE_NAVIGATION"},
                        rationale="Dispatched alternative navigation key after failed prior directive",
                    )
                )

        # Evaluate candidate plans through SemanticFeasibilityEvaluator
        best_candidate, report = self._feasibility.select_feasible_plan(
            candidates=candidates,
            world_model=world_model,
        )

        if not best_candidate or not report.is_feasible:
            logger.warning("Replanning for subgoal '%s' produced no feasible candidates", subgoal.sub_id)
            return None, report

        # Construct NEW PlanDirective
        new_directive = PlanDirective(
            directive_id=f"dir_replan_{uuid4().hex[:8]}",
            objective_id=objective.objective_id,
            subgoal_id=subgoal.sub_id,
            subgoal_title=subgoal.title,
            intent_strategy=best_candidate.intent_strategy,
            candidate_plan_id=best_candidate.candidate_id,
            semantic_targets=best_candidate.targets,
            constraints=getattr(subgoal, "constraints", []),
            preferred_primitives=best_candidate.proposed_primitives,
            expected_outcome=best_candidate.expected_outcome,
            feasibility_score=report.best_score,
            creative_payload=best_candidate.creative_payload,
        )

        logger.info(
            "[AgentPlanner.replan] Emitted NEW PlanDirective '%s' (strategy: %s, primitives: %s) for subgoal '%s'",
            new_directive.directive_id,
            new_directive.intent_strategy,
            [p.value for p in new_directive.preferred_primitives],
            subgoal.sub_id,
        )
        return new_directive, report


__all__ = [
    "AgentPlanner",
]
