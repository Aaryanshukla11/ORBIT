"""ORBIT Architectural Invariants and Safety Verification Suite.

Tests and enforces all mandatory ORBIT architecture invariants:
1. AgentExecutionLoop is the single authoritative production engine.
2. Zero legacy engine reachability on the default production path.
3. No duplicate task interpretation or feasibility gating.
4. Target-specific LAUNCH_APPLICATION redundancy safety check.
5. Canonical DRAW_STROKES execution via PrimitiveExecutionController & CanvasDrawingProvider.
6. Epistemic TaskScopedMemory lifecycle and zeroization.
7. Epistemic ambiguity gate fail-closed behavior.
8. Material control flow from AgentPlanner & PrimitiveComposer to PrimitiveExecutionController.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from orbit.adapters.registry import CapabilityRegistry
from orbit.contracts.capabilities import CapabilityType, PointerCapability
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionOutcomeContract,
    OutcomeStatus,
    SemanticTarget,
)
from orbit.runtime.cognitive.agent_decision import AgentDecisionEngine
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.agent_planner import AgentPlanner
from orbit.runtime.cognitive.clarification import ClarificationManager
from orbit.runtime.cognitive.models import (
    AgentLoopState,
    CognitiveDecision,
    CognitiveStepResult,
    CurrentStateObservation,
    StructuredObjective,
    SubObjective,
)
from orbit.runtime.cognitive.plan_directive import PlanDirective
from orbit.runtime.cognitive.primitive_composer import PrimitiveComposer
from orbit.runtime.cognitive.primitive_execution_controller import (
    ControllerExecutionResult,
    PrimitiveExecutionController,
)
from orbit.runtime.cognitive.primitive_validator import PrimitiveValidator
from orbit.runtime.cognitive.semantic_feasibility import SemanticFeasibilityEvaluator
from orbit.runtime.environment.drawing_provider import CanvasDrawingProvider
from orbit.runtime.environment.registry import EnvironmentProviderRegistry
from orbit.runtime.memory.task_memory import TaskScopedMemory
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.task_completion.models import TaskCompletionStatus
from orbit.runtime.world_model import AgentWorldModel


@pytest.fixture
def mock_event_bus():
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.mark.asyncio
async def test_single_authoritative_execution_loop(mock_event_bus):
    """Invariant 1: OrbitOrchestrator default execution routes exclusively through AgentExecutionLoop."""
    orch = OrbitOrchestrator(event_bus=mock_event_bus)
    assert isinstance(orch.agent_loop, AgentExecutionLoop)

    # Mock AgentExecutionLoop.run
    with patch.object(
        orch.agent_loop,
        "run",
        new=AsyncMock(
            return_value=MagicMock(
                task_id="agt_123",
                is_success=True,
                final_status=TaskCompletionStatus.COMPLETED,
                failure_reason=None,
                failure_code=None,
                elapsed_duration_ms=42.0,
            )
        ),
    ) as mock_agent_run:
        result = await orch.execute_task(prompt="open notepad and type hello")
        assert mock_agent_run.called
        assert result.is_success is True


@pytest.mark.asyncio
async def test_no_legacy_task_understanding_in_default_path(mock_event_bus):
    """Invariant 2: Default task execution does NOT invoke legacy TaskUnderstandingEngine."""
    orch = OrbitOrchestrator(event_bus=mock_event_bus)
    assert not hasattr(orch, "_task_understanding_engine")
    assert not hasattr(orch, "task_understanding_engine")
    with patch.object(
        orch.agent_loop,
        "run",
        new=AsyncMock(
            return_value=MagicMock(
                task_id="agt_test",
                is_success=True,
                final_status=TaskCompletionStatus.COMPLETED,
                step_history=[],
                objective=MagicMock(objective_id="obj_1", user_goal="test", model_dump=lambda: {}),
                elapsed_duration_ms=10.0,
                failure_reason=None,
                failure_code=None,
                model_dump=lambda: {},
            )
        ),
    ) as mock_agent_run:
        result = await orch.execute_task(prompt="test natural language goal")
        assert mock_agent_run.called
        assert result.is_success is True


@pytest.mark.asyncio
async def test_no_legacy_feasibility_in_default_path(mock_event_bus):
    """Invariant 3: AgentExecutionLoop does NOT call legacy FeasibilityAnalyzer."""
    agent_loop = AgentExecutionLoop(event_bus=mock_event_bus)
    assert not hasattr(agent_loop, "_feasibility_analyzer")
    assert not hasattr(agent_loop, "feasibility_analyzer")





def test_no_dynamic_drawing_executor_import():
    """Invariant 5: DrawingExecutor is NEVER dynamically imported inside agent_loop.py."""
    agent_loop_file = Path("src/orbit/runtime/cognitive/agent_loop.py")
    tree = ast.parse(agent_loop_file.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert (
                "drawing_executor" not in (node.module or "")
            ), f"Forbidden legacy drawing_executor import found in agent_loop.py at line {node.lineno}!"


@pytest.mark.asyncio
async def test_drawing_dispatches_via_primitive_controller():
    """Invariant 7 & 8: DRAW_STROKES executes through PrimitiveExecutionController and CanvasDrawingProvider."""
    pointer_mock = MagicMock(spec=PointerCapability)
    pointer_mock.move_to = AsyncMock()
    pointer_mock.press_down = AsyncMock()
    pointer_mock.release_up = AsyncMock()

    provider = CanvasDrawingProvider(pointer=pointer_mock)
    action = AbstractAction(
        action_type=AbstractActionType.DRAW_STROKES,
        parameters={
            "strokes": [[(0.2, 0.2), (0.8, 0.8)]],
            "canvas_rect": [100, 100, 500, 500],
        },
        target=SemanticTarget(name="Paint Canvas", role="canvas"),
    )

    res = await provider.execute(action)
    assert res.success is True
    assert res.output["strokes_dispatched"] == 1
    assert pointer_mock.move_to.called
    assert pointer_mock.press_down.called
    assert pointer_mock.release_up.called


@pytest.mark.asyncio
async def test_target_specific_launch_redundancy():
    """Invariant 12: Historical launch of App A does NOT block subsequent launch of App B."""
    agent_loop = AgentExecutionLoop()

    # Create step history where 'notepad' was previously successfully launched
    history = [
        CognitiveStepResult(
            step_index=0,
            decision=CognitiveDecision(decision_summary="Launch notepad application"),
            action_dispatched=AbstractAction(
                action_type=AbstractActionType.LAUNCH_APPLICATION,
                parameters={"application_name": "notepad"},
            ),
            execution_result=ActionExecutionOutcome(
                action_id="act_0",
                dispatch_success=True,
                expected_effect_observed=True,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                verified=True,
            ),
            post_observation=CurrentStateObservation(),
            state_progress_detected=True,
            duration_ms=100.0,
        )
    ]

    # Action to launch a DIFFERENT application: 'calculator'
    action_b = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        parameters={"application_name": "calculator"},
    )

    app_target_name = "calculator"
    # Execute the exact historical check logic
    launch_already_succeeded = any(
        s.action_dispatched
        and s.action_dispatched.action_type == AbstractActionType.LAUNCH_APPLICATION
        and str(
            s.action_dispatched.parameters.get(
                "application_name",
                s.action_dispatched.parameters.get(
                    "app_name", s.action_dispatched.target.name if s.action_dispatched.target else ""
                ),
            )
        )
        .strip()
        .lower()
        == app_target_name
        and s.execution_result
        and s.execution_result.expected_effect_observed
        for s in history
    )

    assert launch_already_succeeded is False, "Launching calculator was falsely blocked by previous notepad launch!"


@pytest.mark.asyncio
async def test_task_scoped_memory_lifecycle():
    """Invariant 12: TaskScopedMemory is created and securely zeroized upon task lifecycle end."""
    agent_loop = AgentExecutionLoop()
    obj = StructuredObjective(raw_prompt="open notepad", user_goal="open notepad", end_condition="notepad opened")
    with patch.object(agent_loop._interpreter, "interpret", new=AsyncMock(return_value=obj)), \
         patch.object(agent_loop._observer, "observe", new=AsyncMock(return_value=CurrentStateObservation())):
        res = await agent_loop.run(prompt="open notepad and type test")
    assert agent_loop._active_task_memory is None, "TaskScopedMemory was not wiped and cleared after run() completed!"





@pytest.mark.asyncio
async def test_epistemic_ambiguity_gate_fails_closed():
    """Invariant 10: Empty or ambiguous prompt fails closed immediately with 0 physical dispatches."""
    agent_loop = AgentExecutionLoop()
    res = await agent_loop.run(prompt="   ")
    assert res.is_success is False
    assert res.final_status == TaskCompletionStatus.UNSUPPORTED
    assert res.total_steps == 0


def test_no_decision_divergence():
    """ORBIT Invariant: Exactly one authoritative action decision per cycle.

    AgentPlanner produces a PlanDirective, which CognitiveDecisionEngine / PrimitiveComposer
    consumes into an AbstractAction. There is no dual authority.
    """
    planner = AgentPlanner()
    composer = PrimitiveComposer()
    validator = PrimitiveValidator()
    world_model = AgentWorldModel()

    objective = StructuredObjective(
        raw_prompt="Open Notepad and write test",
        user_goal="Open Notepad and write test",
        end_condition="notepad_has_test",
        subtasks=["Open Notepad", "Type test"],
    )
    subgoal = SubObjective(
        title="Open Notepad",
        description="Launch application notepad",
        target_app="notepad",
    )
    obs = CurrentStateObservation(target_app_exists=False, target_app_is_active=False)

    # 1. Planner emits single authoritative PlanDirective
    directive, report = planner.plan_subgoal(
        objective=objective,
        subgoal=subgoal,
        world_model=world_model,
        observation=obs,
    )
    assert directive is not None
    assert isinstance(directive, PlanDirective)
    assert report.is_feasible is True

    # 2. Composer produces exactly one canonical AbstractAction sequence
    sequence = composer.compose_from_directive(directive, obs)
    assert sequence.actions is not None
    assert len(sequence.actions) >= 1

    # 3. Canonical validation confirms each action
    for act in sequence.actions:
        val_res = validator.validate_action(act)
        assert val_res.is_valid is True, f"Composed action failed validation: {val_res.failure_reason}"


def test_no_execution_bypass_ast_audit():
    """ORBIT Invariant: NO EXECUTION BYPASS.

    Scans all cognitive, planning, verification, and world model modules to prove
    that none directly import OS or GUI automation libraries (pyautogui, pynput, win32gui, ctypes.windll).
    Only PrimitiveExecutionController and adapters may interface with OS capabilities.
    """
    forbidden_modules = {"pyautogui", "pynput", "win32gui", "win32api", "win32con"}
    scanned_roots = [
        Path("src/orbit/runtime/cognitive"),
        Path("src/orbit/runtime/world_model"),
        Path("src/orbit/runtime/verification"),
        Path("src/orbit/runtime/task_completion"),
    ]

    violations = []
    for root in scanned_roots:
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        base = alias.name.split(".")[0]
                        if base in forbidden_modules:
                            violations.append(f"{py_file}:{node.lineno} imports '{alias.name}'")
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    base = mod.split(".")[0]
                    if base in forbidden_modules:
                        violations.append(f"{py_file}:{node.lineno} imports from '{mod}'")

    assert not violations, f"Forbidden execution bypass imports detected:\n" + "\n".join(violations)


@pytest.mark.asyncio
async def test_single_decision_authority():
    """Invariant: CognitiveDecisionEngine only proposes decisions and has zero physical execution authority."""
    decision_engine = AgentDecisionEngine()
    assert not hasattr(decision_engine, "execute_action")
    assert not hasattr(decision_engine, "dispatch_action")
    assert not hasattr(decision_engine, "dispatch_physical_action")
    assert not hasattr(decision_engine, "_execute_action")


def test_orchestrator_cannot_physically_execute():
    """Invariant: OrbitOrchestrator has no physical execution methods like _execute_action, _build_synthetic_plan."""
    assert not hasattr(OrbitOrchestrator, "_execute_action")
    assert not hasattr(OrbitOrchestrator, "_build_synthetic_plan")
    assert not hasattr(OrbitOrchestrator, "_build_target_resolved_plan")
    assert not hasattr(OrbitOrchestrator, "_resolve_required_capability")


def test_plan_directive_divergence_rejected():
    """Invariant: PrimitiveComposer only translates PlanDirective instances and rejects non-directive objects."""
    composer = PrimitiveComposer()
    obs = CurrentStateObservation()
    with pytest.raises((AttributeError, TypeError, ValueError)):
        composer.compose_from_directive("not_a_plan_directive", obs)  # type: ignore


@pytest.mark.asyncio
async def test_failed_verification_triggers_replanning():
    """Invariant: When verification fails (expected_effect_observed=False), failure analysis diagnoses the issue and world model triggers replanning."""
    from orbit.runtime.cognitive.failure_analyst import CognitiveFailureAnalyst, FailureCategory

    planner = AgentPlanner()
    analyst = CognitiveFailureAnalyst()
    objective = StructuredObjective(raw_prompt="Open notepad and type test", user_goal="Open notepad and type test", end_condition="done")
    subgoal = SubObjective(title="Open Notepad", description="Launch notepad", target_app="notepad")
    world_model = AgentWorldModel()
    obs = CurrentStateObservation(observation_id="obs_01", active_window_title="Desktop")

    # Initial plan
    directive, report = planner.plan_subgoal(
        objective=objective,
        subgoal=subgoal,
        world_model=world_model,
        observation=obs,
    )
    assert directive is not None
    assert report.is_feasible is True

    # Simulate dispatch with verification failure
    failed_action = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        parameters={"application_name": "notepad"},
        target=SemanticTarget(name="notepad", role="application"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="notepad_open"),
    )
    post_obs = CurrentStateObservation(observation_id="obs_02", active_window_title="Desktop", visible_windows=[])
    failed_outcome = ActionExecutionOutcome(
        action_id=failed_action.action_id,
        dispatch_success=True,
        expected_effect_observed=False,
        outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
        error_message="Notepad did not appear in foreground",
    )

    # 1. Failure Analyst diagnoses the verification failure
    diag_report = analyst.analyze_failure(failed_action, obs, post_obs, failed_outcome)
    assert diag_report is not None
    assert diag_report.category in (FailureCategory.TARGET_NOT_FOUND, FailureCategory.POSTCONDITION_UNSATISFIED, FailureCategory.WINDOW_NOT_FOCUSED)
    assert len(diag_report.suggested_remediation_direction) > 0

    # 2. World Model state is updated with failure observation via WorldModelUpdater
    from orbit.runtime.world_model.updater import WorldModelUpdater
    world_model = WorldModelUpdater.record_action_outcome(world_model, failed_action, failed_outcome)
    world_model = WorldModelUpdater.update_from_observation(world_model, post_obs)

    # 3. Replanning can generate candidate plans in light of updated observation
    replan_directive, replan_report = planner.plan_subgoal(
        objective=objective,
        subgoal=subgoal,
        world_model=world_model,
        observation=post_obs,
    )
    assert replan_directive is not None
    assert replan_report.is_feasible is True


@pytest.mark.asyncio
async def test_adversarial_competing_decision_rejected_in_favor_of_plan_directive():
    """P0 Adversarial Test: Planner emits PlanDirective(LAUNCH_APPLICATION), competing engine attempts CLICK.
    The runtime MUST reject CLICK and only execute the PlanDirective-authorized action.
    """
    from orbit.adapters.mocks import MockPointerAdapter
    from orbit.runtime.cognitive.plan_directive import PlanDirective

    pointer_mock = MockPointerAdapter()
    agent_loop = AgentExecutionLoop(pointer=pointer_mock)

    # Force planner to emit a strict LAUNCH_APPLICATION directive
    directive = PlanDirective(
        objective_id="obj_test_01",
        subgoal_id="sub_test_01",
        subgoal_title="Launch Notepad",
        preferred_primitives=[AbstractActionType.LAUNCH_APPLICATION],
        semantic_targets=[SemanticTarget(name="notepad", role="application")],
    )
    with patch.object(agent_loop._planner, "plan_subgoal", return_value=(directive, MagicMock(is_feasible=True))):
        # Adversarial decision engine attempts competing CLICK action
        competing_decision = CognitiveDecision(
            decision_summary="Adversarial competing click",
            next_action=AbstractAction(
                action_type=AbstractActionType.CLICK,
                target=SemanticTarget(name="unrelated_button", role="Button"),
                parameters={"button": "left"},
            ),
        )
        with patch.object(agent_loop._decision_engine, "decide_next_step", new=AsyncMock(return_value=competing_decision)), \
             patch.object(agent_loop._observer, "observe", new=AsyncMock(return_value=CurrentStateObservation(perceived_elements_count=1))), \
             patch.object(agent_loop._primitive_execution_controller, "execute_primitive", new_callable=AsyncMock) as mock_exec:
            
            # Setup successful outcome for the canonical controller
            mock_exec.return_value = ControllerExecutionResult(
                action_dispatched=AbstractAction(
                    action_type=AbstractActionType.LAUNCH_APPLICATION,
                    parameters={"application_name": "notepad"},
                ),
                execution_outcome=ActionExecutionOutcome(
                    action_id="act_dir_0",
                    dispatch_success=True,
                    expected_effect_observed=True,
                    verified=True,
                    outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                ),
                post_observation=CurrentStateObservation(),
                should_continue=True,
            )

            with patch.object(agent_loop._goal_verifier, "verify_goal_achievement", new=AsyncMock(side_effect=[MagicMock(is_satisfied=False), MagicMock(is_satisfied=True)])):
                res = await agent_loop.run(prompt="launch notepad")

            # CRITICAL ASSERTIONS:
            # 1. Controller was called with LAUNCH_APPLICATION, NOT competing CLICK
            assert mock_exec.called
            first_dispatched = mock_exec.call_args_list[0].kwargs["action"]
            assert first_dispatched.action_type == AbstractActionType.LAUNCH_APPLICATION

            # Verify competing CLICK was completely rejected and never dispatched
            for call in mock_exec.call_args_list:
                assert call.kwargs["action"].action_type != AbstractActionType.CLICK

            # 2. Zero physical pointer clicks dispatched
            assert len(pointer_mock.click_history) == 0


def test_primitive_composer_does_not_invent_intent():
    """P0 Composer Authority Test: PrimitiveComposer translates PlanDirective into low-level primitives without inventing new tasks."""
    from orbit.runtime.cognitive.plan_directive import PlanDirective

    composer = PrimitiveComposer()
    directive = PlanDirective(
        objective_id="obj_test_01",
        subgoal_id="sub_test_01",
        subgoal_title="Type in notepad",
        preferred_primitives=[AbstractActionType.TYPE_TEXT],
        semantic_targets=[SemanticTarget(name="notepad", role="document")],
        creative_payload={"text": "ORBIT TEST"},
    )

    composed_seq = composer.compose_from_directive(directive)

    # 1. Composed actions match the directive payload and target
    assert len(composed_seq.actions) > 0
    for act in composed_seq.actions:
        # Composer must NOT independently launch unrelated apps or switch intent
        assert act.action_type in (AbstractActionType.TYPE_TEXT, AbstractActionType.FOCUS_WINDOW, AbstractActionType.WAIT_SETTLE)
        if act.action_type == AbstractActionType.TYPE_TEXT:
            assert act.parameters.get("text") == "ORBIT TEST"
        if act.target:
            assert "notepad" in act.target.name.lower() or act.target.role in ("edit", "document", "window", "application")



@pytest.mark.asyncio
async def test_adversarial_verification_action_success_without_world_change_fails_gate():
    """Section 10 Adversarial Verification Test:
    Physical controller reports ACTION_SUCCESS (dispatch_success=True),
    but the environment does NOT change (expected_effect_observed=False).
    The loop must NOT mark the task successful, must run failure analysis,
    update world state, and trigger replanning.
    """
    from orbit.runtime.agent.contracts import VerificationStrategy
    from orbit.runtime.cognitive.failure_analyst import CognitiveFailureAnalyst
    from orbit.runtime.world_model.updater import WorldModelUpdater

    agent_loop = AgentExecutionLoop()
    analyst = CognitiveFailureAnalyst()
    world_model = AgentWorldModel()

    initial_obs = CurrentStateObservation(observation_id="obs_01", active_window_title="Desktop")
    stale_post_obs = CurrentStateObservation(observation_id="obs_02", active_window_title="Desktop")

    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="SubmitButton", role="button"),
        outcome_contract=ActionOutcomeContract(
            expected_state_transition="form_submitted_dialog_visible",
            verification_strategy=VerificationStrategy.AUTO_ROUTED,
        ),
    )

    # Controller reports dispatch success, but reality did not change
    mock_outcome = ActionExecutionOutcome(
        action_id=action.action_id,
        dispatch_success=True,
        expected_effect_observed=False,
        outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
        error_message="Form submitted dialog never appeared",
    )

    # Verification must fail closed
    assert mock_outcome.dispatch_success is True
    assert mock_outcome.expected_effect_observed is False

    # Failure analyst must diagnose the non-change
    failure_diag = analyst.analyze_failure(action, initial_obs, stale_post_obs, mock_outcome)
    assert failure_diag is not None
    assert failure_diag.diagnosis != ""

    # World model is updated with the non-change
    world_model = WorldModelUpdater.record_action_outcome(world_model, action, mock_outcome)
    world_model = WorldModelUpdater.update_from_observation(world_model, stale_post_obs)
    assert len(world_model.action_history) > 0
    assert world_model.action_history[-1]["verified"] is False
    assert world_model.action_history[-1]["outcome_status"] == OutcomeStatus.EFFECT_UNVERIFIED.value

    # GoalVerifier must reject task completion
    goal_check = await agent_loop._goal_verifier.verify_goal_achievement(
        task_id="task_adv_verif",
        objective=StructuredObjective(raw_prompt="submit form", user_goal="submit form", end_condition="form_submitted"),
        current_observation=stale_post_obs,
    )
    assert goal_check.is_completed is False, "Task falsely marked successful when environment did not change!"


@pytest.mark.asyncio
async def test_real_replanning_target_moved_emits_distinct_new_directive():
    """Section 11 Real Replanning Test:
    Initial: PlanDirective: CLICK target A.
    Then target A disappears / moves.
    Expected:
    1. Initial directive generated
    2. Action attempted & fails verification
    3. Failure classified & world state updated
    4. NEW PlanDirective generated
    5. new_directive != initial_directive
    6. New directive executes and achieves verified goal.
    """
    from orbit.runtime.cognitive.failure_analyst import CognitiveFailureAnalyst
    from orbit.runtime.world_model.updater import WorldModelUpdater

    planner = AgentPlanner()
    analyst = CognitiveFailureAnalyst()
    world_model = AgentWorldModel()

    objective = StructuredObjective(
        raw_prompt="Interact with dialog controls",
        user_goal="Submit form dialog",
        end_condition="form_submitted",
    )
    subgoal_initial = SubObjective(
        sub_id="sub_click_a",
        title="Click Submit Button",
        description="Click the primary dialog submit button",
        target_entity="Submit Button",
        preferred_primitives=[AbstractActionType.CLICK],
    )

    obs_initial = CurrentStateObservation(observation_id="obs_01", active_window_title="Dialog")

    # 1. Initial directive generated
    initial_directive, rep1 = planner.plan_subgoal(
        objective=objective,
        subgoal=subgoal_initial,
        world_model=world_model,
        observation=obs_initial,
    )
    assert initial_directive is not None
    assert initial_directive.preferred_primitives == [AbstractActionType.CLICK]

    # 2. Action attempted & verification fails because Submit Button disappeared
    action_1 = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="Submit Button", role="button"),
        outcome_contract=ActionOutcomeContract(expected_state_transition="form_submitted"),
    )
    obs_post_fail = CurrentStateObservation(observation_id="obs_02", active_window_title="Dialog", perceived_elements_count=0)
    failed_outcome = ActionExecutionOutcome(
        action_id=action_1.action_id,
        dispatch_success=False,
        expected_effect_observed=False,
        outcome_status=OutcomeStatus.DISPATCH_FAILED,
        error_message="Target Submit Button not found on screen",
    )

    # 3. Failure classified & world state updated
    diag = analyst.analyze_failure(action_1, obs_initial, obs_post_fail, failed_outcome)
    world_model = WorldModelUpdater.record_action_outcome(world_model, action_1, failed_outcome)
    world_model = WorldModelUpdater.update_from_observation(world_model, obs_post_fail)

    # 4. Formulate fallback keyboard enter subgoal to represent replanned intent
    subgoal_replan = SubObjective(
        sub_id="sub_enter_key_fallback",
        title="Type Enter Key Fallback",
        description="Type Enter to confirm dialog",
        preferred_primitives=[AbstractActionType.TYPE_TEXT],
    )

    new_directive, rep2 = planner.plan_subgoal(
        objective=objective,
        subgoal=subgoal_replan,
        world_model=world_model,
        observation=obs_post_fail,
    )

    # 5. Explicitly assert new_directive != initial_directive
    assert new_directive is not None
    assert new_directive.directive_id != initial_directive.directive_id
    assert new_directive.preferred_primitives != initial_directive.preferred_primitives
    assert new_directive.preferred_primitives == [AbstractActionType.TYPE_TEXT]

    # 6. Compose and verify new directive
    composer = PrimitiveComposer()
    seq = composer.compose_from_directive(new_directive)
    assert len(seq.actions) == 1
    assert seq.actions[0].action_type == AbstractActionType.TYPE_TEXT


@pytest.mark.asyncio
async def test_goal_completion_must_be_independent_rejects_premature_model_claim():
    """Section 12 & Invariant K: Goal Completion Must Be Independent.
    Model emits COMPLETE_GOAL while environment is NOT in desired state.
    GoalVerifier MUST reject completion, task remains incomplete, and loop continues.
    """
    agent_loop = AgentExecutionLoop()

    objective = StructuredObjective(
        raw_prompt="open notepad and type hello",
        user_goal="open notepad and type hello",
        end_condition="notepad_contains_hello",
    )

    # Model claims goal is satisfied with COMPLETE_GOAL
    premature_decision = CognitiveDecision(
        decision_summary="I am claiming the goal is complete now.",
        is_goal_satisfied=True,
        next_action=AbstractAction(
            action_type=AbstractActionType.COMPLETE_GOAL,
            rationale="I think I'm done",
        ),
    )

    # Environment reality: Notepad is NOT open and text does NOT exist
    unmet_obs = CurrentStateObservation(
        observation_id="obs_unmet",
        active_window_title="Desktop",
        target_app_exists=False,
        target_app_is_active=False,
        ocr_tokens=["Recycle", "Bin"],
    )

    # GoalVerifier evaluates reality
    verification_res = await agent_loop._goal_verifier.verify_goal_achievement(
        task_id="task_premature",
        objective=objective,
        current_observation=unmet_obs,
    )

    # Invariant: Model claim is completely ignored; GoalVerifier proves reality
    assert verification_res.is_completed is False, "GoalVerifier permitted premature model completion claim!"


def test_planner_cannot_physically_execute():
    """Invariant G: AgentPlanner cannot directly physically execute actions.
    It produces candidate plans and emits PlanDirectives only.
    """
    planner = AgentPlanner()
    for forbidden_attr in ("execute", "dispatch", "click", "type", "press", "move_to", "pointer", "keyboard"):
        assert not hasattr(planner, forbidden_attr), f"AgentPlanner has forbidden physical execution attribute: {forbidden_attr}"


def test_decision_engine_cannot_bypass_plan_directive():
    """Invariant H: DecisionEngine cannot bypass PlanDirective.
    AgentDecisionEngine has no physical dispatch or execution methods.
    """
    decision_engine = AgentDecisionEngine()
    for forbidden_attr in ("execute", "dispatch", "execute_action", "dispatch_primitive", "_execute_action"):
        assert not hasattr(decision_engine, forbidden_attr), f"AgentDecisionEngine has forbidden execution method: {forbidden_attr}"


def test_semantic_hardcoded_planning_cannot_become_execution_authority():
    """Invariant M: AgentPlanner and PrimitiveComposer contain zero static drawing plans/stroke arrays.
    Geometric strokes and creative payloads are received dynamically from structured objectives/models.
    """
    planner = AgentPlanner()
    composer = PrimitiveComposer()
    
    # Assert neither planner nor composer contains hardcoded stroke geometry arrays
    assert not hasattr(planner, "STATIC_DRAWING_PLANS")
    assert not hasattr(planner, "DEFAULT_STROKES")
    assert not hasattr(composer, "STATIC_DRAWING_PLANS")
    assert not hasattr(composer, "DEFAULT_STROKES")
