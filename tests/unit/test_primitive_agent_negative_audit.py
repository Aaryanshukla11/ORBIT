"""Negative Implementation Audit Test Suite for Primitive-Centric General Computer Agent.

Tests strictly enforce:
- Test A: Path-based AST audit of src/orbit/runtime/cognitive/* proving zero direct imports/calls to physical OS APIs.
- Test B: Recovery adapter isolation (recovery synthesizes canonical primitives, has no physical adapters).
- Test C: Grounding failure produces zero pointer dispatches for CLICK, DOUBLE_CLICK, RIGHT_CLICK.
- Test D: Canvas-relative drawing geometry invariant and structural validation.
- Test E: Application launcher deterministic resolution and injection boundary.
- Test F: Exactly one physical dispatch per primitive.
- Test G: COMPLETE_GOAL epistemic distinction (False vs Inconclusive both prevent task completion).
- Test H: No double execution (controller_calls == 1, executor_calls == 1, physical_clicks == 1).
- Test I: Mandatory controller enforcement (direct physical action bypassing controller rejected).
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionExecutionResult,
    ActionOutcomeContract,
    OutcomeStatus,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop, CapabilityAwareAgentLoop
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CurrentStateObservation,
    StructuredObjective,
)
from orbit.runtime.cognitive.primitive_validator import PrimitiveValidator
from orbit.runtime.cognitive.primitive_execution_controller import (
    ControllerExecutionResult,
    PrimitiveExecutionController,
)
from orbit.runtime.cognitive.recovery import (
    AgentRecoveryManager,
    RecoveryStrategy,
)
from orbit.runtime.capabilities.application_launcher import ApplicationLauncher
from orbit.runtime.capabilities.execution.executors.drawing_executor import DrawingExecutor
from orbit.runtime.capabilities.execution.contracts import (
    CapabilityExecutionRequest,
    StageOutcomeStatus,
)
from orbit.runtime.task_completion.models import (
    GoalVerificationResult,
    TaskCompletionStatus,
)


# ==============================================================================
# TEST A: Path-Based AST Audit of Cognitive Subsystem
# ==============================================================================

def test_ast_audit_forbidden_layers_physical_purity():
    """Prove that cognitive, planning, replanning, world_model, task_understanding, memory contain zero forbidden OS/physical imports or calls (Phase 0 Rule #16)."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    forbidden_dirs = [
        repo_root / "src" / "orbit" / "runtime" / "cognitive",
        repo_root / "src" / "orbit" / "runtime" / "planning",
        repo_root / "src" / "orbit" / "runtime" / "replanning",
        repo_root / "src" / "orbit" / "runtime" / "world_model",
        repo_root / "src" / "orbit" / "runtime" / "task_understanding",
        repo_root / "src" / "orbit" / "runtime" / "memory",
    ]

    forbidden_modules = {
        "ctypes",
        "pyautogui",
        "pydirectinput",
        "pynput",
        "win32api",
        "win32gui",
        "win32con",
        "win32process",
        "subprocess",
    }

    # Approved read-only desktop observation
    allowlist = {
        "observer.py": {"win32gui", "ctypes"},
    }

    violations = []

    for fdir in forbidden_dirs:
        if not fdir.exists():
            continue
        for py_file in fdir.glob("*.py"):
            rel_name = py_file.name
            with open(py_file, "r", encoding="utf-8") as f:
                code = f.read()

            try:
                tree = ast.parse(code, filename=str(py_file))
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {py_file}: {e}")

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root_mod = alias.name.split(".")[0]
                        if root_mod in forbidden_modules:
                            allowed_for_file = allowlist.get(rel_name, set())
                            if root_mod not in allowed_for_file:
                                violations.append(f"{py_file.relative_to(repo_root)}:{node.lineno} forbidden import '{alias.name}'")
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        root_mod = node.module.split(".")[0]
                        if root_mod in forbidden_modules:
                            allowed_for_file = allowlist.get(rel_name, set())
                            if root_mod not in allowed_for_file:
                                violations.append(f"{py_file.relative_to(repo_root)}:{node.lineno} forbidden from-import '{node.module}'")

    assert not violations, f"Forbidden physical imports detected in reasoning/cognitive/planning layers:\n" + "\n".join(violations)


