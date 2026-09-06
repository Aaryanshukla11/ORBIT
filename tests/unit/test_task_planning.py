"""Unit test suite for ORBIT Task Planning Subsystem (M1.8 Step 2)."""

import pytest
from orbit.runtime.planning import (
    ActionDependencyGraph,
    ExecutableTaskPlan,
    PlanActionType,
    PlanExplainer,
    PlanStatus,
    PlanStep,
    TaskPlanningEngine,
)
from orbit.runtime.task_understanding import (
    RawTaskRequest,
    StructuredTaskIntent,
    TargetReference,
    TaskConstraints,
    TaskGoal,
    TaskUnderstandingEngine,
    TaskUnderstandingResult,
    TaskUnderstandingStatus,
)


@pytest.fixture
def planner():
    return TaskPlanningEngine()


@pytest.fixture
def understanding_engine():
    return TaskUnderstandingEngine()


# ============================================================================
# 1. Basic Single-Goal Plan Generation Tests
# ============================================================================

def test_plan_open_notepad(planner, understanding_engine):
    """Test planning 'Open Notepad'."""
    understanding = understanding_engine.understand("Open Notepad")
    plan = planner.plan_task(understanding)

    assert plan.status == PlanStatus.VALID
    assert len(plan.steps) == 2

    # Step 0: ENSURE_APPLICATION_OPEN
    s0 = plan.steps[0]
    assert s0.action_type == PlanActionType.ENSURE_APPLICATION_OPEN
    assert s0.target.identifier == "Notepad"
    assert len(s0.dependencies) == 0

    # Step 1: VERIFY_APPLICATION_AVAILABLE depends on Step 0
    s1 = plan.steps[1]
    assert s1.action_type == PlanActionType.VERIFY_APPLICATION_AVAILABLE
    assert s0.step_id in s1.dependencies


def test_plan_open_calculator(planner, understanding_engine):
    """Test planning 'Launch Calculator'."""
    understanding = understanding_engine.understand("Launch Calculator")
    plan = planner.plan_task(understanding)

    assert plan.status == PlanStatus.VALID
    assert plan.steps[0].action_type == PlanActionType.ENSURE_APPLICATION_OPEN
    assert plan.steps[0].target.identifier == "Calculator"


def test_plan_click_save(planner, understanding_engine):
    """Test planning 'Click Save'."""
    understanding = understanding_engine.understand("Click Save")
    plan = planner.plan_task(understanding)

    assert plan.status == PlanStatus.VALID
    assert len(plan.steps) == 3

    # Step 0: LOCATE_TARGET
    assert plan.steps[0].action_type == PlanActionType.LOCATE_TARGET
    assert plan.steps[0].target.identifier == "Save"
    assert plan.steps[0].deferred_grounding is not None

    # Step 1: ACTIVATE_CONTROL
    assert plan.steps[1].action_type == PlanActionType.ACTIVATE_CONTROL
    assert plan.steps[0].step_id in plan.steps[1].dependencies

    # Step 2: VERIFY_TARGET_EFFECT
    assert plan.steps[2].action_type == PlanActionType.VERIFY_TARGET_EFFECT
    assert plan.steps[1].step_id in plan.steps[2].dependencies


def test_plan_save_document(planner, understanding_engine):
    """Test planning 'Save document'."""
    understanding = understanding_engine.understand("Save document")
    plan = planner.plan_task(understanding)

    assert plan.status == PlanStatus.VALID
    assert len(plan.steps) == 3
    assert plan.steps[0].action_type == PlanActionType.LOCATE_TARGET
    assert plan.steps[1].action_type == PlanActionType.SAVE_DOCUMENT
    assert plan.steps[2].action_type == PlanActionType.VERIFY_DOCUMENT_SAVED


def test_plan_search(planner, understanding_engine):
    """Test planning 'Search for weather'."""
    understanding = understanding_engine.understand("Search for weather")
    plan = planner.plan_task(understanding)

    assert plan.status == PlanStatus.VALID
    assert len(plan.steps) == 4
    assert plan.steps[0].action_type == PlanActionType.LOCATE_TARGET
    assert plan.steps[1].action_type == PlanActionType.ENTER_TEXT
    assert plan.steps[1].constraints.content == "weather"
    assert plan.steps[2].action_type == PlanActionType.ACTIVATE_CONTROL
    assert plan.steps[3].action_type == PlanActionType.VERIFY_TARGET_EFFECT


def test_plan_copy_content(planner, understanding_engine):
    """Test planning 'Copy the selected text'."""
    understanding = understanding_engine.understand("Copy the selected text")
    plan = planner.plan_task(understanding)

    assert plan.status == PlanStatus.VALID
    assert len(plan.steps) == 3
    assert plan.steps[0].action_type == PlanActionType.VALIDATE_SELECTION_CONTEXT
    assert plan.steps[1].action_type == PlanActionType.COPY_CONTENT
    assert plan.steps[2].action_type == PlanActionType.VERIFY_CLIPBOARD_STATE


