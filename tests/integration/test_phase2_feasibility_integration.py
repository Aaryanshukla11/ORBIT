"""Phase 2 Integration Test: Full Dual-Gate Feasibility and Directive Pipeline.

Validates:
Preflight (RuntimeFeasibility) -> Planner Candidates -> SemanticFeasibility -> PlanDirective -> PrimitiveComposer
"""

import pytest
from orbit.runtime.agent.contracts import AbstractActionType
from orbit.runtime.cognitive.agent_planner import AgentPlanner
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective, SubObjective
from orbit.runtime.cognitive.primitive_composer import PrimitiveComposer
from orbit.runtime.cognitive.runtime_feasibility import RuntimeFeasibilityEvaluator
from orbit.runtime.world_model.model import AgentWorldModel


@pytest.mark.asyncio
async def test_full_phase2_dual_gate_feasibility_pipeline_integration():
    # 1. Setup WorldModel and Observation
    wm = AgentWorldModel(is_desktop_locked=False)
    obs = CurrentStateObservation(
        active_process_name="explorer.exe",
        active_window_title="Desktop",
    )

    # 2. Setup Subgoal and Objective
    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a house",
        user_goal="Draw house in Paint",
        end_condition="paint_has_drawing",
        parameters={
            "strokes": [
                [(0.2, 0.4), (0.5, 0.1), (0.8, 0.4)],  # roof
                [(0.2, 0.4), (0.8, 0.4), (0.8, 0.8), (0.2, 0.8), (0.2, 0.4)],  # base
            ]
        },
    )
    subgoal = SubObjective(
        sub_id="sub_house_01",
        title="Render house strokes on Paint canvas",
        target_entity="mspaint",
    )

    # 3. Gate 1: Runtime Feasibility Preflight
    runtime_eval = RuntimeFeasibilityEvaluator(check_network=False)
    rf_res = await runtime_eval.evaluate(subgoal, wm, obs)
    assert rf_res.is_feasible is True

    # 4. Gate 2: AgentPlanner Candidate Generation & Semantic Feasibility
    planner = AgentPlanner()
    directive, sf_report = planner.plan_subgoal(obj, subgoal, wm, obs)

    assert sf_report.is_feasible is True
    assert directive is not None
    assert directive.intent_strategy == "CANVAS_RENDERING"
    assert directive.preferred_primitives == [AbstractActionType.DRAW_STROKES]
    assert directive.feasibility_score >= 0.8

    # 5. Hand directive to PrimitiveComposer
    composer = PrimitiveComposer()
    seq = composer.compose_from_directive(directive)

    assert seq is not None
    assert len(seq.actions) == 1
    assert seq.actions[0].action_type == AbstractActionType.DRAW_STROKES
    assert seq.actions[0].target.role == "canvas"
    assert len(seq.actions[0].parameters["strokes"]) == 2