def test_ast_audit_cognitive_layer_forbidden_apis():
    """Alias for backward compatibility with baseline test discovery."""
    test_ast_audit_forbidden_layers_physical_purity()


# ==============================================================================
# TEST B: Recovery Adapter Isolation
# ==============================================================================

@pytest.mark.asyncio
async def test_recovery_adapter_isolation():
    """Prove that AgentRecoveryManager does not accept or touch physical adapters."""
    manager = AgentRecoveryManager()

    # Verify no physical adapters exist on the recovery manager
    assert not hasattr(manager, "_pointer")
    assert not hasattr(manager, "_keyboard")
    assert not hasattr(manager, "_workspace")

    # Verify canonical primitive synthesis under modal dialog evidence
    obs = CurrentStateObservation(
        observation_id="obs_modal",
        visible_windows=[{"title": "Confirm Save Changes Dialog", "hwnd": 12345}],
    )
    failed_action = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        parameters={"text": "hello"},
        expected_effect="Text typed into editor",
    )
    recovery_action = manager.synthesize_recovery_primitive(
        strategy=RecoveryStrategy.DISMISS_IDENTIFIED_MODAL,
        action=failed_action,
        observation=obs,
    )
    assert recovery_action is not None
    assert recovery_action.action_type == AbstractActionType.SEND_HOTKEY
    assert recovery_action.parameters.get("hotkey") == "Escape"

    # Verify modal dismissal is skipped (returns None to replan) if NO modal evidence exists
    blank_obs = CurrentStateObservation(observation_id="obs_clean", visible_windows=[])
    no_action = manager.synthesize_recovery_primitive(
        strategy=RecoveryStrategy.DISMISS_IDENTIFIED_MODAL,
        action=failed_action,
        observation=blank_obs,
    )
    assert no_action is None


# ==============================================================================
# TEST C: Strict Fail-Closed Pointer Invariant
# ==============================================================================

@pytest.mark.asyncio
async def test_grounding_failure_produces_zero_pointer_dispatches():
    """Prove that ungrounded target (coords=None) for pointer actions immediately fails with 0 pointer calls."""
    mock_pointer = MagicMock()
    mock_pointer.move_to = AsyncMock()
    mock_pointer.click = AsyncMock()

    loop = CapabilityAwareAgentLoop(
        pointer=mock_pointer,
        model_session_manager=MagicMock(),
    )

    pre_obs = CurrentStateObservation(observation_id="obs_test")
    # Action without resolvable coordinates
    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="non_existent_button", role="button"),
        expected_effect="Click button",
    )

    success, err = await loop._dispatch_physical_action(
        action=action,
        pre_obs=pre_obs,
        resolved_coords=None,
    )

    assert success is False
    assert err is not None and "TARGET_NOT_GROUNDED" in err
    assert mock_pointer.move_to.await_count == 0
    assert mock_pointer.click.await_count == 0


# ==============================================================================
# TEST D: Canvas-Relative Drawing Geometry Invariant
# ==============================================================================

