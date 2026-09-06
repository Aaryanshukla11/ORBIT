"""Deterministic compiler translating abstract PlanSteps into concrete Runtime Actions (M1.8 Step 3).

SAFETY INVARIANTS:
1. Pure compilation: NO direct OS input, NO pointer movements, NO keystrokes.
2. NO coordinate generation: Screen coordinates are NEVER fabricated. All spatial grounding
   is strictly delegated to runtime perception and target locator.
3. Fail-Closed on ambiguity, negation, or unsupported primitives.
"""

from __future__ import annotations

import logging
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
        app_name = step.constraints.application_name or intent.window_title or "Application"
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="pointer_move",
            target_intent=intent,
            action_parameters={},
            expected_outcome=ExpectedOutcome(
                outcome_type=ExpectedOutcomeType.WINDOW_FOCUSED,
                strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
                window_title=app_name,
            ),
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
        intent = self._build_target_intent_from_step(step, default_strategy=TargetStrategy.ACCESSIBILITY_ELEMENT)
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

    def _compile_unsupported_action(self, step: PlanStep) -> CompiledRuntimeAction:
        return CompiledRuntimeAction(
            step_id=step.step_id,
            action_type="unsupported",
            is_supported=False,
            rejection_reason=f"Step declared as UNSUPPORTED_ACTION: {step.description}",
            metadata={"step_action_type": step.action_type.value},
        )