# ============================================================================
# 2. Composite Multi-Step Plan Decomposition
# ============================================================================

def test_composite_open_notepad_and_type_hello_world(planner, understanding_engine):
    """Test composite plan 'Open Notepad and type Hello World'."""
    understanding = understanding_engine.understand("Open Notepad and type Hello World")
    plan = planner.plan_task(understanding)

    assert plan.status == PlanStatus.VALID
    assert len(plan.steps) == 6

    # Step sequence:
    # 0: ENSURE_APPLICATION_OPEN
    # 1: VERIFY_APPLICATION_AVAILABLE
    # 2: FOCUS_APPLICATION
    # 3: LOCATE_INPUT_SURFACE
    # 4: ENTER_TEXT
    # 5: VERIFY_TEXT_ENTRY
    types = [s.action_type for s in plan.steps]
    assert types == [
        PlanActionType.ENSURE_APPLICATION_OPEN,
        PlanActionType.VERIFY_APPLICATION_AVAILABLE,
        PlanActionType.FOCUS_APPLICATION,
        PlanActionType.LOCATE_INPUT_SURFACE,
        PlanActionType.ENTER_TEXT,
        PlanActionType.VERIFY_TEXT_ENTRY,
    ]

    # Verify linear dependency chain
    for i in range(1, len(plan.steps)):
        pred_id = plan.steps[i - 1].step_id
        curr_deps = plan.steps[i].dependencies
        assert pred_id in curr_deps, f"Step {i} must depend on Step {i - 1}"

    # Verify verbatim content preserved
    enter_step = plan.steps[4]
    assert enter_step.constraints.content == "Hello World"
    assert enter_step.constraints.application_name == "Notepad"


def test_composite_open_type_and_save(planner, understanding_engine):
    """Test three-stage composite plan: open -> type -> save."""
    understanding = understanding_engine.understand("Open Notepad and type 'Secret Data' and save document")
    plan = planner.plan_task(understanding)

    assert plan.status == PlanStatus.VALID
    assert len(plan.steps) == 9

    # Verify all steps have valid topological index
    for idx, s in enumerate(plan.steps):
        assert s.step_index == idx


# ============================================================================
# 3. Dependency Graph & Cycle Detection
# ============================================================================

def test_dependency_graph_cycle_detection():
    """Verify ActionDependencyGraph detects cyclic dependencies and fails validation."""
    graph = ActionDependencyGraph()
    step_a = PlanStep(step_id="step_a", step_index=0, action_type=PlanActionType.ENSURE_APPLICATION_OPEN, description="A")
    step_b = PlanStep(step_id="step_b", step_index=1, action_type=PlanActionType.FOCUS_APPLICATION, description="B")
    step_c = PlanStep(step_id="step_c", step_index=2, action_type=PlanActionType.ENTER_TEXT, description="C")

    graph.add_step(step_a)
    graph.add_step(step_b)
    graph.add_step(step_c)

    # A -> B -> C -> A (cycle!)
    graph.add_dependency("step_b", "step_a")
    graph.add_dependency("step_c", "step_b")
    graph.add_dependency("step_a", "step_c")

    cycles = graph.detect_cycles()
    assert len(cycles) > 0

    is_valid, errors = graph.validate()
    assert not is_valid
    assert any("cycle" in err.lower() for err in errors)

    with pytest.raises(ValueError, match="cycle"):
        graph.topological_sort()


def test_dependency_graph_missing_dependency():
    """Verify ActionDependencyGraph detects references to non-existent predecessor step IDs."""
    graph = ActionDependencyGraph()
    step_a = PlanStep(
        step_id="step_a",
        step_index=0,
        action_type=PlanActionType.ENTER_TEXT,
        description="A",
        dependencies=["non_existent_step_id"],
    )
    graph.add_step(step_a)

    is_valid, errors = graph.validate()
    assert not is_valid
    assert any("non-existent" in err for err in errors)


# ============================================================================
# 4. Negative Constraints & Safety Semantics
# ============================================================================

def test_negative_save_constraint_blocks_active_save(planner, understanding_engine):
    """Verify that 'Do not save the document' generates a prohibited step without active save dispatch."""
    understanding = understanding_engine.understand("Do not save the document")
    plan = planner.plan_task(understanding)

    assert plan.status == PlanStatus.VALID
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.is_negated is True
    assert "PROHIBITED" in step.description


def test_negative_typing_constraint_in_composite(planner, understanding_engine):
    """Verify 'Open Notepad but don't type anything'."""
    understanding = understanding_engine.understand("Open Notepad but don't type anything")
    plan = planner.plan_task(understanding)

    assert plan.status == PlanStatus.VALID
    # Open Notepad (2 steps) + Prohibited type step (1 step)
    assert len(plan.steps) == 3
    assert plan.steps[0].action_type == PlanActionType.ENSURE_APPLICATION_OPEN
    assert plan.steps[1].action_type == PlanActionType.VERIFY_APPLICATION_AVAILABLE
    assert plan.steps[2].is_negated is True
    assert "PROHIBITED" in plan.steps[2].description


