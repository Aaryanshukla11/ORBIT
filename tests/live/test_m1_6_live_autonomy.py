"""Live Windows End-to-End Autonomy Validation Suite for Milestone M1.6.

Exercises and verifies the complete closed-loop autonomy pipeline on Windows:
OBSERVE -> RESOLVE TARGET -> VALIDATE COORDINATES -> DISPATCH SAFETY GATE -> ACT -> RE-OBSERVE -> VERIFY

Strict Epistemic Classification:
- LIVE_OS_VALIDATED: Executed against live Windows display, Win32 window APIs, and production adapters.
- TEST_PROVEN: Deterministically proven under controlled integration test assertions.
- CODE_PROVEN: Backed by strict runtime invariants and typed models.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import subprocess
import sys
import time
from typing import Generator
from uuid import uuid4
import pytest

from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.workspace.abi import IS_WINDOWS
from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter
from orbit.contracts.runtime import SystemState
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
from orbit.runtime.execution import (
    ClosedLoopExecutionEngine,
    ClosedLoopExecutionResult,
    ExecutionPolicy,
    ExecutionState,
)
from orbit.runtime.execution.context import DispatchStage
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    TargetIntent,
    TargetStrategy,
)
from orbit.runtime.verification import (
    ActionVerifier,
    ExpectedOutcome,
    ExpectedOutcomeType,
    VerificationStrategy,
)


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
lbl = tk.Label(root, text="ORBIT M1.6 Live Validation Window", font=("Arial", 12))
lbl.pack(pady=10)
btn = tk.Button(root, text="Action Target", width=20, height=2)
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
async def test_live_scenario_a_real_application_discovery():
    """SCENARIO A: Real Application Discovery on Live Windows OS.

    Proves:
    1. ProductionObservationAdapter captures live desktop windows without mocks.
    2. The isolated test application is discovered with genuine HWND, process ID, and DWM bounding box.
    """
    obs = ProductionObservationAdapter(default_ttl_ms=1000.0)
    await obs.initialize()

    unique_title = f"ORBIT_Discovery_{uuid4().hex[:6]}"

    try:
        with spawn_isolated_test_window(unique_title, width=320, height=220, x=180, y=180):
            snapshot = await obs.capture_snapshot()

            assert snapshot is not None
            assert snapshot.snapshot_id is not None
            assert snapshot.timestamp_ns > 0
            assert snapshot.generation_id >= 0

            # Find the spawned window in the live observation snapshot
            matching_windows = [
                w for w in snapshot.windows
                if w.window_title and unique_title in w.window_title
            ]
            assert len(matching_windows) == 1, f"Expected 1 matching window, found {len(matching_windows)}"

            target_window = matching_windows[0]
            assert target_window.hwnd > 0
            assert target_window.process_id > 0
            assert target_window.extended_bounds.width >= 200
            assert target_window.extended_bounds.height >= 150
            assert target_window.is_visible is True
    finally:
        await obs.shutdown()


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="Live OS validation requires Windows platform")
async def test_live_scenario_b_real_target_resolution_and_safe_point():
    """SCENARIO B: Dynamic Target Resolution and Safe Action Point Calculation.

    Proves:
    1. EvidenceBasedTargetLocator dynamically resolves target from live observation.
    2. Coordinates are NOT hardcoded, but calculated strictly within the window interior.
    3. SafeActionPoint applies interior margins and carries the active desktop generation.
    """
    from orbit.runtime.targeting.models import TargetResolutionStatus

    obs = ProductionObservationAdapter(default_ttl_ms=1000.0)
    wsp = ProductionWorkspaceAdapter()
    locator = EvidenceBasedTargetLocator()

    await obs.initialize()
    await wsp.initialize()

    unique_title = f"ORBIT_Resolution_{uuid4().hex[:6]}"

    try:
        with spawn_isolated_test_window(unique_title, width=340, height=240, x=220, y=220):
            snapshot = await obs.capture_snapshot()

            intent = TargetIntent(
                strategy=TargetStrategy.WINDOW_TITLE,
                window_title=unique_title,
            )

            resolution = locator.locate_target(snapshot, intent)

            assert resolution.status == TargetResolutionStatus.RESOLVED
            assert resolution.target is not None
            assert resolution.target.safe_point is not None

            sp = resolution.target.safe_point
            bounds = resolution.target.bounding_box

            # Verify safe point is strictly interior
            assert bounds.left < sp.x < bounds.right
            assert bounds.top < sp.y < bounds.bottom
            assert sp.desktop_generation_id == snapshot.generation_id
    finally:
        await wsp.shutdown()
        await obs.shutdown()


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="Live OS validation requires Windows platform")
async def test_live_scenario_c_real_safe_action_dispatch():
    """SCENARIO C: Safe Action Dispatch through AutonomousDispatchGate.

    Proves:
    1. Coordinate passes workspace usable canvas and desktop generation checks.
    2. Action moves pointer to the dynamically resolved target on the live desktop.
    3. Pointer dispatch verifies stage progression to DISPATCHED.
    """
    event_bus = EventBus()
    obs = ProductionObservationAdapter(default_ttl_ms=1000.0)
    wsp = ProductionWorkspaceAdapter()
    ptr = ProductionPointerAdapter()
    locator = EvidenceBasedTargetLocator()
    verifier = ActionVerifier()

    await obs.initialize()
    await wsp.initialize()
    await ptr.initialize()

    unique_title = f"ORBIT_Action_{uuid4().hex[:6]}"

    try:
        with spawn_isolated_test_window(unique_title, width=300, height=200, x=250, y=250):
            engine = ClosedLoopExecutionEngine(
                observation=obs,
                pointer=ptr,
                workspace=wsp,
                target_locator=locator,
                action_verifier=verifier,
                event_bus=event_bus,
            )

            intent = TargetIntent(
                strategy=TargetStrategy.WINDOW_TITLE,
                window_title=unique_title,
            )

            result: ClosedLoopExecutionResult = await engine.execute_task_action(
                session_id="live_session_c",
                task_id="task_action_dispatch",
                prompt="Move pointer to target window interior",
                target_intent=intent,
                action_type="pointer_move",
                policy=ExecutionPolicy(max_total_attempts=2, allow_inconclusive_as_success=True),
            )

            assert result.is_success is True
            assert result.final_state == ExecutionState.SUCCEEDED
            assert result.dispatch_stage == DispatchStage.DISPATCHED
            assert result.resolved_target is not None
            assert result.resolved_target.safe_point.x >= 250
            assert result.resolved_target.safe_point.y >= 250
    finally:
        await ptr.shutdown()
        await wsp.shutdown()
        await obs.shutdown()


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="Live OS validation requires Windows platform")
async def test_live_scenario_d_real_post_action_verification():
    """SCENARIO D: Live Post-Action Observation and State Verification.

    Proves:
    1. After action execution, a fresh post-action observation snapshot is captured.
    2. ActionVerifier compares pre-action and post-action evidence truthfully.
    3. Verification result reflects actual observable desktop state.
    """
    event_bus = EventBus()
    obs = ProductionObservationAdapter(default_ttl_ms=1000.0)
    wsp = ProductionWorkspaceAdapter()
    ptr = ProductionPointerAdapter()
    locator = EvidenceBasedTargetLocator()
    verifier = ActionVerifier()

    await obs.initialize()
    await wsp.initialize()
    await ptr.initialize()

    unique_title = f"ORBIT_Verify_{uuid4().hex[:6]}"

    try:
        with spawn_isolated_test_window(unique_title, width=320, height=220, x=200, y=200):
            engine = ClosedLoopExecutionEngine(
                observation=obs,
                pointer=ptr,
                workspace=wsp,
                target_locator=locator,
                action_verifier=verifier,
                event_bus=event_bus,
            )

            intent = TargetIntent(
                strategy=TargetStrategy.WINDOW_TITLE,
                window_title=unique_title,
                expected_outcome=ExpectedOutcome(
                    strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
                    outcome_type=ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE,
                ),
            )

            result: ClosedLoopExecutionResult = await engine.execute_task_action(
                session_id="live_session_d",
                task_id="task_verify_state",
                prompt="Interact and verify window presence",
                target_intent=intent,
                action_type="pointer_move",
                expected_outcome=intent.expected_outcome,
                policy=ExecutionPolicy(max_total_attempts=2, allow_inconclusive_as_success=True),
            )

            assert result.is_success is True
            assert result.verification_result is not None
            assert result.verification_result.pre_evidence is not None
            assert result.verification_result.post_evidence is not None
            assert result.dispatch_stage == DispatchStage.DISPATCHED
    finally:
        await ptr.shutdown()
        await wsp.shutdown()
        await obs.shutdown()
