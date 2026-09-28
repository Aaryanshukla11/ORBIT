"""P0 Authoritative Planning & Execution Convergence Tests (Phase 10).

Proves the core P0 invariants:
1. PlanDirective is the ONLY authoritative representation of what ORBIT intends to execute.
2. CognitiveDecisionEngine / OrbitDecisionEngine cannot bypass PlanDirective or dispatch physical actions.
3. PrimitiveComposer mechanically translates PlanDirective and fails closed if input is insufficient without inventing plans.
4. AgentPlanner is the authoritative source of PlanDirective.
5. PrimitiveExecutionController is the ONLY physical execution gateway.
6. Recovery flows through FailureAnalyst -> WorldModel -> AgentPlanner.replan() -> NEW PlanDirective.
7. Verification failure triggers replanning cycle, not false success.
8. No hardcoded drawing coordinate sequences in AgentPlanner.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionOutcomeContract,
    ActionExecutionOutcome,
    ActionExecutionResult,
    OutcomeStatus,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.agent_planner import AgentPlanner
from orbit.runtime.cognitive.engine import CognitiveDecisionEngine, OrbitDecisionEngine
from orbit.runtime.cognitive.failure_analyst import CognitiveFailureAnalyst, FailureCategory, FailureReport
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CurrentStateObservation,
    ExecutionBudget,
    StructuredObjective,
    SubObjective,
)
from orbit.runtime.cognitive.plan_directive import PlanDirective
from orbit.runtime.cognitive.primitive_composer import PrimitiveComposer
from orbit.runtime.cognitive.primitive_execution_controller import PrimitiveExecutionController
from orbit.runtime.cognitive.primitive_validator import PrimitiveValidator
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.task_completion.models import GoalVerificationResult, TaskCompletionStatus
from orbit.runtime.task_completion.multi_evidence_verifier import MultiEvidenceActionVerifier
from orbit.runtime.world_model.model import AgentWorldModel


# ---------------------------------------------------------------------------
# TEST 1 — PlanDirective authority
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_1_plan_directive_authority_cannot_be_bypassed_by_competing_decision_engine():
    """Conflicting intent from legacy decision engine cannot bypass authoritative PlanDirective."""
    obs = CurrentStateObservation(observation_id="obs_001", active_window_title="Desktop")
    observer = MagicMock()
    observer.observe = AsyncMock(return_value=obs)

    # Planner produces PlanDirective authorizing ONLY LAUNCH_APPLICATION for 'notepad'
    planner = MagicMock(spec=AgentPlanner)
    directive = PlanDirective(
        objective_id="obj_test_1",
        subgoal_id="sg_1",
        subgoal_title="Launch Notepad",
        intent_strategy="GUI_INTERACTIVE",
        preferred_primitives=[AbstractActionType.LAUNCH_APPLICATION],
        semantic_targets=[SemanticTarget(name="notepad", role="application")],
        creative_payload={"application_name": "notepad"},
        expected_outcome=ActionOutcomeContract(
            expected_state_transition="notepad_window_open",
            verification_strategy=VerificationStrategy.WINDOW_FOCUS,
        ),
    )
    report = MagicMock()
    report.is_feasible = True
    planner.plan_subgoal = MagicMock(return_value=(directive, report))

    # Competing legacy decision engine attempts conflicting intent: CLICK 'MaliciousButton'
    competing_decision = CognitiveDecision(
        step_index=0,
        decision_summary="Competing rogue planner trying to click button",
        decision_confidence=1.0,
        next_action=AbstractAction(
            action_type=AbstractActionType.CLICK,
            target=SemanticTarget(name="MaliciousButton", role="button"),
        ),
    )
    decision_engine = MagicMock(spec=CognitiveDecisionEngine)
    decision_engine.decide_next_step = AsyncMock(return_value=competing_decision)

    executed_actions = []
    controller = MagicMock(spec=PrimitiveExecutionController)

    async def fake_execute(*args, **kwargs):
        action = kwargs.get("action") or (args[0] if args else None)
        executed_actions.append(action)
        return MagicMock(
            execution_outcome=ActionExecutionOutcome(
                action_id=action.action_id if action else "act_1",
                action_type=action.action_type if action else AbstractActionType.LAUNCH_APPLICATION,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                expected_effect_observed=True,
                dispatch_success=True,
            ),
            post_observation=obs,
            should_continue=True,
        )

    controller.execute_primitive = AsyncMock(side_effect=fake_execute)

    loop = AgentExecutionLoop(
        observer=observer,
        decision_engine=decision_engine,
        planner=planner,
        budget=ExecutionBudget(max_total_actions=1),
    )
    loop._primitive_execution_controller = controller

    res = await loop.run("Launch Notepad")

    # Authoritative PlanDirective governed execution: LAUNCH_APPLICATION notepad was executed, NOT competing CLICK
    assert len(executed_actions) == 1
    assert executed_actions[0].action_type == AbstractActionType.LAUNCH_APPLICATION
    assert executed_actions[0].parameters.get("application_name") == "notepad"


# ---------------------------------------------------------------------------
# TEST 2 — Composer cannot plan
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_2_composer_cannot_plan_fails_closed_without_directive():
    """Providing insufficient/non-semantic input to PrimitiveComposer fails closed without inventing a task plan."""
    composer = PrimitiveComposer(model_client=None)

    # Vague goal given to compose() directly without LLM
    context = MagicMock()
    context.to_dict = MagicMock(return_value={})
    objective = StructuredObjective(
        raw_prompt="Random ambiguous user text",
        user_goal="Random ambiguous user text",
        end_condition="complete",
    )

    seq = await composer.compose(objective=objective, sub_objective=None, context=context)

    # Fail closed: ZERO actions invented
    assert isinstance(seq.actions, list)
    assert len(seq.actions) == 0


# ---------------------------------------------------------------------------
# TEST 3 — Planner creates PlanDirective
# ---------------------------------------------------------------------------
def test_3_planner_creates_plan_directive_as_semantic_source():
    """AgentPlanner is the sole semantic source producing PlanDirective."""
    planner = AgentPlanner()
    objective = StructuredObjective(
        raw_prompt="Launch Calculator",
        user_goal="Launch Calculator",
        end_condition="calc_opened",
        parameters={"app_name": "calc"},
    )
    subgoal = SubObjective(
        sub_id="sg_calc",
        title="Open calc application",
        description="Launch calculator window",
        target_entity="calc",
        preferred_primitives=[AbstractActionType.LAUNCH_APPLICATION],
    )
    world_model = AgentWorldModel()

    directive, report = planner.plan_subgoal(
        objective=objective,
        subgoal=subgoal,
        world_model=world_model,
    )

    assert directive is not None
    assert report.is_feasible is True
    assert isinstance(directive, PlanDirective)
    assert directive.objective_id == objective.objective_id
    assert directive.subgoal_id == "sg_calc"
    assert AbstractActionType.LAUNCH_APPLICATION in directive.preferred_primitives


# ---------------------------------------------------------------------------
# TEST 4 — Physical execution gateway
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_4_physical_execution_gateway_is_primitive_execution_controller():
    """All physical actions must route through PrimitiveExecutionController."""
    controller_mock = MagicMock(spec=PrimitiveExecutionController)
    obs = CurrentStateObservation(observation_id="obs_002", active_window_title="Editor")

    action = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        parameters={"text": "hello"},
        target=SemanticTarget(name="Document", role="edit"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="text typed"),
    )

    controller_mock.execute_primitive = AsyncMock(
        return_value=MagicMock(
            execution_outcome=ActionExecutionOutcome(
                action_id=action.action_id,
                action_type=action.action_type,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                expected_effect_observed=True,
                dispatch_success=True,
            ),
            post_observation=obs,
            should_continue=True,
        )
    )

    observer = MagicMock()
    observer.observe = AsyncMock(return_value=obs)

    loop = AgentExecutionLoop(
        observer=observer,
        budget=ExecutionBudget(max_total_actions=1),
    )
    loop._primitive_execution_controller = controller_mock

    # Direct plan directive setup
    directive = PlanDirective(
        objective_id="obj_type",
        subgoal_id="sg_type",
        subgoal_title="Type text",
        preferred_primitives=[AbstractActionType.TYPE_TEXT],
        creative_payload={"text": "hello"},
    )
    loop._planner.plan_subgoal = MagicMock(return_value=(directive, MagicMock(is_feasible=True)))

    await loop.run("Type hello")

    # Prove execute_primitive on controller was invoked
    assert controller_mock.execute_primitive.called


# ---------------------------------------------------------------------------
# TEST 5 — Recovery convergence
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_5_recovery_convergence_routes_via_failure_analyst_world_model_and_replan():
    """Forced action failure routes: FailureAnalyst -> WorldModel -> AgentPlanner.replan() -> NEW PlanDirective."""
    obs_pre = CurrentStateObservation(observation_id="obs_pre", active_window_title="Main")
    obs_post = CurrentStateObservation(observation_id="obs_post", active_window_title="Main")

    observer = MagicMock()
    observer.observe = AsyncMock(side_effect=[obs_pre, obs_post, obs_post, obs_post])

    # Initial directive: click 'ButtonA'
    initial_directive = PlanDirective(
        directive_id="dir_initial_fail",
        objective_id="obj_rec",
        subgoal_id="sg_main",
        subgoal_title="Click ButtonA",
        preferred_primitives=[AbstractActionType.CLICK],
        semantic_targets=[SemanticTarget(name="ButtonA", role="button")],
    )

    # Replanned directive: send hotkey 'enter'
    replanned_directive = PlanDirective(
        directive_id="dir_replan_success",
        objective_id="obj_rec",
        subgoal_id="sg_main",
        subgoal_title="Send Enter",
        preferred_primitives=[AbstractActionType.SEND_HOTKEY],
        semantic_targets=[SemanticTarget(name="ButtonA", role="button")],
        creative_payload={"hotkey": "enter"},
    )

    planner = MagicMock(spec=AgentPlanner)
    planner.plan_subgoal = MagicMock(return_value=(initial_directive, MagicMock(is_feasible=True)))
    planner.replan = MagicMock(return_value=(replanned_directive, MagicMock(is_feasible=True)))

    controller = MagicMock(spec=PrimitiveExecutionController)
    call_count = 0

    async def fake_exec_with_failure(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        action = kwargs.get("action") or (args[0] if args else None)
        if call_count == 1:
            # First action fails verification
            return MagicMock(
                execution_outcome=ActionExecutionOutcome(
                    action_id=action.action_id if action else "act_1",
                    action_type=action.action_type if action else AbstractActionType.CLICK,
                    outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
                    expected_effect_observed=False,
                    dispatch_success=True,
                    verification_reason="Target button unresponsive",
                ),
                post_observation=obs_post,
                should_continue=False,
            )
        else:
            # Second action succeeds
            return MagicMock(
                execution_outcome=ActionExecutionOutcome(
                    action_id=action.action_id if action else "act_2",
                    action_type=action.action_type if action else AbstractActionType.SEND_HOTKEY,
                    outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                    expected_effect_observed=True,
                    dispatch_success=True,
                ),
                post_observation=obs_post,
                should_continue=True,
            )

    controller.execute_primitive = AsyncMock(side_effect=fake_exec_with_failure)

    loop = AgentExecutionLoop(
        observer=observer,
        planner=planner,
        budget=ExecutionBudget(max_total_actions=2, max_recoveries_per_transition=2),
    )
    loop._primitive_execution_controller = controller
    loop._resolve_target_coordinates = AsyncMock(return_value=(100, 100))

    res = await loop.run("Click ButtonA")

    # Proves AgentPlanner.replan was called with FailureReport context and produced a NEW PlanDirective
    assert planner.replan.called
    replan_args = planner.replan.call_args[1]
    assert isinstance(replan_args.get("failure_report"), FailureReport)
    assert replan_args.get("failed_directive").directive_id == "dir_initial_fail"


# ---------------------------------------------------------------------------
# TEST 6 — Verification failure
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_6_verification_failure_when_os_succeeds_but_environment_state_unchanged():
    """Action is unverified when OS API returns success without expected environment transition."""
    verifier = MultiEvidenceActionVerifier()
    pre_obs = CurrentStateObservation(observation_id="pre_1", active_window_title="Editor - Untitled")
    post_obs = CurrentStateObservation(observation_id="post_1", active_window_title="Editor - Untitled")

    action = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        parameters={"application_name": "calc"},
        target=SemanticTarget(name="calc", role="application"),
        outcome_contract=ActionOutcomeContract(
            expected_state_transition="calc_window_open",
            verification_strategy=VerificationStrategy.WINDOW_FOCUS,
        ),
    )

    res = await verifier.verify_action_effect(
        action=action,
        pre_obs=pre_obs,
        post_obs=post_obs,
    )

    # Proves verification failed because expected window title 'calc' did not appear in active window
    assert res.is_verified is False
    assert res.outcome_status in (OutcomeStatus.EFFECT_UNVERIFIED, OutcomeStatus.DISPATCH_FAILED)


# ---------------------------------------------------------------------------
# TEST 7 — No hardcoded drawing plan
# ---------------------------------------------------------------------------
def test_7_no_hardcoded_drawing_plan_coordinates_in_agent_planner():
    """AgentPlanner does not contain hardcoded coordinate stroke polygons."""
    import inspect
    import orbit.runtime.cognitive.agent_planner as ap_mod

    source = inspect.getsource(ap_mod)
    # Ensure hardcoded normalized square coordinates are absent from planner
    assert "[(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8), (0.2, 0.2)]" not in source
    assert "[(0.5, 0.2), (0.8, 0.8), (0.2, 0.8), (0.5, 0.2)]" not in source


# ---------------------------------------------------------------------------
# TEST 8 — DecisionEngine authority
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_8_decision_engine_cannot_directly_execute_physical_actions():
    """CognitiveDecisionEngine is advisory and cannot execute physical capabilities directly."""
    engine = CognitiveDecisionEngine()
    obs = CurrentStateObservation(observation_id="obs_adv", active_window_title="Desktop")
    obj = StructuredObjective(
        raw_prompt="Open notepad",
        user_goal="Open notepad",
        end_condition="notepad_open",
    )

    dec = await engine.decide_next_step(
        objective=obj,
        observation=obs,
        step_history=[],
        step_index=0,
    )

    # Engine produces a CognitiveDecision data model only, with zero capability dispatch authority
    assert isinstance(dec, CognitiveDecision)
    assert not hasattr(engine, "execute")
    assert not hasattr(engine, "dispatch")
    assert not hasattr(engine, "send_input")
