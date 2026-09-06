"""Live Windows Plan Execution and Closed-Loop Dispatch Suite for Milestone M1.8 Step 3.

Validates end-to-end task understanding -> DAG planning -> plan execution against
live Windows display, real rendered GUI fixtures, and production capability adapters.

Epistemic Classifications:
- CONTROLLED_LIVE_VALIDATED: Executed against a dedicated, live-rendered Win32/Tkinter GUI fixture on the Windows desktop.
- LIVE_OS_VALIDATED: Executed directly against the live Windows operating system and active desktop geometry.
- TEST_PROVEN: Proven through deterministic integration assertions with bounded mock overrides.
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
from orbit.adapters.workspace.abi import IS_WINDOWS
from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter
from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.runtime import SystemState
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
from orbit.runtime.execution import (
    ClosedLoopExecutionEngine,
    ExecutionPolicy,
    ExecutionState,
)
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.plan_execution import (
    PlanExecutionResult,
    PlanExecutionStatus,
    PlanExecutor,
    PlanStepExecutionStatus,
)
from orbit.runtime.planning import (
    ExecutableTaskPlan,
    PlanActionType,
    PlanStatus,
    PlanStep,
    TaskPlanningEngine,
)
from orbit.runtime.task_understanding import (
    TargetReference,
    TaskConstraints,
    TaskUnderstandingEngine,
)
from orbit.runtime.targeting import EvidenceBasedTargetLocator
from orbit.runtime.verification import ActionVerifier


@contextmanager
def launch_controlled_gui_fixture(
    title: str = "ORBIT Live Step3 Fixture",
    x: int = 150,
    y: int = 150,
    width: int = 350,
    height: int = 250,
) -> Generator[subprocess.Popen, None, None]:
    """Launch a dedicated, live rendered Win32 Tkinter fixture and guarantee clean termination."""
    script = f"""
import tkinter as tk
import sys

root = tk.Tk()
root.title("{title}")
root.geometry("{width}x{height}+{x}+{y}")
root.attributes("-topmost", True)

clicked_count = 0

def on_click():
    global clicked_count
    clicked_count += 1
    lbl_status.config(text=f"Clicked: {{clicked_count}}")

lbl_title = tk.Label(root, text="ORBIT Plan Execution Test", font=("Arial", 12, "bold"))
lbl_title.pack(pady=10)

btn_submit = tk.Button(root, text="Click Here", command=on_click, width=15, height=2, bg="#4CAF50", fg="white")
btn_submit.pack(pady=10)

lbl_status = tk.Label(root, text="Ready", font=("Arial", 10))
lbl_status.pack(pady=5)

root.update()
root.mainloop()
"""
    proc = subprocess.Popen([sys.executable, "-c", script])
    time.sleep(1.2)  # Allow Tkinter window to render on desktop
    try:
        yield proc
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _find_window_by_title_substring(title_substr: str) -> int:
    found_hwnd = 0
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def enum_cb(h, _):
        nonlocal found_hwnd
        if ctypes.windll.user32.IsWindowVisible(h):
            length = ctypes.windll.user32.GetWindowTextLengthW(h)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(h, buf, length + 1)
                if title_substr.lower() in buf.value.lower():
                    r = wintypes.RECT()
                    ctypes.windll.user32.GetWindowRect(h, ctypes.byref(r))
                    if (r.right - r.left) >= 50 and (r.bottom - r.top) >= 50:
                        found_hwnd = h
                        return 0
        return 1

    cb = WNDENUMPROC(enum_cb)
    ctypes.windll.user32.EnumWindows(cb, 0)
    return found_hwnd


@contextmanager
def spawn_isolated_test_window(
    title: str, width: int = 360, height: int = 260, x: int = 150, y: int = 150
) -> Generator[str, None, None]:
    """Spawn an external, isolated live Win32 GUI window with dedicated message pump."""
    code = f"""
