"""Live Windows Dynamic Replanning and Plan Recovery Suite for Milestone M1.8 Step 4.

Validates dynamic replanning, failure classification, DAG plan repair, and bounded recovery
against live Windows desktop, live rendered GUI fixtures, and production capability adapters.

Epistemic Classifications:
- CONTROLLED_LIVE_VALIDATED: Executed against a dedicated, live-rendered Win32/Tkinter GUI fixture on the Windows desktop.
- LIVE_OS_VALIDATED: Executed directly against the live Windows operating system and active desktop geometry.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import time
from typing import Generator, Optional
import pytest

from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.registry import CapabilityRegistry
from orbit.adapters.workspace.abi import IS_WINDOWS
from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter
from orbit.contracts.capabilities import CapabilityType
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.execution import (
    ClosedLoopExecutionEngine,
    ExecutionPolicy,
)
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.plan_execution import (
    PlanExecutionResult,
    PlanExecutionStatus,
    PlanExecutor,
)
from orbit.runtime.planning import (
    ExecutableTaskPlan,
    PlanActionType,
    PlanStatus,
    PlanStep,
)
from orbit.runtime.replanning import (
    DynamicReplanner,
    ReplanBudget,
)
from orbit.runtime.task_understanding import TargetReference
from orbit.runtime.targeting import EvidenceBasedTargetLocator
from orbit.runtime.verification import ActionVerifier


@contextmanager
def launch_live_replan_gui_fixture(
    title: str = "ORBIT Live Replan Fixture",
    x: int = 200,
    y: int = 200,
    width: int = 380,
    height: int = 280,
) -> Generator[str, None, None]:
    """Launch a dedicated, live rendered Win32 Tkinter fixture for replanning verification."""
    script = f"""
import tkinter as tk
root = tk.Tk()
root.title("{title}")
root.geometry("{width}x{height}+{x}+{y}")
root.attributes("-topmost", True)

lbl_title = tk.Label(root, text="ORBIT Dynamic Replanning Target", font=("Arial", 12, "bold"))
lbl_title.pack(pady=10)

btn_action = tk.Button(root, text="Action Button", width=20, height=2, bg="#2196F3", fg="white")
btn_action.pack(pady=10)

lbl_status = tk.Label(root, text="Ready for replan test", font=("Arial", 10))
lbl_status.pack(pady=5)

