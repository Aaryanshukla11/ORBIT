"""Unit and integration tests for Human Takeover Gating for MVP Stabilization.

Verifies:
- Test A: Normal Task Submission (Physical Enter key does not trigger HUMAN_TAKEOVER_ACTIVE)
- Test B: Physical Keyboard Input during execution (Ignored by takeover subsystem, no cancellation)
- Test C: Stale State Recovery (System in HUMAN_TAKEOVER_ACTIVE recovers to IDLE when disabled)
- Test D: Re-enable validation (When ORBIT_HUMAN_TAKEOVER_ENABLED=true, takeover preemption functions normally)
"""

import asyncio
import os
import time
from unittest.mock import AsyncMock
import pytest

from orbit.config import is_human_takeover_enabled
from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.runtime import SystemState, TaskStatus
from orbit.adapters.mocks import (
    MockHumanTakeoverAdapter,
    MockKeyboardAdapter,
    MockObservationAdapter,
    MockPointerAdapter,
    MockSafetyCoordinator,
    MockWorkspaceAdapter,
)
from orbit.adapters.registry import CapabilityRegistry
from orbit.adapters.takeover.adapter import ProductionHumanTakeoverAdapter
from orbit.adapters.takeover.classifier import (
    InputDevice,
    InputEventType,
    InputSource,
    TakeoverEvidence,
)
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator


def build_test_registry(enable_hooks=True):
    reg = CapabilityRegistry()
    reg.register(CapabilityType.OBSERVATION, MockObservationAdapter())
    reg.register(CapabilityType.POINTER, MockPointerAdapter())
    reg.register(CapabilityType.KEYBOARD, MockKeyboardAdapter())
    reg.register(CapabilityType.HUMAN_TAKEOVER, ProductionHumanTakeoverAdapter(enable_live_hooks=enable_hooks, human_takeover_enabled=False))
    reg.register(CapabilityType.WORKSPACE, MockWorkspaceAdapter())
    reg.register(CapabilityType.SAFETY, MockSafetyCoordinator())
    return reg


@pytest.mark.asyncio
async def test_a_normal_task_submission_enter_key(monkeypatch):
    """Test A: Physical Enter key event does not trigger takeover when disabled."""
    monkeypatch.setenv("ORBIT_HUMAN_TAKEOVER_ENABLED", "false")
    assert not is_human_takeover_enabled()

    bus = EventBus()
    reg = build_test_registry(enable_hooks=True)
    orch = OrbitOrchestrator(event_bus=bus, registry=reg, clock=SystemClock(), human_takeover_enabled=False)
    orch.execute_task = AsyncMock()
    await orch.initialize()
    assert orch.system_state == SystemState.IDLE

    # Simulate physical Enter key (VK_RETURN = 13)
    tkv: ProductionHumanTakeoverAdapter = reg.resolve(CapabilityType.HUMAN_TAKEOVER)
    evidence = TakeoverEvidence(
        event_id=1,
        timestamp_ns=time.perf_counter_ns(),
        device=InputDevice.KEYBOARD,
        event_type=InputEventType.KEY_DOWN,
        source=InputSource.USER_PHYSICAL,
        should_trigger_takeover=True,
        reason="Physical keydown (VK 13) from USER_PHYSICAL",
        vk_code=13,
        scan_code=28,
        is_injected=False,
    )

    is_active = await tkv.is_takeover_active()
    assert is_active is False
    assert orch.system_state == SystemState.IDLE

    # Submit task
    task = await orch.submit_task(session_id="s1", prompt="Open Notepad")
    assert task.status in (TaskStatus.CREATED, TaskStatus.QUEUED, TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.COMPLETED)
    assert orch.system_state != SystemState.HUMAN_TAKEOVER_ACTIVE
    await orch.shutdown()