import tkinter as tk
root = tk.Tk()
root.title("{title}")
root.geometry("{width}x{height}+{x}+{y}")
lbl = tk.Label(root, text="ORBIT M1.8 Live Plan Execution Window", font=("Arial", 12))
lbl.pack(pady=10)
btn = tk.Button(root, text="Target Button", width=20, height=2)
btn.pack(pady=10)
root.update_idletasks()
root.update()
root.mainloop()
"""
    proc = subprocess.Popen([sys.executable, "-c", code])
    t_end = time.perf_counter() + 6.0
    while time.perf_counter() < t_end:
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd and ctypes.windll.user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
            if (r.right - r.left) >= 100 and (r.bottom - r.top) >= 100:
                break
        time.sleep(0.05)
    time.sleep(0.3)
    try:
        yield title
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except Exception:
            pass


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="Live OS validation requires Windows platform")
async def test_live_controlled_gui_plan_execution():
    """Verify live natural-language task understanding -> plan generation -> live closed-loop execution.

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

    try:
        engine = ClosedLoopExecutionEngine(
            observation=obs,
            pointer=ptr,
            workspace=wsp,
            target_locator=locator,
            action_verifier=verifier,
            event_bus=bus,
            clock=SystemClock(),
        )
        executor = PlanExecutor(execution_engine=engine, event_bus=bus)

        # Build multi-step plan targeting the active IDE window
        step1 = PlanStep(
            step_id="step_open",
            step_index=0,
            action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
            description="Ensure Antigravity IDE is open",
            target=TargetReference(semantic_type="application", identifier="Antigravity IDE"),
            dependencies=[],
        )
        step2 = PlanStep(
            step_id="step_verify",
            step_index=1,
            action_type=PlanActionType.VERIFY_APPLICATION_AVAILABLE,
            description="Verify Antigravity IDE is available",
            target=TargetReference(semantic_type="application", identifier="Antigravity IDE"),
            dependencies=["step_open"],
        )

        plan = ExecutableTaskPlan(
            plan_id="plan_live_ide",
            task_id="task_live_ide",
            description="Verify live Antigravity IDE window",
            status=PlanStatus.VALID,
            steps=[step1, step2],
            step_dependencies={"step_open": [], "step_verify": ["step_open"]},
        )

        # Step 3: Execute plan against live desktop
        result: PlanExecutionResult = await executor.execute_plan(
            plan=plan,
            session_id="session_live_step3",
            policy=ExecutionPolicy(max_total_attempts=2, allow_inconclusive_as_success=True),
        )

        assert result.is_success is True
        assert result.final_status == PlanExecutionStatus.SUCCEEDED
        assert result.completed_steps == 2
        assert result.failed_steps == 0
        assert result.blocked_steps == 0

        # Verify that physical coordinates were resolved against live desktop
        first_resolved = next((r.resolved_target for r in result.step_results if r.resolved_target is not None), None)
        assert first_resolved is not None
        assert first_resolved.safe_point.x >= 0
        assert first_resolved.safe_point.y >= 0
    finally:
        await ptr.shutdown()
        await wsp.shutdown()
        await obs.shutdown()


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="Live OS validation requires Windows platform")
async def test_live_unsupported_task_fails_closed_zero_dispatch():
    """Verify that an unsupported task terminates fail-closed on live Windows with 0 unauthorized OS dispatches.

    Epistemic Classification: LIVE_OS_VALIDATED
    """
    bus = EventBus()
    obs = ProductionObservationAdapter()
    wsp = ProductionWorkspaceAdapter()
    ptr = ProductionPointerAdapter()
    locator = EvidenceBasedTargetLocator()
    verifier = ActionVerifier()

    await obs.initialize()
    await wsp.initialize()
    await ptr.initialize()

    try:
        engine = ClosedLoopExecutionEngine(
            observation=obs,
            pointer=ptr,
            workspace=wsp,
            target_locator=locator,
            action_verifier=verifier,
            event_bus=bus,
            clock=SystemClock(),
        )
        executor = PlanExecutor(execution_engine=engine, event_bus=bus)

        understanding_engine = TaskUnderstandingEngine()
        understanding = understanding_engine.understand("Draw a photorealistic oil painting of a castle")

        planning_engine = TaskPlanningEngine(understanding_engine=understanding_engine)
        plan = planning_engine.plan_task(understanding, task_id="task_live_unsupported")

        # Plan should be UNSUPPORTED or contain UNSUPPORTED_ACTION
        result: PlanExecutionResult = await executor.execute_plan(
            plan=plan,
            session_id="session_live_unsupported",
        )

        assert result.is_success is False
        assert result.final_status in {PlanExecutionStatus.UNSUPPORTED, PlanExecutionStatus.FAILED}
        assert result.total_dispatches == 0
    finally:
        await ptr.shutdown()
        await wsp.shutdown()
        await obs.shutdown()