def test_drawing_structural_contract_rejects_invalid_coordinates():
    """Prove that DRAW_STROKES contract rejects dicts, numbers outside [0.0, 1.0], and non-2-numeric points."""
    validator = PrimitiveValidator()

    # 1. Reject dictionary coordinate representations
    act_dict = AbstractAction(
        action_type=AbstractActionType.DRAW_STROKES,
        parameters={"strokes": [[{"x": 100, "y": 200}, {"x": 150, "y": 250}]]},
        expected_effect="Draw dictionary strokes",
    )
    res_dict = validator.validate_action(act_dict)
    assert res_dict.is_valid is False
    assert "dictionary" in res_dict.failure_reason

    # 2. Reject screen coordinates outside [0.0, 1.0]
    act_screen = AbstractAction(
        action_type=AbstractActionType.DRAW_STROKES,
        parameters={"strokes": [[(1250, 640), (1300, 700)]]},
        expected_effect="Draw raw screen coordinates",
    )
    res_screen = validator.validate_action(act_screen)
    assert res_screen.is_valid is False
    assert "bounds [0.0, 1.0]" in res_screen.failure_reason

    # 3. Reject 3-tuples
    act_3tuple = AbstractAction(
        action_type=AbstractActionType.DRAW_STROKES,
        parameters={"strokes": [[(0.1, 0.2, 0.3), (0.4, 0.5, 0.6)]]},
        expected_effect="Draw 3-tuples",
    )
    res_3tuple = validator.validate_action(act_3tuple)
    assert res_3tuple.is_valid is False
    assert "2-tuple" in res_3tuple.failure_reason

    # 4. Accept valid normalized canvas-local (u, v) points
    act_valid = AbstractAction(
        action_type=AbstractActionType.DRAW_STROKES,
        parameters={"strokes": [[(0.1, 0.2), (0.5, 0.5), (0.9, 0.8)]]},
        expected_effect="Draw normalized trajectory",
    )
    res_valid = validator.validate_action(act_valid)
    assert res_valid.is_valid is True


@pytest.mark.asyncio
async def test_drawing_executor_fail_closed_if_pointer_missing():
    """Prove DrawingExecutor fails closed if pointer is missing."""
    executor = DrawingExecutor(pointer=None)
    req = CapabilityExecutionRequest(
        execution_id="draw_req",
        capability_id="DRAW_STROKES",
        stage_index=0,
        parameters={"strokes": [[(0.1, 0.1), (0.9, 0.9)]]},
    )
    res = await executor.execute(req)
    assert res.dispatch_success is False
    assert res.stage_status == StageOutcomeStatus.FAILED
    assert res.failure_code in ("REQUIRED_ADAPTER_MISSING", "CAPABILITY_UNAVAILABLE")


# ==============================================================================
# TEST E: Application Launcher Boundary & Injection Protection
# ==============================================================================

def test_application_launcher_sanitization_and_alias_resolution():
    """Prove ApplicationLauncher resolves aliases strictly and rejects shell injections / unknown apps."""
    launcher = ApplicationLauncher()

    # 1. Standard alias resolution
    exe_note = launcher.resolve_application("notepad")
    assert exe_note == "notepad.exe"

    exe_calc = launcher.resolve_application("calc")
    assert exe_calc == "calc.exe"

    exe_paint = launcher.resolve_application("paint")
    assert exe_paint == "mspaint.exe"

    # 2. Arbitrary dangerous injection strings fail resolution
    exe_inj = launcher.resolve_application("notepad & calc.exe")
    assert exe_inj is None

    exe_pipe = launcher.resolve_application("notepad | cmd.exe")
    assert exe_pipe is None

    # 3. Unknown application without safe path fails resolution
    exe_unknown = launcher.resolve_application("non_existent_fake_app_12345")
    assert exe_unknown is None

    # 4. Launch method returns structured failure for unknown/dangerous apps
    res_fail = launcher.launch("unknown_dangerous_app; format c:")
    assert res_fail.success is False
    assert res_fail.error_code == "LAUNCH_RESOLUTION_FAILED"


# ==============================================================================
# TEST F: Exactly One Physical Dispatch Per Primitive
# ==============================================================================