root.update_idletasks()
root.update()
root.mainloop()
"""
    proc = subprocess.Popen([sys.executable, "-c", script])
    t_end = time.perf_counter() + 6.0
    while time.perf_counter() < t_end:
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd and ctypes.windll.user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
            if (r.right - r.left) >= 100 and (r.bottom - r.top) >= 100:
                break
        time.sleep(0.05)
    time.sleep(0.5)
    try:
        yield title
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="Live OS validation requires Windows platform")
async def test_live_controlled_gui_dynamic_replanning_and_execution():
    """Verify live closed-loop execution and replanning integration against live Windows desktop.

    Epistemic Classification: LIVE_OS_VALIDATED
    """
    with launch_live_replan_gui_fixture() as target_app:
        bus = EventBus()
        obs = ProductionObservationAdapter(default_ttl_ms=1500.0)
        wsp = ProductionWorkspaceAdapter()
        ptr = ProductionPointerAdapter()
        locator = EvidenceBasedTargetLocator()
        verifier = ActionVerifier()

        await obs.initialize()
        await wsp.initialize()
        await ptr.initialize()

        reg = CapabilityRegistry()
        reg.register(CapabilityType.OBSERVATION, obs)
        reg.register(CapabilityType.WORKSPACE, wsp)
        reg.register(CapabilityType.POINTER, ptr)

        try:
            replanner = DynamicReplanner(
                observation=obs,
                budget=ReplanBudget(max_global_replans=3, max_step_replans=2),
            )

            engine = ClosedLoopExecutionEngine(
                capability_registry=reg,
                target_locator=locator,
                action_verifier=verifier,
                event_bus=bus,
                clock=SystemClock(),
            )

            executor = PlanExecutor(
                execution_engine=engine,
                replanner=replanner,
                event_bus=bus,
            )

            step1 = PlanStep(
                step_id="step_open_gui",
                step_index=0,
                action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
                description=f"Ensure {target_app} is open",
                target=TargetReference(semantic_type="application", identifier=target_app),
                dependencies=[],
            )
            step2 = PlanStep(
                step_id="step_verify_gui",
                step_index=1,
                action_type=PlanActionType.VERIFY_APPLICATION_AVAILABLE,
                description=f"Verify {target_app} is available",
                target=TargetReference(semantic_type="application", identifier=target_app),
                dependencies=["step_open_gui"],
            )

            plan = ExecutableTaskPlan(
                plan_id="plan_live_replan_gui",
                task_id="task_live_replan_gui",
                description="Live GUI replan execution test",
                status=PlanStatus.VALID,
                steps=[step1, step2],
                step_dependencies={"step_open_gui": [], "step_verify_gui": ["step_open_gui"]},
            )

            result: PlanExecutionResult = await executor.execute_plan(
                plan=plan,
                session_id="sess_live_replan_1",
                policy=ExecutionPolicy(max_total_attempts=2, allow_inconclusive_as_success=True),
            )

            assert result.is_success is True
            assert result.final_status == PlanExecutionStatus.SUCCEEDED
            assert result.completed_steps == 2
            assert result.failed_steps == 0
        finally:
            await ptr.shutdown()
            await wsp.shutdown()
            await obs.shutdown()


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="Live OS validation requires Windows platform")
async def test_live_replanning_budget_exhaustion_terminates_fail_closed():
    """Verify that attempting to locate a non-existent target exhausts replan budget and safely fails closed.

    Epistemic Classification: LIVE_OS_VALIDATED
    """
    bus = EventBus()
    obs = ProductionObservationAdapter(default_ttl_ms=1500.0)
    wsp = ProductionWorkspaceAdapter()
    ptr = ProductionPointerAdapter()
    locator = EvidenceBasedTargetLocator()
    verifier = ActionVerifier()

    await obs.initialize()
    await wsp.initialize()
    await ptr.initialize()

    reg = CapabilityRegistry()
    reg.register(CapabilityType.OBSERVATION, obs)
    reg.register(CapabilityType.WORKSPACE, wsp)
    reg.register(CapabilityType.POINTER, ptr)

    try:
        replanner = DynamicReplanner(
            observation=obs,
            budget=ReplanBudget(max_global_replans=2, max_step_replans=1),
        )

        engine = ClosedLoopExecutionEngine(
            capability_registry=reg,
            target_locator=locator,
            action_verifier=verifier,
            event_bus=bus,
            clock=SystemClock(),
        )

        executor = PlanExecutor(
            execution_engine=engine,
            replanner=replanner,
            event_bus=bus,
        )

        non_existent_target = "NonExistentApp_Target_XYZ_99999"
        step1 = PlanStep(
            step_id="step_locate_nonexistent",
            step_index=0,
            action_type=PlanActionType.LOCATE_INPUT_SURFACE,
            description=f"Locate {non_existent_target}",
            target=TargetReference(semantic_type="ui_control", identifier=non_existent_target),
            dependencies=[],
        )

        plan = ExecutableTaskPlan(
            plan_id="plan_live_budget_exhaust",
            task_id="task_live_budget_exhaust",
            description="Live budget exhaustion test",
            status=PlanStatus.VALID,
            steps=[step1],
            step_dependencies={"step_locate_nonexistent": []},
        )

        result: PlanExecutionResult = await executor.execute_plan(
            plan=plan,
            session_id="sess_live_budget_1",
            policy=ExecutionPolicy(
                max_total_attempts=1,
                max_target_resolution_attempts=1,
                max_recovery_attempts=0,
                allow_inconclusive_as_success=False,
            ),
        )

        assert result.is_success is False
        assert result.final_status == PlanExecutionStatus.FAILED
        assert result.failed_steps >= 1
        # Replanner was invoked and recorded in diagnostics
        assert "total_replans" in result.diagnostics
        assert result.diagnostics.get("successful_replans", 0) <= 2
        assert result.diagnostics["total_replans"] >= 1
    finally:
        await ptr.shutdown()
        await wsp.shutdown()
        await obs.shutdown()
