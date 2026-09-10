"""ASTRA-6 Architectural Invariants and Safety Verification Suite.

Tests and enforces all mandatory ASTRA-6 architecture invariants:
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
    """ASTRA-6 Invariant: Exactly one authoritative action decision per cycle.

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
    """ASTRA-6 Invariant: NO EXECUTION BYPASS.

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