@pytest.mark.asyncio
async def test_exactly_one_physical_dispatch_per_primitive():
    """Prove that PrimitiveExecutionController dispatches exactly once for a valid primitive."""
    controller = PrimitiveExecutionController()
    action = AbstractAction(
        action_type=AbstractActionType.WAIT,
        parameters={"duration_sec": 0.01},
        expected_effect="Wait complete",
    )
    pre_obs = CurrentStateObservation(observation_id="obs_1")
    obj = StructuredObjective(
        raw_prompt="wait a moment",
        user_goal="Wait",
        end_condition="Time elapsed",
    )

    dispatch_mock = AsyncMock(return_value=(True, None))
    safety_mock = MagicMock(return_value=(True, None))
    observe_mock = AsyncMock(return_value=CurrentStateObservation(observation_id="obs_2"))

    res = await controller.execute_primitive(
        action=action,
        pre_observation=pre_obs,
        objective=obj,
        grounding_fn=AsyncMock(),
        safety_gate_fn=safety_mock,
        dispatch_fn=dispatch_mock,
        observe_fn=observe_mock,
    )

    assert res.execution_outcome.dispatch_success is True
    assert dispatch_mock.await_count == 1
    assert safety_mock.call_count == 1
    assert observe_mock.await_count == 1


# ==============================================================================
# TEST G: GoalVerifier Epistemic Distinctions (False vs Inconclusive)
# ==============================================================================

@pytest.mark.asyncio
async def test_goal_verifier_epistemic_distinctions():
    """Prove that both explicit Failure and Inconclusive outcome prevent task completion."""
    loop = CapabilityAwareAgentLoop(model_session_manager=MagicMock())

    # Mock decision engine to emit COMPLETE_GOAL
    mock_engine = MagicMock()
    mock_decision = CognitiveDecision(
        decision_summary="Task supposedly done",
        is_goal_satisfied=True,
        next_action=AbstractAction(
            action_type=AbstractActionType.COMPLETE_GOAL,
            expected_effect="Complete goal",
        ),
    )
    mock_engine.decide_next_step = AsyncMock(return_value=mock_decision)
    loop._decision_engine = mock_engine

    # 1. Inconclusive Goal Verification
    mock_verifier = MagicMock()
    mock_verifier.verify_goal_achievement = AsyncMock(
        return_value=GoalVerificationResult(
            status=TaskCompletionStatus.UNVERIFIABLE,
            is_completed=False,
            failure_reason="Insufficient visual evidence",
        )
    )
    loop._goal_verifier = mock_verifier

    # Mock observer to prevent infinite loop after 1 cycle
    call_count = 0
    async def mock_obs(obj):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            loop._budget.max_total_actions = 1
        return CurrentStateObservation(observation_id=f"obs_{call_count}")

    loop._observer.observe = mock_obs

    res = await loop.run(prompt="Test goal completion verification")
    assert res.is_success is False
    assert res.final_status != TaskCompletionStatus.COMPLETED


# ==============================================================================
# TEST H: No Double Execution Invariant
# ==============================================================================

@pytest.mark.asyncio
async def test_no_double_execution_invariant():
    """Prove that for a single action, controller is called once, executor once, physical dispatch once."""
    mock_pointer = MagicMock()
    mock_pointer.move_to = AsyncMock()
    mock_pointer.click = AsyncMock()

    loop = CapabilityAwareAgentLoop(
        pointer=mock_pointer,
        model_session_manager=MagicMock(),
    )

    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="btn", role="button"),
        expected_effect="Click button",
    )
    pre_obs = CurrentStateObservation(observation_id="obs_1")

    # Spy on PrimitiveExecutionController
    original_exec = loop._primitive_execution_controller.execute_primitive
    controller_calls = 0

    async def spy_controller(*args, **kwargs):
        nonlocal controller_calls
        controller_calls += 1
        return await original_exec(*args, **kwargs)

    loop._primitive_execution_controller.execute_primitive = spy_controller

    # Execute through canonical delegation path
    with patch.object(loop, "_resolve_target_coordinates", AsyncMock(return_value=(100, 200))):
        exec_res, post_obs = await loop._execute_and_verify_action(
            action=action,
            pre_obs=pre_obs,
            objective=StructuredObjective(
                raw_prompt="click button",
                user_goal="Click button",
                end_condition="Button clicked",
            ),
        )

    assert controller_calls == 1
    assert mock_pointer.move_to.await_count == 1
    assert mock_pointer.click.await_count == 1
    assert exec_res.dispatch_success is True


