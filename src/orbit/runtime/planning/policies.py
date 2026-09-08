"""Deterministic planning rules transforming structured intents into dependency-aware plan steps."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from orbit.runtime.planning.models import (
    DeferredGroundingRequirement,
    PlanActionType,
    PlanStep,
    Postcondition,
    Precondition,
)
from orbit.runtime.task_understanding.models import (
    StructuredTaskIntent,
    TargetReference,
    TaskConstraints,
    TaskGoal,
)
from orbit.runtime.targeting.models import TargetStrategy


class PlanningRuleRegistry:
    """Transforms ordered StructuredTaskIntent sequences into high-level PlanStep nodes with dependencies."""

    def generate_steps_for_intent(
        self,
        intent: StructuredTaskIntent,
        preceding_step_id: Optional[str] = None,
        context_app: Optional[str] = None,
    ) -> List[PlanStep]:
        """Apply the appropriate planning rule for the given intent."""
        if intent.goal == TaskGoal.OPEN_APPLICATION:
            return self._plan_open_application(intent, preceding_step_id)
        elif intent.goal == TaskGoal.WRITE_TEXT:
            return self._plan_write_text(intent, preceding_step_id, context_app)
        elif intent.goal == TaskGoal.CLICK_TARGET:
            return self._plan_click_target(intent, preceding_step_id, context_app)
        elif intent.goal == TaskGoal.CALCULATE:
            return self._plan_calculate(intent, preceding_step_id, context_app)
        elif intent.goal == TaskGoal.SAVE_DOCUMENT:
            return self._plan_save_document(intent, preceding_step_id, context_app)
        elif intent.goal == TaskGoal.CLOSE_APPLICATION:
            return self._plan_close_application(intent, preceding_step_id, context_app)
        elif intent.goal == TaskGoal.COPY_CONTENT:
            return self._plan_copy_content(intent, preceding_step_id)
        elif intent.goal == TaskGoal.PASTE_CONTENT:
            return self._plan_paste_content(intent, preceding_step_id, context_app)
        elif intent.goal == TaskGoal.SEARCH:
            return self._plan_search(intent, preceding_step_id, context_app)
        elif intent.goal in (TaskGoal.DRAW, TaskGoal.CREATE_DOCUMENT, TaskGoal.INTERACT):
            return self._plan_draw(intent, preceding_step_id, context_app)
        else:
            return self._plan_unsupported(intent, preceding_step_id)

    # --- Rule Implementations ---

    def _plan_open_application(
        self,
        intent: StructuredTaskIntent,
        preceding_step_id: Optional[str],
    ) -> List[PlanStep]:
        app_name = intent.target.identifier if intent.target else (intent.constraints.application_name or "Application")
        is_ambig = intent.is_ambiguous or (intent.target is not None and intent.target.is_ambiguous)

        # Step 1: Ensure Application Open
        step_1_id = f"step_{uuid4().hex[:6]}"
        step_1 = PlanStep(
            step_id=step_1_id,
            action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
            description=f"Ensure application '{app_name}' is open and ready",
            target=intent.target,
            constraints=intent.constraints,
            preconditions=[
                Precondition(
                    condition_type="application_known",
                    target=app_name,
                    description=f"Application identity '{app_name}' is specified",
                )
            ],
            postconditions=[
                Postcondition(
                    condition_type="application_running",
                    target=app_name,
                    description=f"Application '{app_name}' is active with a top-level window",
                )
            ],
            dependencies=[preceding_step_id] if preceding_step_id else [],
            deferred_grounding=DeferredGroundingRequirement(
                strategy_preferences=[
                    TargetStrategy.WINDOW_TITLE,
                    TargetStrategy.ACCESSIBILITY_ELEMENT,
                ],
                target_reference=intent.target or TargetReference(semantic_type="application", identifier=app_name),
                grounding_notes=f"Locate or launch top-level window for '{app_name}'",
            ) if not is_ambig else None,
            evidence=[
                f"source_goal: {intent.goal.value}",
                f"planning_rule: OPEN_APPLICATION_RULE",
                f"application_target: '{app_name}'",
            ],
            is_negated=intent.is_negated,
            is_ambiguous=is_ambig,
            unresolved_reason=intent.unresolved_reason,
        )

        # Step 2: Verify Application Available
        step_2_id = f"step_{uuid4().hex[:6]}"
        step_2 = PlanStep(
            step_id=step_2_id,
            action_type=PlanActionType.VERIFY_APPLICATION_AVAILABLE,
            description=f"Verify application '{app_name}' is responsive and interactive",
            target=intent.target,
            constraints=intent.constraints,
            preconditions=[
                Precondition(
                    condition_type="application_running",
                    target=app_name,
                    description=f"Application '{app_name}' must be running",
                )
            ],
            postconditions=[
                Postcondition(
                    condition_type="application_responsive",
                    target=app_name,
                    description=f"Application '{app_name}' window state verified interactive",
                )
            ],
            dependencies=[step_1_id],
            evidence=[
                f"source_goal: {intent.goal.value}",
                f"planning_rule: VERIFY_APPLICATION_AVAILABLE_RULE",
            ],
            is_negated=intent.is_negated,
            is_ambiguous=is_ambig,
            unresolved_reason=intent.unresolved_reason,
        )

        return [step_1, step_2]

    def _plan_write_text(
        self,
        intent: StructuredTaskIntent,
        preceding_step_id: Optional[str],
        context_app: Optional[str],
    ) -> List[PlanStep]:
        app_name = intent.constraints.application_name or context_app or "Active Application"
        content = intent.constraints.content or ""
        is_ambig = intent.is_ambiguous

        # If negated, we do not produce active writing actions
        if intent.is_negated:
            neg_step = PlanStep(
                step_id=f"step_{uuid4().hex[:6]}",
                action_type=PlanActionType.ENTER_TEXT,
                description=f"PROHIBITED: User requested NOT to type text into '{app_name}'",
                target=intent.target,
                constraints=intent.constraints,
                dependencies=[preceding_step_id] if preceding_step_id else [],
                evidence=[
                    f"source_goal: {intent.goal.value}",
                    f"planning_rule: PROHIBITED_WRITE_TEXT_RULE",
                    f"negation_details: {intent.constraints.negation_details}",
                ],
                is_negated=True,
                is_ambiguous=False,
            )
            return [neg_step]

        steps: List[PlanStep] = []
        last_id = preceding_step_id

        # Step 1: Focus application if known
        if preceding_step_id:
            step_focus_id = f"step_{uuid4().hex[:6]}"
            step_focus = PlanStep(
                step_id=step_focus_id,
                action_type=PlanActionType.FOCUS_APPLICATION,
                description=f"Bring '{app_name}' to foreground focus",
                target=TargetReference(semantic_type="application", identifier=app_name),
                constraints=intent.constraints,
                preconditions=[
                    Precondition(condition_type="window_exists", target=app_name, description=f"Window for '{app_name}' exists")
                ],
                postconditions=[
                    Postcondition(condition_type="window_focused", target=app_name, description=f"Window for '{app_name}' is foreground")
                ],
                dependencies=[last_id] if last_id else [],
                evidence=[f"source_goal: {intent.goal.value}", "planning_rule: FOCUS_APPLICATION_RULE"],
                is_ambiguous=is_ambig,
            )
            steps.append(step_focus)
            last_id = step_focus_id

        # Step 2: Locate Input Surface
        step_locate_id = f"step_{uuid4().hex[:6]}"
        step_locate = PlanStep(
            step_id=step_locate_id,
            action_type=PlanActionType.LOCATE_INPUT_SURFACE,
            description=f"Locate text input surface inside '{app_name}'",
            target=TargetReference(semantic_type="ui_control", role="edit", identifier="document_body"),
            constraints=intent.constraints,
            preconditions=[
                Precondition(condition_type="window_focused", target=app_name, description="Target window is focused")
            ],
            postconditions=[
                Postcondition(condition_type="input_surface_located", description="Input surface resolved with safe click target")
            ],
            dependencies=[last_id] if last_id else [],
            deferred_grounding=DeferredGroundingRequirement(
                strategy_preferences=[
                    TargetStrategy.ACCESSIBILITY_ELEMENT,
                    TargetStrategy.OCR_TEXT,
                    TargetStrategy.VISUAL_TEMPLATE,
                ],
                target_reference=TargetReference(semantic_type="ui_control", role="edit", identifier="document_body"),
                grounding_notes="Resolve editable document surface via UIA or screen OCR",
            ),
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: LOCATE_INPUT_SURFACE_RULE"],
            is_ambiguous=is_ambig,
        )
        steps.append(step_locate)
        last_id = step_locate_id

        # Step 3: Enter Text
        step_enter_id = f"step_{uuid4().hex[:6]}"
        step_enter = PlanStep(
            step_id=step_enter_id,
            action_type=PlanActionType.ENTER_TEXT,
            description=f"Enter verbatim content: '{content}'",
            target=intent.target,
            constraints=intent.constraints,
            preconditions=[
                Precondition(condition_type="input_surface_focused", description="Input surface is ready for keyboard input")
            ],
            postconditions=[
                Postcondition(
                    condition_type="text_entered",
                    description=f"Text buffer updated with '{content}'",
                    expected_state={"verbatim_content": content},
                )
            ],
            dependencies=[last_id],
            evidence=[
                f"source_goal: {intent.goal.value}",
                f"planning_rule: ENTER_TEXT_RULE",
                f"verbatim_payload_length: {len(content)} chars",
            ],
            is_ambiguous=is_ambig,
            unresolved_reason=intent.unresolved_reason,
        )
        steps.append(step_enter)
        last_id = step_enter_id

        # Step 4: Verify Text Entry
        step_verify_id = f"step_{uuid4().hex[:6]}"
        step_verify = PlanStep(
            step_id=step_verify_id,
            action_type=PlanActionType.VERIFY_TEXT_ENTRY,
            description=f"Verify rendered text entry matches '{content}'",
            target=intent.target,
            constraints=intent.constraints,
            preconditions=[
                Precondition(condition_type="text_dispatched", description="Keyboard input dispatched")
            ],
            postconditions=[
                Postcondition(
                    condition_type="text_rendered_verified",
                    description="Verified text rendered on target surface",
                    expected_state={"verbatim_content": content},
                )
            ],
            dependencies=[last_id],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: VERIFY_TEXT_ENTRY_RULE"],
            is_ambiguous=is_ambig,
        )
        steps.append(step_verify)

        return steps

    def _plan_click_target(
        self,
        intent: StructuredTaskIntent,
        preceding_step_id: Optional[str],
        context_app: Optional[str],
    ) -> List[PlanStep]:
        label = intent.target.identifier if intent.target else "Target"
        is_ambig = intent.is_ambiguous or (intent.target is not None and intent.target.is_ambiguous)

        # Step 1: Locate Target
        step_1_id = f"step_{uuid4().hex[:6]}"
        step_1 = PlanStep(
            step_id=step_1_id,
            action_type=PlanActionType.LOCATE_TARGET,
            description=f"Locate UI control '{label}' on screen",
            target=intent.target,
            constraints=intent.constraints,
            preconditions=[
                Precondition(condition_type="screen_observed", description="Fresh observation frame captured")
            ],
            postconditions=[
                Postcondition(condition_type="target_resolved", description=f"Safe action point for '{label}' computed")
            ],
            dependencies=[preceding_step_id] if preceding_step_id else [],
            deferred_grounding=DeferredGroundingRequirement(
                strategy_preferences=[
                    TargetStrategy.ACCESSIBILITY_ELEMENT,
                    TargetStrategy.OCR_TEXT,
                    TargetStrategy.VISUAL_TEMPLATE,
                ],
                target_reference=intent.target or TargetReference(semantic_type="ui_control", identifier=label),
                grounding_notes=f"Perceptually locate '{label}' using multimodal evidence",
            ) if not is_ambig else None,
            evidence=[f"source_goal: {intent.goal.value}", f"planning_rule: LOCATE_TARGET_RULE", f"target_label: '{label}'"],
            is_negated=intent.is_negated,
            is_ambiguous=is_ambig,
            unresolved_reason=intent.unresolved_reason,
        )

        # Step 2: Activate Control
        step_2_id = f"step_{uuid4().hex[:6]}"
        step_2 = PlanStep(
            step_id=step_2_id,
            action_type=PlanActionType.ACTIVATE_CONTROL,
            description=f"Click / activate UI control '{label}'",
            target=intent.target,
            constraints=intent.constraints,
            preconditions=[
                Precondition(condition_type="target_resolved", description=f"Target '{label}' resolved with verified coordinates")
            ],
            postconditions=[
                Postcondition(condition_type="control_invoked", description=f"Click event dispatched to '{label}'")
            ],
            dependencies=[step_1_id],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: ACTIVATE_CONTROL_RULE"],
            is_negated=intent.is_negated,
            is_ambiguous=is_ambig,
            unresolved_reason=intent.unresolved_reason,
        )

        # Step 3: Verify Target Effect
        step_3_id = f"step_{uuid4().hex[:6]}"
        step_3 = PlanStep(
            step_id=step_3_id,
            action_type=PlanActionType.VERIFY_TARGET_EFFECT,
            description=f"Verify outcome of activating '{label}'",
            target=intent.target,
            constraints=intent.constraints,
            dependencies=[step_2_id],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: VERIFY_TARGET_EFFECT_RULE"],
            is_negated=intent.is_negated,
            is_ambiguous=is_ambig,
        )

        return [step_1, step_2, step_3]

    def _plan_save_document(
        self,
        intent: StructuredTaskIntent,
        preceding_step_id: Optional[str],
        context_app: Optional[str],
    ) -> List[PlanStep]:
        # Handle negation explicitly
        if intent.is_negated:
            neg_step = PlanStep(
                step_id=f"step_{uuid4().hex[:6]}",
                action_type=PlanActionType.SAVE_DOCUMENT,
                description="PROHIBITED: User requested NOT to save the document",
                target=intent.target,
                constraints=intent.constraints,
                dependencies=[preceding_step_id] if preceding_step_id else [],
                evidence=[
                    f"source_goal: {intent.goal.value}",
                    "planning_rule: PROHIBITED_SAVE_RULE",
                    f"negation_details: {intent.constraints.negation_details}",
                ],
                is_negated=True,
                is_ambiguous=False,
            )
            return [neg_step]

        is_ambig = intent.is_ambiguous

        # Step 1: Locate Save Control
        step_1_id = f"step_{uuid4().hex[:6]}"
        step_1 = PlanStep(
            step_id=step_1_id,
            action_type=PlanActionType.LOCATE_TARGET,
            description="Locate 'Save' command or button",
            target=TargetReference(semantic_type="ui_control", identifier="Save", role="button"),
            constraints=intent.constraints,
            dependencies=[preceding_step_id] if preceding_step_id else [],
            deferred_grounding=DeferredGroundingRequirement(
                strategy_preferences=[
                    TargetStrategy.ACCESSIBILITY_ELEMENT,
                    TargetStrategy.OCR_TEXT,
                    TargetStrategy.VISUAL_TEMPLATE,
                ],
                target_reference=TargetReference(semantic_type="ui_control", identifier="Save", role="button"),
                grounding_notes="Locate Save button or File -> Save menu item",
            ) if not is_ambig else None,
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: LOCATE_SAVE_CONTROL_RULE"],
            is_ambiguous=is_ambig,
            unresolved_reason=intent.unresolved_reason,
        )

        # Step 2: Save Document Action
        step_2_id = f"step_{uuid4().hex[:6]}"
        step_2 = PlanStep(
            step_id=step_2_id,
            action_type=PlanActionType.SAVE_DOCUMENT,
            description="Execute save document operation",
            target=intent.target,
            constraints=intent.constraints,
            preconditions=[
                Precondition(condition_type="save_control_located", description="Save control located")
            ],
            postconditions=[
                Postcondition(condition_type="save_invoked", description="Save command dispatched")
            ],
            dependencies=[step_1_id],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: SAVE_DOCUMENT_RULE"],
            is_ambiguous=is_ambig,
        )

        # Step 3: Verify Document Saved
        step_3_id = f"step_{uuid4().hex[:6]}"
        step_3 = PlanStep(
            step_id=step_3_id,
            action_type=PlanActionType.VERIFY_DOCUMENT_SAVED,
            description="Verify document persistence state",
            target=intent.target,
            constraints=intent.constraints,
            dependencies=[step_2_id],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: VERIFY_DOCUMENT_SAVED_RULE"],
            is_ambiguous=is_ambig,
        )

        return [step_1, step_2, step_3]

    def _plan_close_application(
        self,
        intent: StructuredTaskIntent,
        preceding_step_id: Optional[str],
        context_app: Optional[str],
    ) -> List[PlanStep]:
        app_name = intent.target.identifier if intent.target else (context_app or "Application")
        is_ambig = intent.is_ambiguous

        step_1_id = f"step_{uuid4().hex[:6]}"
        step_1 = PlanStep(
            step_id=step_1_id,
            action_type=PlanActionType.CLOSE_APPLICATION,
            description=f"Close application '{app_name}'",
            target=intent.target,
            constraints=intent.constraints,
            dependencies=[preceding_step_id] if preceding_step_id else [],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: CLOSE_APPLICATION_RULE"],
            is_ambiguous=is_ambig,
            unresolved_reason=intent.unresolved_reason,
        )

        step_2_id = f"step_{uuid4().hex[:6]}"
        step_2 = PlanStep(
            step_id=step_2_id,
            action_type=PlanActionType.VERIFY_APPLICATION_AVAILABLE,
            description=f"Verify application '{app_name}' window has closed",
            target=intent.target,
            constraints=intent.constraints,
            dependencies=[step_1_id],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: VERIFY_APPLICATION_CLOSED_RULE"],
            is_ambiguous=is_ambig,
        )

        return [step_1, step_2]

    def _plan_copy_content(
        self,
        intent: StructuredTaskIntent,
        preceding_step_id: Optional[str],
    ) -> List[PlanStep]:
        step_1_id = f"step_{uuid4().hex[:6]}"
        step_1 = PlanStep(
            step_id=step_1_id,
            action_type=PlanActionType.VALIDATE_SELECTION_CONTEXT,
            description="Validate active text selection context",
            target=intent.target,
            constraints=intent.constraints,
            dependencies=[preceding_step_id] if preceding_step_id else [],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: VALIDATE_SELECTION_RULE"],
        )

        step_2_id = f"step_{uuid4().hex[:6]}"
        step_2 = PlanStep(
            step_id=step_2_id,
            action_type=PlanActionType.COPY_CONTENT,
            description="Copy selected content to clipboard",
            target=intent.target,
            constraints=intent.constraints,
            dependencies=[step_1_id],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: COPY_CONTENT_RULE"],
        )

        step_3_id = f"step_{uuid4().hex[:6]}"
        step_3 = PlanStep(
            step_id=step_3_id,
            action_type=PlanActionType.VERIFY_CLIPBOARD_STATE,
            description="Verify clipboard contains copied payload",
            target=intent.target,
            constraints=intent.constraints,
            dependencies=[step_2_id],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: VERIFY_CLIPBOARD_RULE"],
        )

        return [step_1, step_2, step_3]

    def _plan_paste_content(
        self,
        intent: StructuredTaskIntent,
        preceding_step_id: Optional[str],
        context_app: Optional[str],
    ) -> List[PlanStep]:
        step_1_id = f"step_{uuid4().hex[:6]}"
        step_1 = PlanStep(
            step_id=step_1_id,
            action_type=PlanActionType.LOCATE_INPUT_SURFACE,
            description="Locate destination input surface for paste",
            target=intent.target,
            constraints=intent.constraints,
            dependencies=[preceding_step_id] if preceding_step_id else [],
            deferred_grounding=DeferredGroundingRequirement(
                strategy_preferences=[TargetStrategy.ACCESSIBILITY_ELEMENT, TargetStrategy.OCR_TEXT],
                target_reference=intent.target or TargetReference(semantic_type="ui_control", role="edit"),
                grounding_notes="Locate focused text insertion caret",
            ),
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: LOCATE_PASTE_SURFACE_RULE"],
        )

        step_2_id = f"step_{uuid4().hex[:6]}"
        step_2 = PlanStep(
            step_id=step_2_id,
            action_type=PlanActionType.PASTE_CONTENT,
            description="Paste clipboard content into active surface",
            target=intent.target,
            constraints=intent.constraints,
            dependencies=[step_1_id],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: PASTE_CONTENT_RULE"],
        )

        step_3_id = f"step_{uuid4().hex[:6]}"
        step_3 = PlanStep(
            step_id=step_3_id,
            action_type=PlanActionType.VERIFY_TEXT_ENTRY,
            description="Verify pasted content appears on input surface",
            target=intent.target,
            constraints=intent.constraints,
            dependencies=[step_2_id],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: VERIFY_PASTE_RULE"],
        )

        return [step_1, step_2, step_3]

    def _plan_search(
        self,
        intent: StructuredTaskIntent,
        preceding_step_id: Optional[str],
        context_app: Optional[str],
    ) -> List[PlanStep]:
        query = intent.constraints.content or intent.constraints.custom_parameters.get("query", "")
        is_ambig = intent.is_ambiguous

        step_1_id = f"step_{uuid4().hex[:6]}"
        step_1 = PlanStep(
            step_id=step_1_id,
            action_type=PlanActionType.LOCATE_TARGET,
            description="Locate search box or input control",
            target=TargetReference(semantic_type="search_box", identifier="search_input", role="edit"),
            constraints=intent.constraints,
            dependencies=[preceding_step_id] if preceding_step_id else [],
            deferred_grounding=DeferredGroundingRequirement(
                strategy_preferences=[TargetStrategy.ACCESSIBILITY_ELEMENT, TargetStrategy.OCR_TEXT],
                target_reference=TargetReference(semantic_type="search_box", identifier="search_input", role="edit"),
                grounding_notes="Locate search input field on active view",
            ) if not is_ambig else None,
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: LOCATE_SEARCH_BOX_RULE"],
            is_ambiguous=is_ambig,
            unresolved_reason=intent.unresolved_reason,
        )

        step_2_id = f"step_{uuid4().hex[:6]}"
        step_2 = PlanStep(
            step_id=step_2_id,
            action_type=PlanActionType.ENTER_TEXT,
            description=f"Enter search query: '{query}'",
            target=intent.target,
            constraints=intent.constraints,
            dependencies=[step_1_id],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: ENTER_SEARCH_QUERY_RULE"],
            is_ambiguous=is_ambig,
        )

        step_3_id = f"step_{uuid4().hex[:6]}"
        step_3 = PlanStep(
            step_id=step_3_id,
            action_type=PlanActionType.ACTIVATE_CONTROL,
            description="Submit search query",
            target=TargetReference(semantic_type="ui_control", identifier="submit", role="button"),
            constraints=intent.constraints,
            dependencies=[step_2_id],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: SUBMIT_SEARCH_RULE"],
            is_ambiguous=is_ambig,
        )

        step_4_id = f"step_{uuid4().hex[:6]}"
        step_4 = PlanStep(
            step_id=step_4_id,
            action_type=PlanActionType.VERIFY_TARGET_EFFECT,
            description="Verify search results view loaded",
            target=intent.target,
            constraints=intent.constraints,
            dependencies=[step_3_id],
            evidence=[f"source_goal: {intent.goal.value}", "planning_rule: VERIFY_SEARCH_RESULTS_RULE"],
            is_ambiguous=is_ambig,
        )

        return [step_1, step_2, step_3, step_4]

    def _plan_calculate(
        self,
        intent: StructuredTaskIntent,
        preceding_step_id: Optional[str],
        context_app: Optional[str],
    ) -> List[PlanStep]:
        app_name = intent.constraints.application_name or context_app or "Calculator"
        tokens: List[str] = intent.constraints.custom_parameters.get("tokens", [])
        expected_result = intent.constraints.custom_parameters.get("expected_result", "")
        expression = intent.constraints.content or ""
        is_ambig = intent.is_ambiguous

        steps: List[PlanStep] = []
        last_id = preceding_step_id

        # Step 1: Focus Calculator window if preceding step exists
        if preceding_step_id:
            step_focus_id = f"step_{uuid4().hex[:6]}"
            step_focus = PlanStep(
                step_id=step_focus_id,
                action_type=PlanActionType.FOCUS_APPLICATION,
                description=f"Bring '{app_name}' to foreground focus",
                target=TargetReference(semantic_type="application", identifier=app_name),
                constraints=intent.constraints,
                preconditions=[
                    Precondition(condition_type="window_exists", target=app_name, description=f"Window for '{app_name}' exists")
                ],
                postconditions=[
                    Postcondition(condition_type="window_focused", target=app_name, description=f"Window for '{app_name}' is foreground")
                ],
                dependencies=[last_id] if last_id else [],
                evidence=[f"source_goal: {intent.goal.value}", "planning_rule: FOCUS_APPLICATION_RULE"],
                is_ambiguous=is_ambig,
            )
            steps.append(step_focus)
            last_id = step_focus_id

        # Step 2..N: Click each calculation token
        for token in tokens:
            step_click_id = f"step_{uuid4().hex[:6]}"
            step_click = PlanStep(
                step_id=step_click_id,
                action_type=PlanActionType.ACTIVATE_CONTROL,
                description=f"Click Calculator button '{token}'",
                target=TargetReference(semantic_type="ui_control", identifier=token, role="button"),
                constraints=intent.constraints,
                dependencies=[last_id] if last_id else [],
                deferred_grounding=DeferredGroundingRequirement(
                    strategy_preferences=[
                        TargetStrategy.ACCESSIBILITY_ELEMENT,
                        TargetStrategy.OCR_TEXT,
                        TargetStrategy.VISUAL_TEMPLATE,
                    ],
                    target_reference=TargetReference(semantic_type="ui_control", identifier=token, role="button"),
                    grounding_notes=f"Locate and activate Calculator button '{token}'",
                ) if not is_ambig else None,
                evidence=[
                    f"source_goal: {intent.goal.value}",
                    f"planning_rule: CALCULATE_CLICK_RULE",
                    f"button_token: '{token}'",
                ],
                is_ambiguous=is_ambig,
                unresolved_reason=intent.unresolved_reason,
            )
            steps.append(step_click)
            last_id = step_click_id

        # Final Step: Verify calculation result
        step_verify_id = f"step_{uuid4().hex[:6]}"
        step_verify = PlanStep(
            step_id=step_verify_id,
            action_type=PlanActionType.VERIFY_TARGET_EFFECT,
            description=f"Verify calculation '{expression}' result matches '{expected_result}'",
            target=TargetReference(semantic_type="ui_control", identifier="CalculatorResults", role="text"),
            constraints=intent.constraints,
            dependencies=[last_id] if last_id else [],
            evidence=[
                f"source_goal: {intent.goal.value}",
                "planning_rule: VERIFY_CALCULATION_RESULT_RULE",
                f"expected_result: '{expected_result}'",
            ],
            is_ambiguous=is_ambig,
        )
        steps.append(step_verify)

        return steps

    def _plan_draw(
        self,
        intent: StructuredTaskIntent,
        preceding_step_id: Optional[str],
        context_app: Optional[str] = None,
    ) -> List[PlanStep]:
        app_name = (
            (intent.constraints.application_name if intent.constraints else None)
            or context_app
            or "Paint"
        )
        subject = (
            (intent.constraints.content if intent.constraints else None)
            or "canvas drawing"
        )
        is_ambig = intent.is_ambiguous

        steps: List[PlanStep] = []

        # Step 1: Ensure Paint/Canvas App Open
        step_1_id = f"step_{uuid4().hex[:6]}"
        step_1 = PlanStep(
            step_id=step_1_id,
            action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
            description=f"Ensure application '{app_name}' is open and ready for drawing",
            target=TargetReference(semantic_type="application", identifier=app_name),
            constraints=intent.constraints,
            preconditions=[
                Precondition(
                    condition_type="application_known",
                    target=app_name,
                    description=f"Drawing target application '{app_name}' is identified",
                )
            ],
            postconditions=[
                Postcondition(
                    condition_type="application_running",
                    target=app_name,
                    description=f"Application '{app_name}' is active and foregrounded",
                )
            ],
            dependencies=[preceding_step_id] if preceding_step_id else [],
            deferred_grounding=DeferredGroundingRequirement(
                strategy_preferences=[TargetStrategy.WINDOW_TITLE, TargetStrategy.ACCESSIBILITY_ELEMENT],
                target_reference=TargetReference(semantic_type="application", identifier=app_name),
                grounding_notes=f"Locate or launch application '{app_name}'",
            ),
            evidence=[
                f"source_goal: {intent.goal.value}",
                "planning_rule: DRAW_CANVAS_RULE",
                f"application_target: '{app_name}'",
            ],
            is_ambiguous=is_ambig,
        )
        steps.append(step_1)

        # Step 2: Focus Canvas
        step_2_id = f"step_{uuid4().hex[:6]}"
        step_2 = PlanStep(
            step_id=step_2_id,
            action_type=PlanActionType.LOCATE_INPUT_SURFACE,
            description=f"Focus drawing canvas in '{app_name}'",
            target=TargetReference(semantic_type="canvas", identifier=app_name, role="drawing_canvas"),
            constraints=intent.constraints,
            preconditions=[
                Precondition(
                    condition_type="application_running",
                    target=app_name,
                    description=f"Application '{app_name}' is running",
                )
            ],
            postconditions=[
                Postcondition(
                    condition_type="canvas_focused",
                    target="canvas",
                    description=f"Canvas in '{app_name}' is active and ready for drawing strokes",
                )
            ],
            dependencies=[step_1_id],
            deferred_grounding=DeferredGroundingRequirement(
                strategy_preferences=[TargetStrategy.ACCESSIBILITY_ELEMENT, TargetStrategy.WINDOW_TITLE],
                target_reference=TargetReference(semantic_type="canvas", identifier=app_name),
                grounding_notes=f"Focus drawing viewport in '{app_name}'",
            ),
            evidence=[
                f"source_goal: {intent.goal.value}",
                "planning_rule: FOCUS_CANVAS_RULE",
                f"drawing_subject: '{subject}'",
            ],
            is_ambiguous=is_ambig,
        )
        steps.append(step_2)

        # Step 3: Draw Canvas Strokes
        step_3_id = f"step_{uuid4().hex[:6]}"
        step_3 = PlanStep(
            step_id=step_3_id,
            action_type=PlanActionType.ACTIVATE_CONTROL,
            description=f"Execute drawing strokes for '{subject}' on canvas",
            target=TargetReference(semantic_type="canvas", identifier=app_name),
            constraints=intent.constraints,
            preconditions=[
                Precondition(
                    condition_type="canvas_focused",
                    target="canvas",
                    description="Drawing canvas is ready",
                )
            ],
            postconditions=[
                Postcondition(
                    condition_type="canvas_modified",
                    target="canvas",
                    description=f"Drawing strokes for '{subject}' rendered on canvas",
                )
            ],
            dependencies=[step_2_id],
            deferred_grounding=DeferredGroundingRequirement(
                strategy_preferences=[TargetStrategy.ACCESSIBILITY_ELEMENT, TargetStrategy.WINDOW_TITLE],
                target_reference=TargetReference(semantic_type="canvas", identifier=app_name),
                grounding_notes=f"Perform drawing interaction for '{subject}'",
            ),
            evidence=[
                f"source_goal: {intent.goal.value}",
                "planning_rule: EXECUTE_DRAW_STROKES_RULE",
                f"subject: '{subject}'",
            ],
            is_ambiguous=is_ambig,
        )
        steps.append(step_3)

        return steps

    def _plan_unsupported(
        self,
        intent: StructuredTaskIntent,
        preceding_step_id: Optional[str],
    ) -> List[PlanStep]:
        step = PlanStep(
            step_id=f"step_{uuid4().hex[:6]}",
            action_type=PlanActionType.UNSUPPORTED_ACTION,
            description=f"UNSUPPORTED: Cannot plan action for goal '{intent.goal.value}'",
            target=intent.target,
            constraints=intent.constraints,
            dependencies=[preceding_step_id] if preceding_step_id else [],
            evidence=[
                f"source_goal: {intent.goal.value}",
                "planning_rule: UNSUPPORTED_GOAL_RULE",
            ],
            is_ambiguous=True,
            unresolved_reason=f"Goal '{intent.goal.value}' is not supported by current planning rules",
        )
        return [step]
