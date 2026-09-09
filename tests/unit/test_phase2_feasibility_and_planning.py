"""Phase 2 Unit Tests: Feasibility Ordering, Plan Directives, and Semantic Evaluation.

Tests adherence to ASTRA evaluation dimensions:
- Dimension 3: Dual-Gate Feasibility (Runtime Preflight + Semantic Candidate Evaluation)
- Dimension 5: PlanDirective Formulation & Authoritative Strategy Selection
- Dimension 11: Single Canonical Primitive Execution Authority via Directives
- Dimension 23: Creative Generation Contract (zero screen coordinates, pure canonical primitives)
"""

import pytest
from orbit.runtime.agent.contracts import (
    AbstractActionType,
    ActionOutcomeContract,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.cognitive.agent_planner import AgentPlanner
from orbit.runtime.cognitive.models import (
    CurrentStateObservation,
    StructuredObjective,
    SubObjective,
)
from orbit.runtime.cognitive.plan_directive import PlanDirective
from orbit.runtime.cognitive.primitive_composer import PrimitiveComposer
from orbit.runtime.cognitive.semantic_feasibility import (
    CandidatePlan,
    SemanticFeasibilityEvaluator,
    SemanticFeasibilityReport,
)
from orbit.runtime.world_model.model import AgentWorldModel, FailedSequenceRecord


# ============================================================================
# Dimension 3 & 5: Semantic Feasibility Candidate Evaluation
# ============================================================================

def test_semantic_feasibility_evaluates_candidate_plans():
    """Requirement: SemanticFeasibility scores candidate plans and selects best candidate."""
    evaluator = SemanticFeasibilityEvaluator(min_feasibility_threshold=0.5)
    wm = AgentWorldModel()

    cand1 = CandidatePlan(
        subgoal_id="sub_launch",
        intent_strategy="GUI_INTERACTIVE",
        proposed_primitives=[AbstractActionType.LAUNCH_APPLICATION],
        targets=[SemanticTarget(name="notepad", role="window")],
        expected_outcome=ActionOutcomeContract(expected_state_transition="Notepad window focused"),
        estimated_complexity=1,
    )

    cand_empty = CandidatePlan(
        subgoal_id="sub_empty",
        intent_strategy="GUI_INTERACTIVE",
        proposed_primitives=[],
        targets=[],
        expected_outcome=ActionOutcomeContract(expected_state_transition="Nothing"),
    )

    best, report = evaluator.select_feasible_plan([cand_empty, cand1], wm)
    assert report.is_feasible is True
    assert best is not None
    assert best.candidate_id == cand1.candidate_id
    assert report.candidate_scores[cand_empty.candidate_id] == 0.0
    assert report.candidate_scores[cand1.candidate_id] >= 0.8


def test_semantic_feasibility_penalizes_past_failed_sequences():
    """Requirement: Sequences matching recent failure records in WorldModel are penalized."""
    evaluator = SemanticFeasibilityEvaluator()
    wm = AgentWorldModel()
    wm.failed_primitive_sequences.append(
        FailedSequenceRecord(
            sub_goal_title="Open App",
            primitive_sequence=["LAUNCH_APPLICATION"],
            failed_at_index=0,
            action_that_failed="LAUNCH_APPLICATION",
            failure_reason="Process blocked",
            root_cause="Permissions",
        )
    )

    cand = CandidatePlan(
        subgoal_id="sub_app",
        intent_strategy="GUI_INTERACTIVE",
        proposed_primitives=[AbstractActionType.LAUNCH_APPLICATION],
        targets=[SemanticTarget(name="blocked_app", role="window")],
        expected_outcome=ActionOutcomeContract(expected_state_transition="Window open"),
    )

    score, rejections = evaluator.evaluate_candidate(cand, wm)
    assert score <= 0.5
    assert any("matches recently failed sequence" in r for r in rejections)


def test_semantic_feasibility_rejects_unnormalized_stroke_coordinates():
    """Requirement: Drawing candidates with unnormalized screen coordinates are rejected (score 0.0)."""
    evaluator = SemanticFeasibilityEvaluator()
    wm = AgentWorldModel()

    # Coordinates outside [0.0, 1.0]
    bad_cand = CandidatePlan(
        subgoal_id="sub_draw",
        intent_strategy="CANVAS_RENDERING",
        proposed_primitives=[AbstractActionType.DRAW_STROKES],
        targets=[SemanticTarget(name="Paint", role="canvas")],
        expected_outcome=ActionOutcomeContract(expected_state_transition="Drawn"),
        creative_payload={"strokes": [[(1250, 640), (1300, 700)]]},
    )

    score, rejections = evaluator.evaluate_candidate(bad_cand, wm)
    assert score == 0.0
    assert any("Invalid unnormalized stroke coordinate" in r for r in rejections)


# ============================================================================
# Dimension 5 & 11: AgentPlanner Ordering and PlanDirective Emission
# ============================================================================

def test_agent_planner_orders_feasibility_before_directive_emission():
    """Requirement: AgentPlanner strictly evaluates candidates before emitting PlanDirective."""
    planner = AgentPlanner()
    wm = AgentWorldModel()

    objective = StructuredObjective(
        raw_prompt="Open Notepad and write test note",
        user_goal="Write test note in Notepad",
        end_condition="notepad_has_text",
        parameters={"text": "Phase 2 Verified"},
    )
    subgoal = SubObjective(
        sub_id="sub_notepad_launch",
        title="Launch Notepad Application",
        description="Open notepad.exe to prepare for writing",
        target_entity="notepad",
    )

    directive, report = planner.plan_subgoal(objective, subgoal, wm)

    assert report.is_feasible is True
    assert directive is not None
    assert isinstance(directive, PlanDirective)
    assert directive.subgoal_id == "sub_notepad_launch"
    assert directive.preferred_primitives == [AbstractActionType.LAUNCH_APPLICATION]
    assert directive.feasibility_score >= 0.8
    assert directive.semantic_targets[0].name == "notepad"


def test_primitive_composer_consumes_plan_directive_cleanly():
    """Requirement: PrimitiveComposer translates PlanDirective into validated canonical primitives."""
    composer = PrimitiveComposer()

    directive = PlanDirective(
        objective_id="obj_draw_01",
        subgoal_id="sub_draw_01",
        subgoal_title="Draw Square in Paint",
        intent_strategy="CANVAS_RENDERING",
        semantic_targets=[SemanticTarget(name="Paint", role="canvas", context="mspaint")],
        preferred_primitives=[AbstractActionType.DRAW_STROKES],
        expected_outcome=ActionOutcomeContract(
            expected_state_transition="Square drawn on canvas",
            verification_strategy=VerificationStrategy.CANVAS_CHANGE,
        ),
        creative_payload={
            "strokes": [
                [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8), (0.2, 0.2)]
            ]
        },
    )

    seq = composer.compose_from_directive(directive)
    assert seq is not None
    assert len(seq.actions) == 1
    action = seq.actions[0]
    assert action.action_type == AbstractActionType.DRAW_STROKES
    assert action.parameters.get("strokes") == directive.creative_payload["strokes"]
    assert action.target.role == "canvas"