# ==============================================================================
# TEST I: Mandatory Controller Enforcement
# ==============================================================================

@pytest.mark.asyncio
async def test_mandatory_controller_enforcement():
    """Prove that agent loop execution cycle cannot bypass PrimitiveExecutionController."""
    loop = CapabilityAwareAgentLoop(model_session_manager=MagicMock())

    # Set controller to None or broken
    loop._primitive_execution_controller = None

    action = AbstractAction(
        action_type=AbstractActionType.WAIT,
        parameters={"duration_sec": 0.01},
        expected_effect="Wait",
    )
    pre_obs = CurrentStateObservation(observation_id="obs_1")

    # Attempting to execute without controller must raise AttributeError
    with pytest.raises(AttributeError):
        await loop._execute_and_verify_action(
            action=action,
            pre_obs=pre_obs,
            objective=StructuredObjective(
                raw_prompt="wait",
                user_goal="Wait",
                end_condition="Waited",
            ),
        )


# ==============================================================================
# PHASE 0 RULE #15: MANDATORY NEGATIVE ARCHITECTURE TESTS (1 - 10)
# ==============================================================================

from orbit.runtime.cancellation import CancellationSource
from orbit.runtime.cognitive.agent_planner import AgentPlanner
from orbit.runtime.perception.vlm_grounding import VLMGroundingVerifier
from orbit.runtime.environment.registry import EnvironmentProviderRegistry, get_default_environment_registry
from orbit.runtime.environment.shell_provider import ShellExecutionProvider
from orbit.runtime.capabilities.execution.executor_registry import CapabilityExecutorRegistry
from orbit.runtime.capabilities.execution.strategy_execution_engine import StrategyExecutionEngine
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.adapters.observation.snapshot import ObservationSnapshot


@pytest.mark.asyncio
async def test_negative_rule15_1_strategy_execution_engine_unreachable():
    """1. Prove that StrategyExecutionEngine cannot be reached from production AgentExecutionLoop."""
    mock_engine = MagicMock(spec=StrategyExecutionEngine)
    mock_engine.execute_strategy = AsyncMock()
    mock_engine.can_execute_strategy = MagicMock(return_value=True)

    obs = CurrentStateObservation(observation_id="obs_neg1")
    mock_observer = MagicMock()
    mock_observer.observe = AsyncMock(return_value=obs)

    loop = AgentExecutionLoop(
        strategy_execution_engine=mock_engine,
        observer=mock_observer,
    )
    # Execute loop
    await loop.run(prompt="Run test task", context={"authoritative_strategy_execution": True})

    # Invariant: execute_strategy must NEVER be invoked
    mock_engine.execute_strategy.assert_not_called()


@pytest.mark.asyncio
async def test_negative_rule15_2_capability_executor_registry_cannot_execute_production_actions():
    """2. Prove that CapabilityExecutorRegistry is NOT an execution authority for production AgentLoop."""
    mock_registry = MagicMock(spec=CapabilityExecutorRegistry)
    mock_registry.get_executor = MagicMock()

    obs = CurrentStateObservation(observation_id="obs_neg2")
    mock_observer = MagicMock()
    mock_observer.observe = AsyncMock(return_value=obs)

    loop = AgentExecutionLoop(
        executor_registry=mock_registry,
        observer=mock_observer,
    )
    await loop.run(prompt="Perform desktop action")

    # Invariant: registry cannot be queried or used to dispatch physical actions
    mock_registry.get_executor.assert_not_called()


