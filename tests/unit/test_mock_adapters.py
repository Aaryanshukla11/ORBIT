"""Unit tests for mock capability adapters."""

import pytest

from orbit.adapters.mocks import (
    MockHumanTakeoverAdapter,
    MockKeyboardAdapter,
    MockObservationAdapter,
    MockPointerAdapter,
    MockSafetyCoordinator,
    MockWorkspaceAdapter,
)
from orbit.models.common import ScreenPoint


@pytest.mark.asyncio
async def test_mock_observation():
    obs = MockObservationAdapter()
    # Before initialization, state is CREATED and status is UNAVAILABLE
    health_pre = await obs.get_health()
    assert health_pre.status.value == "UNAVAILABLE"
    assert obs.is_ready is False

    await obs.initialize()
    assert obs.is_ready is True

    frame = await obs.capture_screen()
    assert frame.frame_id == "frame_000001"
    assert frame.resolution.width == 1920
    assert frame.resolution.height == 1080
    assert len(frame.raw_bytes) > 0

    metrics = await obs.get_display_metrics()
    assert len(metrics) == 1
    assert metrics[0].is_primary is True

    health = await obs.get_health()
    assert health.status.value == "HEALTHY"


@pytest.mark.asyncio
async def test_mock_pointer():
    ptr = MockPointerAdapter(initial_position=ScreenPoint(x=100, y=100))
    pos = await ptr.get_cursor_position()
    assert pos.x == 100 and pos.y == 100

    await ptr.move_to(300, 400)
    pos2 = await ptr.get_cursor_position()
    assert pos2.x == 300 and pos2.y == 400

    await ptr.click(500, 600, button="left")
    assert len(ptr.click_history) == 1
    assert ptr.click_history[0] == {"x": 500, "y": 600, "button": "left", "count": 1}

    await ptr.press_down("left")
    assert ptr.button_states["left"] is True
    await ptr.emergency_release_all()
    assert ptr.button_states["left"] is False


@pytest.mark.asyncio
async def test_mock_keyboard():
    kbd = MockKeyboardAdapter()
    await kbd.type_text("Hello ORBIT")
    assert kbd.typed_history == ["Hello ORBIT"]

    await kbd.press_shortcut("ctrl+c")
    assert kbd.shortcut_history == ["ctrl+c"]


@pytest.mark.asyncio
async def test_mock_takeover():
    tkv = MockHumanTakeoverAdapter()
    triggered = []

    await tkv.start_monitoring(lambda: triggered.append(True))
    assert tkv.is_monitoring is True

    tkv.trigger_takeover()
    assert len(triggered) == 1
    assert await tkv.is_takeover_active() is True

    await tkv.reset_takeover_state()
    assert await tkv.is_takeover_active() is False


@pytest.mark.asyncio
async def test_mock_workspace():
    wsp = MockWorkspaceAdapter()
    await wsp.register_appbar(edge="right", size=400)
    assert wsp.is_registered is True
    area = await wsp.get_work_area()
    assert area.width == 1920 - 400

    await wsp.unregister_appbar()
    assert wsp.is_registered is False


@pytest.mark.asyncio
async def test_mock_safety():
    sft = MockSafetyCoordinator()
    assert await sft.is_safe_state() is True
    await sft.emergency_stop_all()
    assert sft.stop_count == 1
