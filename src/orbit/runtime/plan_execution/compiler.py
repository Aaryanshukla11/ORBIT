"""Deterministic compiler translating abstract PlanSteps into concrete Runtime Actions (M1.8 Step 3).

SAFETY INVARIANTS:
1. Pure compilation: NO direct OS input, NO pointer movements, NO keystrokes.
2. NO coordinate generation: Screen coordinates are NEVER fabricated. All spatial grounding
   is strictly delegated to runtime perception and target locator.
3. Fail-Closed on ambiguity, negation, or unsupported primitives.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from orbit.runtime.plan_execution.models import CompiledRuntimeAction
from orbit.runtime.planning.models import PlanActionType, PlanStep
from orbit.runtime.targeting.models import TargetIntent, TargetStrategy
from orbit.runtime.verification.models import (
    ExpectedOutcome,
    ExpectedOutcomeType,
    VerificationStrategy,
)

logger = logging.getLogger(__name__)


class PlanStepCompiler:
    """Deterministic compiler translating high-level PlanStep models to executable runtime intents."""

    def compile(self, step: PlanStep) -> CompiledRuntimeAction:
        """Compile an abstract PlanStep into a validated CompiledRuntimeAction."""
        # 1. Check for explicit negative constraints or prohibition
        if step.is_negated:
            return CompiledRuntimeAction(
                step_id=step.step_id,
                action_type="unsupported",
                is_supported=False,
                rejection_reason=f"Step '{step.action_type.value}' is explicitly prohibited by user constraints",
                metadata={"step_action_type": step.action_type.value, "is_negated": True},
            )

        # 2. Check for unresolved ambiguity
        if step.is_ambiguous:
            return CompiledRuntimeAction(
                step_id=step.step_id,
                action_type="unsupported",
                is_supported=False,
                rejection_reason=f"Step '{step.action_type.value}' contains unresolved ambiguity: {step.unresolved_reason or 'ambiguous target/binding'}",
                metadata={"step_action_type": step.action_type.value, "is_ambiguous": True},
            )

        # 3. Dispatch to type-specific compiler method
        compiler_method = getattr(self, f"_compile_{step.action_type.value.lower()}", None)
        if compiler_method is None:
            return CompiledRuntimeAction(
                step_id=step.step_id,
                action_type="unsupported",
                is_supported=False,
                rejection_reason=f"Unsupported plan action type '{step.action_type.value}'",
                metadata={"step_action_type": step.action_type.value},
            )

        try:
            return compiler_method(step)
        except Exception as ex:
            logger.exception("Unexpected compilation error for step %s: %s", step.step_id, ex)
            return CompiledRuntimeAction(
                step_id=step.step_id,
                action_type="unsupported",
                is_supported=False,
                rejection_reason=f"Internal compilation error: {str(ex)}",
                metadata={"step_action_type": step.action_type.value, "error": str(ex)},
            )

    def _build_target_intent_from_step(
        self,
        step: PlanStep,
        default_strategy: TargetStrategy = TargetStrategy.ACCESSIBILITY_ELEMENT,
    ) -> TargetIntent:
        """Extract TargetIntent from DeferredGroundingRequirement or TargetReference."""
        strategy = default_strategy
        name: Optional[str] = None
        text: Optional[str] = None
        window_title: Optional[str] = None
        role: Optional[str] = None
        target_ref: Optional[Any] = None

        if step.deferred_grounding:
            dg = step.deferred_grounding
            if dg.strategy_preferences:
                strategy = dg.strategy_preferences[0]
            target_ref = dg.target_reference
            target_str = getattr(target_ref, "identifier", None) or getattr(target_ref, "target_name", None) or getattr(target_ref, "text", None)
            name = target_str
            text = target_str
            role = target_ref.role
            window_title = target_str if target_ref.semantic_type == "application" else None
        elif step.target:
            target_ref = step.target
            target_str = getattr(target_ref, "identifier", None) or getattr(target_ref, "target_name", None) or getattr(target_ref, "text", None)
            name = target_str
            text = target_str
            role = target_ref.role
            window_title = target_str if target_ref.semantic_type == "application" else None

        # Handle generic semantic identifiers by clearing literal name match
        generic_tokens = {
            "document_body", "main_document", "editor_canvas", "input_surface",
            "editor_surface", "search_input", "search_box", "submit", "submit_button",
            "search_button",
        }
        if name and name.lower() in generic_tokens:
            if not role:
                if any(k in name.lower() for k in ("search", "input", "editor", "document")):
                    role = "edit"
                elif any(k in name.lower() for k in ("submit", "button")):
                    role = "button"
            name = None
            text = None

        if not window_title and step.constraints.application_name:
            window_title = step.constraints.application_name

        if target_ref and getattr(target_ref, "semantic_type", "") in ("ui_control", "button", "input_surface", "element") and strategy == TargetStrategy.WINDOW_TITLE:
            strategy = TargetStrategy.ACCESSIBILITY_ELEMENT

        # Build strategy-tailored TargetIntent
        return TargetIntent(
            strategy=strategy,
            name=name,
            text=text,
            role=role,
            window_title=window_title,
            metadata={"source_step_id": step.step_id, "action_type": step.action_type.value},
        )

    def _compile_ensure_application_open(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.WINDOW_TITLE)
        app_name = intent.name or intent.window_title or "Application"
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="observe",
            target_intent=intent,
            expected_outcome=None,
            is_supported=True,
            metadata={"application_name": app_name},
        )

    def _compile_focus_application(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.WINDOW_TITLE)
        app_name = intent.name or intent.window_title or "Application"
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="pointer_click",
            target_intent=intent,
            action_parameters={"button": "left", "count": 1},
            expected_outcome=ExpectedOutcome(
                outcome_type=ExpectedOutcomeType.WINDOW_FOCUSED,
                strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
                window_title=app_name,
                target_name=app_name,
            ),
            is_supported=True,
            metadata={"focus_target": app_name},
        )

    def _compile_locate_target(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.ACCESSIBILITY_ELEMENT)
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="pointer_move",
            target_intent=intent,
            action_parameters={},
            expected_outcome=None,
            is_supported=True,
            metadata={"target_name": intent.name or intent.text},
        )

    def _compile_locate_input_surface(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.ACCESSIBILITY_ELEMENT)
        if not intent.role:
            intent.role = "edit"
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="pointer_click",
            target_intent=intent,
            action_parameters={"button": "left", "count": 1},
            expected_outcome=ExpectedOutcome(
                outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
                strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
                target_role=intent.role or "edit",
            ),
            is_supported=True,
            metadata={"input_surface_role": intent.role},
        )

    def _compile_enter_text(self, step: PlanStep) -> CompiledRuntimeAction:
        # Extract text payload from constraints or metadata
        text = step.constraints.content
        if text is None and "text" in step.metadata:
            text = str(step.metadata["text"])

        if text is None:
            return CompiledRuntimeAction(
                step_id=step.step_id,
                action_type="unsupported",
                is_supported=False,
                rejection_reason="ENTER_TEXT action rejected: missing required text payload in constraints or metadata",
                metadata={"step_action_type": step.action_type.value},
            )

        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.ACCESSIBILITY_ELEMENT)
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="type_text",
            target_intent=intent,
            action_parameters={"text": text},
            expected_outcome=ExpectedOutcome(
                outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
                strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
                target_role=intent.role or "edit",
            ),
            is_supported=True,
            metadata={"typed_text_length": len(text)},
        )

    def _compile_activate_control(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.ACCESSIBILITY_ELEMENT)
        button = step.metadata.get("button", "left")
        count = step.metadata.get("count", 1)
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="pointer_click",
            target_intent=intent,
            action_parameters={"button": button, "count": count},
            expected_outcome=None,
            is_supported=True,
            metadata={"button": button, "count": count},
        )

    def _compile_draw_strokes(self, step: PlanStep) -> CompiledRuntimeAction:
        """Compile abstract drawing step into structured geometric stroke series."""
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.ACCESSIBILITY_ELEMENT)
        if not intent.role:
            intent.role = "canvas"

        subject = (step.metadata.get("subject") or (step.description or "")).lower()

        strokes: List[List[Tuple[int, int]]] = []

        if "cube" in subject or "box" in subject or "3d" in subject:
            # 3D isometric/perspective cube
            strokes = [
                # Front square
                [(-60, -40), (40, -40), (40, 60), (-60, 60), (-60, -40)],
                # Back square
                [(-20, -80), (80, -80), (80, 20), (-20, 20), (-20, -80)],
                # 4 Connecting edges
                [(-60, -40), (-20, -80)],
                [(40, -40), (80, -80)],
                [(40, 60), (80, 20)],
                [(-60, 60), (-20, 20)],
            ]
        elif "stickman" in subject or "person" in subject or "figure" in subject:
            # Stickman with head, body, arms, legs
            head_pts = [
                (int(30 * math.cos(math.radians(deg))), int(30 * math.sin(math.radians(deg))) - 60)
                for deg in range(0, 361, 30)
            ]
            strokes = [
                head_pts,
                [(0, -30), (0, 45)],  # Body
                [(0, 45), (-40, 110)],  # Left leg
                [(0, 45), (40, 110)],  # Right leg
                [(-45, 5), (0, -5), (45, 5)],  # Arms
            ]
            if "gun" in subject or "weapon" in subject:
                # Gun in right hand
                strokes.append([(45, 5), (75, 5), (75, 18), (68, 18), (68, 9)])
        elif "circle" in subject or "ellipse" in subject:
            circle_pts = [
                (int(60 * math.cos(math.radians(deg))), int(60 * math.sin(math.radians(deg))))
                for deg in range(0, 361, 20)
            ]
            strokes = [circle_pts]
        elif "triangle" in subject:
            strokes = [[(0, -65), (65, 45), (-65, 45), (0, -65)]]
        elif "star" in subject:
            star_pts = []
            for i in range(11):
                r = 60 if i % 2 == 0 else 25
                ang = -math.pi / 2 + i * math.pi / 5
                star_pts.append((int(r * math.cos(ang)), int(r * math.sin(ang))))
            strokes = [star_pts]
        elif "house" in subject:
            strokes = [
                [(-60, -10), (60, -10), (60, 70), (-60, 70), (-60, -10)],  # Walls
                [(-70, -10), (0, -75), (70, -10)],  # Roof
                [(-18, 70), (-18, 30), (18, 30), (18, 70)],  # Door
            ]
        elif "square" in subject or "rectangle" in subject:
            strokes = [[(-60, -50), (60, -50), (60, 50), (-60, 50), (-60, -50)]]
        else:
            # Default rich recognizable figure (geometric diamond-framed figure)
            strokes = [
                [(-50, -50), (50, -50), (50, 50), (-50, 50), (-50, -50)],
                [(-50, 0), (0, -50), (50, 0), (0, 50), (-50, 0)],
            ]

        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="draw_strokes",
            target_intent=intent,
            action_parameters={
                "subject": subject,
                "strokes": strokes,
            },
            expected_outcome=ExpectedOutcome(
                outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
                strategy=VerificationStrategy.OBSERVATION_STATE_DELTA,
                target_role="canvas",
            ),
            is_supported=True,
            metadata={"subject": subject, "stroke_count": len(strokes)},
        )

    def _compile_save_document(self, step: PlanStep) -> CompiledRuntimeAction:
        # Check explicit negative save constraint
        allow_save = getattr(step.constraints, "allow_save", None)
        if allow_save is False or step.constraints.is_negated or step.is_negated:
            return CompiledRuntimeAction(
                step_id=step.step_id,
                action_type="unsupported",
                is_supported=False,
                rejection_reason="SAVE_DOCUMENT action rejected: saving is explicitly prohibited by task constraints",
                metadata={"is_negated": True},
            )

        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.WINDOW_TITLE)
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="shortcut",
            target_intent=intent,
            action_parameters={"combination": "ctrl+s"},
            expected_outcome=ExpectedOutcome(
                outcome_type=ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE,
                strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
            ),
            is_supported=True,
            metadata={"shortcut": "ctrl+s"},
        )

    def _compile_copy_content(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.WINDOW_TITLE)
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="shortcut",
            target_intent=intent,
            action_parameters={"combination": "ctrl+c"},
            expected_outcome=ExpectedOutcome(
                outcome_type=ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE,
                strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
            ),
            is_supported=True,
            metadata={"shortcut": "ctrl+c"},
        )

    def _compile_paste_content(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.WINDOW_TITLE)
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="shortcut",
            target_intent=intent,
            action_parameters={"combination": "ctrl+v"},
            expected_outcome=ExpectedOutcome(
                outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
                strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
            ),
            is_supported=True,
            metadata={"shortcut": "ctrl+v"},
        )

    def _compile_close_application(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.WINDOW_TITLE)
        app_name = intent.name or intent.window_title or "Application"
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="shortcut",
            target_intent=intent,
            action_parameters={"combination": "alt+f4"},
            expected_outcome=ExpectedOutcome(
                outcome_type=ExpectedOutcomeType.WINDOW_CLOSED,
                strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
                window_title=app_name,
            ),
            is_supported=True,
            metadata={"shortcut": "alt+f4"},
        )

    def _compile_validate_selection_context(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.ACCESSIBILITY_ELEMENT)
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="observe",
            target_intent=intent,
            expected_outcome=ExpectedOutcome(
                outcome_type=ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE,
                strategy=VerificationStrategy.OBSERVATION_STATE_DELTA,
            ),
            is_supported=True,
            metadata={"purpose": "validate_selection"},
        )

    def _compile_verify_application_available(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.WINDOW_TITLE)
        app_name = intent.name or intent.window_title or "Application"
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="observe",
            target_intent=intent,
            expected_outcome=None,
            is_supported=True,
            metadata={"verified_target": app_name},
        )

    def _compile_verify_text_entry(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.ACCESSIBILITY_ELEMENT)
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="observe",
            target_intent=intent,
            expected_outcome=None,
            is_supported=True,
            metadata={"purpose": "verify_text_entry"},
        )

    def _compile_verify_target_effect(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.WINDOW_TITLE)
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="observe",
            target_intent=intent,
            expected_outcome=None,
            is_supported=True,
            metadata={"purpose": "verify_target_effect"},
        )

    def _compile_verify_document_saved(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.WINDOW_TITLE)
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="observe",
            target_intent=intent,
            expected_outcome=None,
            is_supported=True,
            metadata={"purpose": "verify_document_saved"},
        )

    def _compile_verify_clipboard_state(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.ACCESSIBILITY_ELEMENT)
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="observe",
            target_intent=intent,
            expected_outcome=None,
            is_supported=True,
            metadata={"purpose": "verify_clipboard_state"},
        )

    def _compile_search_query(self, step: PlanStep) -> CompiledRuntimeAction:
        query = step.constraints.content or step.metadata.get("query", "")
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.ACCESSIBILITY_ELEMENT)
        if not intent.role:
            intent.role = "edit"
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="type_text",
            target_intent=intent,
            action_parameters={"text": query},
            expected_outcome=ExpectedOutcome(
                outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
                strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
                target_role=intent.role or "edit",
            ),
            is_supported=True,
            metadata={"search_query": query},
        )

    def _compile_select_option(self, step: PlanStep) -> CompiledRuntimeAction:
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.ACCESSIBILITY_ELEMENT)
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="pointer_click",
            target_intent=intent,
            action_parameters={"button": "left", "count": 1},
            expected_outcome=ExpectedOutcome(
                outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
                strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
            ),
            is_supported=True,
            metadata={"option_name": intent.name or intent.text},
        )

    def _compile_navigate_view(self, step: PlanStep) -> CompiledRuntimeAction:
        direction = step.metadata.get("direction", "down")
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.WINDOW_TITLE)
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="shortcut",
            target_intent=intent,
            action_parameters={"combination": "pgdn" if direction == "down" else "pgup"},
            expected_outcome=ExpectedOutcome(
                outcome_type=ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE,
                strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
            ),
            is_supported=True,
            metadata={"navigation_direction": direction},
        )

    def _compile_unsupported_action(self, step: PlanStep) -> CompiledRuntimeAction:
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="unsupported",
            is_supported=False,
            rejection_reason=f"Step declared as UNSUPPORTED_ACTION: {step.description}",
            metadata={"step_action_type": step.action_type.value},
        )