# ============================================================================
# 5. Unsupported Tasks Fail Honestly
# ============================================================================

def test_unsupported_graphical_workflow_fails_honestly(planner, understanding_engine):
    """Test complex unplannable request returns UNSUPPORTED / PARTIALLY_PLANNED."""
    understanding = understanding_engine.understand("Open Photoshop and create a photorealistic dragon")
    plan = planner.plan_task(understanding)

    assert plan.status in {PlanStatus.PARTIALLY_PLANNED, PlanStatus.UNSUPPORTED}
    assert any(s.action_type == PlanActionType.UNSUPPORTED_ACTION for s in plan.steps)
    assert len(plan.unresolved_items) > 0


def test_unknown_task_fails_honestly(planner, understanding_engine):
    """Test completely unplannable prompt returns UNSUPPORTED."""
    understanding = understanding_engine.understand("Perform quantum teleportation")
    plan = planner.plan_task(understanding)

    assert plan.status == PlanStatus.UNSUPPORTED
    assert len(plan.unresolved_items) > 0


# ============================================================================
# 6. Ambiguous Tasks Never Produce Valid Autonomous Steps
# ============================================================================

def test_ambiguous_open_it_plan(planner, understanding_engine):
    """Verify 'Open it' generates an AMBIGUOUS plan with unresolved items."""
    understanding = understanding_engine.understand("Open it")
    plan = planner.plan_task(understanding)

    assert plan.status == PlanStatus.AMBIGUOUS
    assert plan.steps[0].is_ambiguous is True
    assert len(plan.unresolved_items) > 0


def test_ambiguous_click_the_button_plan(planner, understanding_engine):
    """Verify 'Click the button' generates an AMBIGUOUS plan."""
    understanding = understanding_engine.understand("Click the button")
    plan = planner.plan_task(understanding)

    assert plan.status == PlanStatus.AMBIGUOUS
    assert plan.steps[0].is_ambiguous is True


# ============================================================================
# 7. Deferred Runtime Grounding & Zero Coordinate Invariant
# ============================================================================

def test_deferred_grounding_preserves_abstract_targets(planner, understanding_engine):
    """Verify plans preserve abstract target specifications and contain ZERO screen coordinates."""
    prompts = [
        "Open Notepad",
        "Click Save",
        "Open Notepad and type Hello World",
        "Search for pizza places",
    ]
    for p in prompts:
        understanding = understanding_engine.understand(p)
        plan = planner.plan_task(understanding)

        for step in plan.steps:
            # Assert no coordinate attributes
            assert not hasattr(step, "x")
            assert not hasattr(step, "y")
            assert not hasattr(step, "left")
            assert not hasattr(step, "top")

            if step.deferred_grounding:
                req = step.deferred_grounding
                assert len(req.strategy_preferences) > 0
                assert req.target_reference is not None


# ============================================================================
# 8. Determinism
# ============================================================================

def test_plan_determinism(planner, understanding_engine):
    """Verify identical prompts generate equivalent plan step types, descriptions, and dependencies."""
    prompt = "Open Notepad and type 'Deterministic Payload' and click Save"
    u1 = understanding_engine.understand(prompt)
    u2 = understanding_engine.understand(prompt)

    p1 = planner.plan_task(u1)
    p2 = planner.plan_task(u2)

    assert p1.status == p2.status
    assert len(p1.steps) == len(p2.steps)

    for s1, s2 in zip(p1.steps, p2.steps):
        assert s1.step_index == s2.step_index
        assert s1.action_type == s2.action_type
        assert s1.description == s2.description
        assert s1.is_negated == s2.is_negated
        assert s1.is_ambiguous == s2.is_ambiguous
        assert s1.constraints.content == s2.constraints.content
        assert len(s1.dependencies) == len(s2.dependencies)


# ============================================================================
# 9. Plan Explainability
# ============================================================================

def test_plan_explainability(planner, understanding_engine):
    """Verify that plan.explanation contains complete provenance and dependency explanations."""
    understanding = understanding_engine.understand("Open Notepad and type Hello")
    plan = planner.plan_task(understanding)

    assert plan.explanation is not None
    assert plan.explanation["plan_id"] == plan.plan_id
    assert plan.explanation["total_steps"] == len(plan.steps)
    assert "steps" in plan.explanation

    for step in plan.steps:
        step_expl = plan.explanation["steps"][step.step_id]
        assert step_expl["action_type"] == step.action_type.value
        assert len(step_expl["why_created"]) > 0
        assert "must_execute_after" in step_expl