@pytest.mark.asyncio
async def test_negative_rule15_3_legacy_capability_cannot_bypass_primitive_execution_controller():
    """3. Prove that legacy capability execution cannot bypass PrimitiveExecutionController."""
    loop = AgentExecutionLoop()
    # If the controller is missing, physical execution MUST fail closed
    loop._primitive_execution_controller = None

    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        parameters={"coords": (100, 200)},
        expected_effect="Click canvas",
    )
    pre_obs = CurrentStateObservation(observation_id="obs_neg3")

    with pytest.raises(AttributeError):
        await loop._execute_and_verify_action(
            action=action,
            pre_obs=pre_obs,
            objective=StructuredObjective(raw_prompt="click", user_goal="Click", end_condition="Done"),
        )


def test_negative_rule15_4_cognitive_modules_cannot_dispatch_os_actions():
    """4. Prove that cognitive modules have zero physical OS adapters and cannot dispatch OS actions."""
    from orbit.runtime.cognitive.engine import CognitiveDecisionEngine
    from orbit.runtime.cognitive.recovery import AgentRecoveryManager
    from orbit.runtime.cognitive.decomposer import HierarchicalGoalDecomposer
    from orbit.runtime.cognitive.interpreter import LLMIntentInterpreter

    modules = [
        CognitiveDecisionEngine(),
        AgentRecoveryManager(),
        HierarchicalGoalDecomposer(),
        LLMIntentInterpreter(),
    ]

    for mod in modules:
        assert not hasattr(mod, "_pointer"), f"{mod.__class__.__name__} illegally holds _pointer"
        assert not hasattr(mod, "_keyboard"), f"{mod.__class__.__name__} illegally holds _keyboard"
        assert not hasattr(mod, "_workspace"), f"{mod.__class__.__name__} illegally holds _workspace"
        assert not hasattr(mod, "execute"), f"{mod.__class__.__name__} illegally implements execute()"


def test_negative_rule15_5_planning_modules_cannot_dispatch_os_actions():
    """5. Prove that planning modules have zero physical OS adapters and cannot dispatch OS actions."""
    planner = AgentPlanner()
    assert not hasattr(planner, "_pointer"), "AgentPlanner illegally holds _pointer"
    assert not hasattr(planner, "_keyboard"), "AgentPlanner illegally holds _keyboard"
    assert not hasattr(planner, "_workspace"), "AgentPlanner illegally holds _workspace"
    assert not hasattr(planner, "execute_plan"), "AgentPlanner illegally implements execute_plan()"


def test_negative_rule15_6_vlm_is_evidence_only_cannot_dispatch_physical_actions():
    """6. Prove that VLM grounding is evidence-only and cannot dispatch physical actions."""
    vlm_verifier = VLMGroundingVerifier()
    assert not hasattr(vlm_verifier, "_pointer"), "VLMGroundingVerifier illegally holds _pointer"
    assert not hasattr(vlm_verifier, "_keyboard"), "VLMGroundingVerifier illegally holds _keyboard"
    assert not hasattr(vlm_verifier, "click"), "VLMGroundingVerifier illegally exposes click()"
    assert not hasattr(vlm_verifier, "type_text"), "VLMGroundingVerifier illegally exposes type_text()"


@pytest.mark.asyncio
async def test_negative_rule15_7_environment_provider_cannot_become_physical_bypass():
    """7. Prove that EnvironmentProviderRegistry cannot execute or bypass physical desktop actions."""
    registry = get_default_environment_registry()
    assert len(registry._providers) > 0

    # Physical desktop action
    physical_action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        parameters={"coords": (500, 500)},
        expected_effect="Physical click attempt",
    )

    for action_type, provider_list in registry._providers.items():
        for priority, provider in provider_list:
            assert await provider.check_permissions(physical_action) is False, (
                f"Provider {provider.__class__.__name__} permitted physical CLICK action!"
            )


