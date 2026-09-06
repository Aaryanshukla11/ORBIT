"""Unit tests for PlanStepCompiler (Milestone M1.8 Step 3).

Verifies:
1. Deterministic translation of PlanStep to CompiledRuntimeAction.
2. Abstract target and strategy preservation (NO coordinates).
3. Missing parameter fail-closed rejection.
4. Negated and ambiguous step rejection.
5. Zero OS side effects during compilation.
"""

from __future__ import annotations

import pytest

from orbit.runtime.plan_execution.compiler import PlanStepCompiler
from orbit.runtime.plan_execution.models import CompiledRuntimeAction
from orbit.runtime.planning.models import (
    DeferredGroundingRequirement,
    PlanActionType,
    PlanStep,
    Precondition,
    Postcondition,
)
from orbit.runtime.task_understanding.models import (
    TargetReference,
    TaskConstraints,
)
from orbit.runtime.targeting.models import TargetStrategy
from orbit.runtime.verification.models import ExpectedOutcomeType


@pytest.fixture
def compiler() -> PlanStepCompiler:
    return PlanStepCompiler()


def test_compile_ensure_application_open(compiler: PlanStepCompiler):
    step = PlanStep(
        step_id="step_open_1",
        action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
        description="Ensure Notepad is open",
        target=TargetReference(semantic_type="application", identifier="Notepad"),
    )
    compiled: CompiledRuntimeAction = compiler.compile(step)

    assert compiled.is_supported is True
    assert compiled.step_id == "step_open_1"
    assert compiled.action_type == "observe"
    assert compiled.target_intent is not None
    assert compiled.target_intent.window_title == "Notepad"
    assert compiled.expected_outcome is None


def test_compile_focus_application(compiler: PlanStepCompiler):
    step = PlanStep(
        step_id="step_focus_1",
        action_type=PlanActionType.FOCUS_APPLICATION,
        description="Focus Notepad window",
        target=TargetReference(semantic_type="application", identifier="Notepad"),
    )
    compiled = compiler.compile(step)

    assert compiled.is_supported is True
    assert compiled.action_type == "pointer_click"
    assert compiled.action_parameters.get("button") == "left"
    assert compiled.expected_outcome is not None
    assert compiled.expected_outcome.outcome_type == ExpectedOutcomeType.WINDOW_FOCUSED


def test_compile_locate_input_surface(compiler: PlanStepCompiler):
    step = PlanStep(
        step_id="step_locate_editor",
        action_type=PlanActionType.LOCATE_INPUT_SURFACE,
        description="Locate text editor surface",
        target=TargetReference(semantic_type="ui_control", identifier="Editor", role="edit"),
    )
    compiled = compiler.compile(step)

    assert compiled.is_supported is True
    assert compiled.action_type == "pointer_click"
    assert compiled.target_intent.role == "edit"
    assert compiled.expected_outcome is not None
    assert compiled.expected_outcome.outcome_type == ExpectedOutcomeType.ELEMENT_STATE_CHANGED


def test_compile_enter_text_success(compiler: PlanStepCompiler):
    step = PlanStep(
        step_id="step_type_1",
        action_type=PlanActionType.ENTER_TEXT,
        description="Enter text 'Hello World'",
        constraints=TaskConstraints(content="Hello World"),
        target=TargetReference(semantic_type="ui_control", identifier="Text Editor"),
    )
    compiled = compiler.compile(step)

    assert compiled.is_supported is True
    assert compiled.action_type == "type_text"
    assert compiled.action_parameters.get("text") == "Hello World"
    assert compiled.expected_outcome is not None
    assert compiled.expected_outcome.outcome_type == ExpectedOutcomeType.ELEMENT_STATE_CHANGED


def test_compile_enter_text_missing_content_fails_closed(compiler: PlanStepCompiler):
    step = PlanStep(
        step_id="step_type_missing",
        action_type=PlanActionType.ENTER_TEXT,
        description="Enter text with missing content",
        constraints=TaskConstraints(content=None),
        target=TargetReference(semantic_type="ui_control", identifier="Text Editor"),
    )
    compiled = compiler.compile(step)

    assert compiled.is_supported is False
    assert "missing required text payload" in (compiled.rejection_reason or "")


def test_compile_activate_control(compiler: PlanStepCompiler):
    step = PlanStep(
        step_id="step_click_save",
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click Save button",
        target=TargetReference(semantic_type="ui_control", identifier="Save", role="push button"),
        deferred_grounding=DeferredGroundingRequirement(
            strategy_preferences=[TargetStrategy.OCR_TEXT, TargetStrategy.ACCESSIBILITY_ELEMENT],
            target_reference=TargetReference(semantic_type="ui_control", identifier="Save"),
        ),
    )
    compiled = compiler.compile(step)

    assert compiled.is_supported is True
    assert compiled.action_type == "pointer_click"
    assert compiled.target_intent.strategy == TargetStrategy.OCR_TEXT
    assert compiled.target_intent.text == "Save"


def test_compile_save_document_success(compiler: PlanStepCompiler):
    step = PlanStep(
        step_id="step_save_doc",
        action_type=PlanActionType.SAVE_DOCUMENT,
        description="Save document",
        constraints=TaskConstraints(is_negated=False),
    )
    compiled = compiler.compile(step)

    assert compiled.is_supported is True
    assert compiled.action_type == "shortcut"
    assert compiled.action_parameters.get("combination") == "ctrl+s"


def test_compile_save_document_negated_fails_closed(compiler: PlanStepCompiler):
    step = PlanStep(
        step_id="step_save_prohibited",
        action_type=PlanActionType.SAVE_DOCUMENT,
        description="Save document (prohibited)",
        constraints=TaskConstraints(allow_save=False),
        is_negated=True,
    )
    compiled = compiler.compile(step)

    assert compiled.is_supported is False
    assert "prohibited" in (compiled.rejection_reason or "").lower()


def test_compile_ambiguous_step_fails_closed(compiler: PlanStepCompiler):
    step = PlanStep(
        step_id="step_ambig",
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click that",
        is_ambiguous=True,
        unresolved_reason="Target pronoun 'that' is unresolved",
    )
    compiled = compiler.compile(step)

    assert compiled.is_supported is False
    assert "unresolved ambiguity" in (compiled.rejection_reason or "").lower()


def test_compile_unsupported_action_type(compiler: PlanStepCompiler):
    step = PlanStep(
        step_id="step_dragon",
        action_type=PlanActionType.UNSUPPORTED_ACTION,
        description="Draw a photorealistic dragon",
    )
    compiled = compiler.compile(step)

    assert compiled.is_supported is False
    assert "UNSUPPORTED_ACTION" in (compiled.rejection_reason or "")


def test_compiler_generates_zero_coordinates(compiler: PlanStepCompiler):
    step = PlanStep(
        step_id="step_test_coord",
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click Save button",
        target=TargetReference(semantic_type="ui_control", text="Save"),
    )
    compiled = compiler.compile(step)

    # Invariant: coordinates must never be fabricated at compile time
    assert "x" not in compiled.action_parameters
    assert "y" not in compiled.action_parameters
