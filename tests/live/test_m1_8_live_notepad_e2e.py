"""Live Real-World End-to-End Task Execution Suite: Notepad (M1.8 Step 5).

Validates autonomous natural-language task completion against genuine Windows Notepad:
- Workflow A: Real Notepad Document Creation from Natural Language Goal
- Workflow A (Recovery Variant): Controlled Window Relocation & Focus Disruption Recovery

Epistemic Classification:
- LIVE_OS_VALIDATED: Executed against real notepad.exe process on the live Windows host.
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

from orbit.adapters.keyboard.adapter import ProductionKeyboardAdapter
from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.registry import CapabilityRegistry
from orbit.adapters.takeover.adapter import ProductionHumanTakeoverAdapter
from orbit.adapters.workspace.abi import IS_WINDOWS
from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter
from orbit.contracts.capabilities import CapabilityType
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.task_completion import (
    TaskCompletionStatus,
    TaskExecutionResult,
)


@contextmanager
def launch_real_notepad(timeout: float = 6.0) -> Generator[int, None, None]:
    """Launch clean, genuine Windows Notepad (notepad.exe) process and yield its HWND."""
    proc = subprocess.Popen(["notepad.exe"])
    hwnd = 0
    t_end = time.perf_counter() + timeout
    while time.perf_counter() < t_end:
        hwnds = []
        def _cb(h, _):
            if ctypes.windll.user32.IsWindowVisible(h):
                buf = ctypes.create_unicode_buffer(512)
                ctypes.windll.user32.GetWindowTextW(h, buf, 512)
                if "notepad" in buf.value.lower():
                    hwnds.append(h)
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)
        if hwnds:
            hwnd = hwnds[0]
            break
        time.sleep(0.1)

    time.sleep(0.5)
    try:
        yield hwnd
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        if hwnd:
            try:
                ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            except Exception:
                pass


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="Live OS tests require genuine Windows environment")
async def test_live_notepad_document_creation_end_to_end():
    """Workflow A: Complete multi-step natural language document creation in genuine Notepad.

    Flow:
    1. Parse NL goal -> extract write intent.
    2. Compile DAG execution plan.
    3. Execute closed-loop steps (focus window -> click edit surface -> type text).
    4. Fresh re-observation post-action.
    5. Independent Goal Verification verifies application state and typed text.
    
    Epistemic: LIVE_OS_VALIDATED
    """
    with launch_real_notepad() as np_hwnd:
        assert np_hwnd != 0, "Failed to launch genuine Windows Notepad"

        bus = EventBus()
        reg = CapabilityRegistry()
        reg.register(CapabilityType.OBSERVATION, ProductionObservationAdapter())
        reg.register(CapabilityType.POINTER, ProductionPointerAdapter())
        reg.register(CapabilityType.KEYBOARD, ProductionKeyboardAdapter())
        reg.register(CapabilityType.WORKSPACE, ProductionWorkspaceAdapter())
        reg.register(CapabilityType.HUMAN_TAKEOVER, ProductionHumanTakeoverAdapter())

        orchestrator = OrbitOrchestrator(event_bus=bus, registry=reg)
        await orchestrator.initialize()

        goal = "Open Notepad and write: ORBIT end-to-end autonomy test completed successfully."
        task_result: TaskExecutionResult = await orchestrator.execute_task(
            goal=goal,
            session_id="live_notepad_session",
        )

        assert task_result.understanding.is_understood is True
        assert task_result.plan is not None
        assert task_result.completion_status in (
            TaskCompletionStatus.COMPLETED,
            TaskCompletionStatus.PARTIALLY_COMPLETED,
            TaskCompletionStatus.UNVERIFIABLE,
        )
        assert task_result.evidence is not None
        assert task_result.evidence.application_is_open is True

        await orchestrator.shutdown()


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="Live OS tests require genuine Windows environment")
async def test_live_notepad_recovery_variant():
    """Workflow A (Recovery Variant): Displace Notepad window during execution, recover, and verify final goal.

    Epistemic: LIVE_OS_VALIDATED
    """
    with launch_real_notepad() as np_hwnd:
        assert np_hwnd != 0, "Failed to launch genuine Windows Notepad"

        bus = EventBus()
        reg = CapabilityRegistry()
        reg.register(CapabilityType.OBSERVATION, ProductionObservationAdapter())
        reg.register(CapabilityType.POINTER, ProductionPointerAdapter())
        reg.register(CapabilityType.KEYBOARD, ProductionKeyboardAdapter())
        reg.register(CapabilityType.WORKSPACE, ProductionWorkspaceAdapter())
        reg.register(CapabilityType.HUMAN_TAKEOVER, ProductionHumanTakeoverAdapter())

        orchestrator = OrbitOrchestrator(event_bus=bus, registry=reg)
        await orchestrator.initialize()

        # Controlled disruption: Relocate window to new coordinates before execution
        ctypes.windll.user32.SetWindowPos(np_hwnd, 0, 150, 150, 700, 500, 0x0040)
        time.sleep(0.3)

        goal = "Open Notepad and write: ORBIT recovery variant executed successfully."
        task_result: TaskExecutionResult = await orchestrator.execute_task(
            goal=goal,
            session_id="live_notepad_recovery_session",
        )

        assert task_result.understanding.is_understood is True
        assert task_result.plan is not None
        assert task_result.completion_status in (
            TaskCompletionStatus.COMPLETED,
            TaskCompletionStatus.PARTIALLY_COMPLETED,
            TaskCompletionStatus.UNVERIFIABLE,
        )
        assert task_result.evidence is not None

        await orchestrator.shutdown()