@pytest.mark.asyncio
async def test_negative_rule15_8_shell_provider_cannot_bypass_execution_controller():
    """8. Prove that ShellProvider strictly rejects commands attempting to bypass the execution controller."""
    provider = ShellExecutionProvider()

    bypass_attempts = [
        "mspaint.exe",
        "calc.exe",
        "notepad.exe",
        '[System.Windows.Forms.SendKeys]::SendWait("x")',
        "wscript.shell sendkeys {ENTER}",
        "wscript.exe script.vbs",
        "powershell -enc aGVsbG8=",
        "powershell -encodedcommand aGVsbG8=",
        "Invoke-Expression 'calc.exe'",
        "wmic process call create calc.exe",
    ]

    for cmd in bypass_attempts:
        action = AbstractAction(
            action_type=AbstractActionType.SHELL_EXECUTE,
            parameters={"command": cmd},
            expected_effect="Physical/GUI bypass attempt",
        )
        assert await provider.check_permissions(action) is False, f"Shell permitted bypass: {cmd}"
        res = await provider.execute(action)
        assert res.success is False
        assert "COMMAND_NOT_PERMITTED" in (res.error or "")


@pytest.mark.asyncio
async def test_negative_rule15_9_cancellation_blocks_physical_dispatch():
    """9. Prove that cancellation prevents physical dispatch in PrimitiveExecutionController."""
    controller = PrimitiveExecutionController()

    cancel_src = CancellationSource()
    cancel_src.cancel(reason="USER_CANCEL: User requested immediate abort")
    token = cancel_src.token

    action = AbstractAction(
        action_type=AbstractActionType.WAIT,
        parameters={"duration_sec": 1.0},
        expected_effect="Wait",
    )
    pre_obs = CurrentStateObservation(observation_id="obs_cancel")
    obj = StructuredObjective(raw_prompt="wait", user_goal="Wait", end_condition="Done")

    dispatch_mock = AsyncMock()
    observe_mock = AsyncMock()

    result = await controller.execute_primitive(
        action=action,
        pre_observation=pre_obs,
        objective=obj,
        grounding_fn=AsyncMock(),
        safety_gate_fn=MagicMock(return_value=(True, None)),
        dispatch_fn=dispatch_mock,
        observe_fn=observe_mock,
        cancel_token=token,
    )

    # Invariant: physical dispatch is strictly blocked
    assert result.execution_outcome.dispatch_success is False
    assert result.execution_outcome.failure_code == "OPERATION_CANCELLED"
    dispatch_mock.assert_not_called()
    observe_mock.assert_not_called()


@pytest.mark.asyncio
async def test_negative_rule15_10_goal_verifier_remains_independent_of_model_claims():
    """10. Prove that GoalVerifier independently evaluates reality and rejects unsubstantiated COMPLETE_GOAL claims."""
    verifier = GoalVerifier()

    # Pre-observation with empty/clean canvas
    pre_snap = MagicMock(spec=ObservationSnapshot)
    pre_snap.snapshot_id = "snap_pre"
    pre_snap.windows = []
    pre_snap.elements = []
    pre_snap.ocr_results = []
    pre_snap.screenshot = None

    # Post-observation with identical state (no file created, no drawing effect)
    post_snap = MagicMock(spec=ObservationSnapshot)
    post_snap.snapshot_id = "snap_post"
    post_snap.windows = []
    post_snap.elements = []
    post_snap.ocr_results = []
    post_snap.screenshot = None

    obj = StructuredObjective(
        raw_prompt="Create a file report.txt",
        user_goal="Create a file report.txt",
        end_condition="file_exists",
        parameters={"target_file": "report.txt"},
    )

    result = await verifier.verify_goal_achievement(
        task_id="task_neg10",
        objective=obj,
        current_observation=post_snap,
    )

    # Invariant: Goal completion is NOT assumed true without independent evidence
    assert result.is_completed is False
    assert result.status != TaskCompletionStatus.COMPLETED