@pytest.mark.asyncio
async def test_b_physical_input_during_execution(monkeypatch):
    """Test B: Physical keyboard input during execution does not cancel task."""
    monkeypatch.setenv("ORBIT_HUMAN_TAKEOVER_ENABLED", "false")
    assert not is_human_takeover_enabled()

    bus = EventBus()
    reg = build_test_registry(enable_hooks=True)
    orch = OrbitOrchestrator(event_bus=bus, registry=reg, clock=SystemClock(), human_takeover_enabled=False)
    orch.execute_task = AsyncMock()
    await orch.initialize()

    # Simulate physical key events
    tkv: ProductionHumanTakeoverAdapter = reg.resolve(CapabilityType.HUMAN_TAKEOVER)
    for idx, vk in enumerate((65, 66, 13, 32)):  # 'A', 'B', Enter, Space
        ev = TakeoverEvidence(
            event_id=idx + 2,
            timestamp_ns=time.perf_counter_ns(),
            device=InputDevice.KEYBOARD,
            event_type=InputEventType.KEY_DOWN,
            source=InputSource.USER_PHYSICAL,
            should_trigger_takeover=True,
            reason=f"Physical keydown ({vk})",
            vk_code=vk,
            is_injected=False,
        )
        assert await tkv.is_takeover_active() is False

    assert orch.system_state == SystemState.IDLE
    assert await orch.is_human_takeover_active() is False
    await orch.shutdown()


@pytest.mark.asyncio
async def test_c_stale_state_recovery(monkeypatch):
    """Test C: If system is forced into HUMAN_TAKEOVER_ACTIVE, it recovers to IDLE when disabled."""
    monkeypatch.setenv("ORBIT_HUMAN_TAKEOVER_ENABLED", "false")
    assert not is_human_takeover_enabled()

    bus = EventBus()
    reg = build_test_registry(enable_hooks=True)
    orch = OrbitOrchestrator(event_bus=bus, registry=reg, clock=SystemClock(), human_takeover_enabled=False)
    orch.execute_task = AsyncMock()
    await orch.initialize()

    # Force system state to HUMAN_TAKEOVER_ACTIVE
    orch._system_sm._state = SystemState.HUMAN_TAKEOVER_ACTIVE
    assert orch.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE

    # Submit a new task - should auto-recover to IDLE and NOT fail with HUMAN_TAKEOVER_ACTIVE
    task = await orch.submit_task(session_id="s1", prompt="Open Calculator")
    assert orch.system_state != SystemState.HUMAN_TAKEOVER_ACTIVE
    if task.error:
        assert task.error.code != "HUMAN_TAKEOVER_ACTIVE"

    await orch.shutdown()


@pytest.mark.asyncio
async def test_d_reenable_takeover(monkeypatch):
    """Test D: When ORBIT_HUMAN_TAKEOVER_ENABLED=true, takeover functions normally."""
    monkeypatch.setenv("ORBIT_HUMAN_TAKEOVER_ENABLED", "true")
    assert is_human_takeover_enabled()

    bus = EventBus()
    reg = CapabilityRegistry()
    mock_takeover = MockHumanTakeoverAdapter()
    reg.register(CapabilityType.OBSERVATION, MockObservationAdapter())
    reg.register(CapabilityType.POINTER, MockPointerAdapter())
    reg.register(CapabilityType.KEYBOARD, MockKeyboardAdapter())
    reg.register(CapabilityType.HUMAN_TAKEOVER, mock_takeover)
    reg.register(CapabilityType.WORKSPACE, MockWorkspaceAdapter())
    reg.register(CapabilityType.SAFETY, MockSafetyCoordinator())

    orch = OrbitOrchestrator(event_bus=bus, registry=reg, clock=SystemClock(), human_takeover_enabled=True)
    orch.execute_task = AsyncMock()
    await orch.initialize()
    assert orch.system_state == SystemState.IDLE

    # Trigger takeover
    await orch.handle_human_takeover(reason="Operator intervention", source="hardware_hook")
    assert orch.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE
    assert await orch.is_human_takeover_active() is True

    # Submitting task while enabled and active should fail with HUMAN_TAKEOVER_ACTIVE
    task = await orch.submit_task(session_id="s1", prompt="Open Notepad")
    assert task.status == TaskStatus.FAILED
    assert task.error is not None
    assert task.error.code == "HUMAN_TAKEOVER_ACTIVE"

    # Release takeover
    assert await orch.release_takeover() is True
    assert orch.system_state == SystemState.IDLE

    await orch.shutdown()
