"""Unit tests for NativeAppBarDriver registration, positioning, and transactional rollback."""

import pytest
from orbit.adapters.workspace.abi import (
    ABM_NEW,
    ABM_QUERYPOS,
    ABM_REMOVE,
    ABM_SETPOS,
    IS_WINDOWS,
    RECT,
)
from orbit.adapters.workspace.appbar import (
    AppBarOperationResult,
    NativeAppBarDriver,
    Win32ShellGateway,
)
from orbit.adapters.workspace.state import WorkspaceStateManager
from orbit.adapters.workspace.telemetry import WorkspaceTelemetryRecorder
from orbit.adapters.workspace.types import DockEdge, WorkspaceState
from orbit.adapters.workspace.window import NativeWorkspaceWindow
from orbit.models.common import BoundingBox
from tests.unit.test_workspace_window import FakeWindowGateway


class FakeShellGateway(Win32ShellGateway):
    """Deterministic fake gateway simulating Shell32 SHAppBarMessage."""

    def __init__(
        self,
        raise_on_new: bool = False,
        raise_on_query: bool = False,
        raise_on_setpos: bool = False,
        raise_on_remove: bool = False,
    ) -> None:
        self.raise_on_new = raise_on_new
        self.raise_on_query = raise_on_query
        self.raise_on_setpos = raise_on_setpos
        self.raise_on_remove = raise_on_remove

        self.calls = []
        self.last_abd_rc = None

    def sh_appbar_message(self, message: int, abd) -> int:
        self.calls.append((message, abd.uEdge, (abd.rc.left, abd.rc.top, abd.rc.right, abd.rc.bottom)))

        if message == ABM_NEW:
            if self.raise_on_new:
                raise RuntimeError("Simulated ABM_NEW shell exception")
            return 1
        elif message == ABM_QUERYPOS:
            if self.raise_on_query:
                raise RuntimeError("Simulated ABM_QUERYPOS shell exception")
            return 1
        elif message == ABM_SETPOS:
            if self.raise_on_setpos:
                raise RuntimeError("Simulated ABM_SETPOS shell exception")
            self.last_abd_rc = (abd.rc.left, abd.rc.top, abd.rc.right, abd.rc.bottom)
            return 1
        elif message == ABM_REMOVE:
            if self.raise_on_remove:
                raise RuntimeError("Simulated ABM_REMOVE shell exception")
            return 1

        return 0

    def get_last_error(self) -> int:
        return 0


def test_appbar_dock_edge_none_rejected():
    driver = NativeAppBarDriver()
    res = driver.register_and_dock(
        edge=DockEdge.NONE,
        target_bounds=BoundingBox(left=0, top=0, width=500, height=800),
    )
    assert res.success is False
    assert "Cannot dock to DockEdge.NONE" in (res.error_message or "")


def test_appbar_full_registration_lifecycle_success():
    fake_win_gw = FakeWindowGateway()
    fake_shell_gw = FakeShellGateway()
    win = NativeWorkspaceWindow(gateway=fake_win_gw)
    sm = WorkspaceStateManager(initial_state=WorkspaceState.READY_FLOATING)
    telemetry = WorkspaceTelemetryRecorder()

    driver = NativeAppBarDriver(
        window=win,
        state_manager=sm,
        telemetry_recorder=telemetry,
        shell_gateway=fake_shell_gw,
    )

    req_bounds = BoundingBox(left=2160, top=0, width=720, height=1800)
    res = driver.register_and_dock(edge=DockEdge.RIGHT, target_bounds=req_bounds)

    assert res.success is True
    assert res.edge == DockEdge.RIGHT
    assert res.final_rect is not None
    assert res.final_rect.left == 2160
    assert res.final_rect.width == 720
    assert driver.is_registered is True
    assert driver.current_edge == DockEdge.RIGHT
    assert sm.current_state == WorkspaceState.DOCKED
    assert sm.desktop_generation_id == 2

    # Check shell calls sequence: ABM_NEW -> ABM_QUERYPOS -> ABM_SETPOS
    assert len(fake_shell_gw.calls) == 3
    assert fake_shell_gw.calls[0][0] == ABM_NEW
    assert fake_shell_gw.calls[1][0] == ABM_QUERYPOS
    assert fake_shell_gw.calls[2][0] == ABM_SETPOS


def test_appbar_abm_new_failure_triggers_rollback():
    fake_win_gw = FakeWindowGateway()
    fake_shell_gw = FakeShellGateway(raise_on_new=True)
    win = NativeWorkspaceWindow(gateway=fake_win_gw)
    sm = WorkspaceStateManager(initial_state=WorkspaceState.READY_FLOATING)
    telemetry = WorkspaceTelemetryRecorder()

    driver = NativeAppBarDriver(
        window=win,
        state_manager=sm,
        telemetry_recorder=telemetry,
        shell_gateway=fake_shell_gw,
    )

    req_bounds = BoundingBox(left=2160, top=0, width=720, height=1800)
    res = driver.register_and_dock(edge=DockEdge.RIGHT, target_bounds=req_bounds)

    assert res.success is False
    assert res.rollback_executed is True
    assert res.rollback_success is True
    assert driver.is_registered is False
    assert sm.current_state == WorkspaceState.FAILED
    # Window destroyed during rollback
    assert win.is_created is False


def test_appbar_setpos_window_failure_triggers_rollback():
    # Window set_pos fails -> ABM_REMOVE called, window destroyed
    fake_win_gw = FakeWindowGateway(should_set_pos=False)
    fake_shell_gw = FakeShellGateway()
    win = NativeWorkspaceWindow(gateway=fake_win_gw)
    sm = WorkspaceStateManager(initial_state=WorkspaceState.READY_FLOATING)

    driver = NativeAppBarDriver(
        window=win,
        state_manager=sm,
        shell_gateway=fake_shell_gw,
    )

    req_bounds = BoundingBox(left=2160, top=0, width=720, height=1800)
    res = driver.register_and_dock(edge=DockEdge.RIGHT, target_bounds=req_bounds)

    assert res.success is False
    assert res.rollback_executed is True
    assert sm.current_state == WorkspaceState.FAILED
    assert driver.is_registered is False
    # ABM_REMOVE should be in calls
    call_types = [c[0] for c in fake_shell_gw.calls]
    assert ABM_REMOVE in call_types


def test_appbar_unregistration_idempotence():
    driver = NativeAppBarDriver()
    res = driver.unregister_and_release()
    assert res.success is True
    assert res.operation == "REMOVE"


def test_appbar_unregistration_and_release():
    fake_win_gw = FakeWindowGateway()
    fake_shell_gw = FakeShellGateway()
    win = NativeWorkspaceWindow(gateway=fake_win_gw)
    sm = WorkspaceStateManager(initial_state=WorkspaceState.READY_FLOATING)

    driver = NativeAppBarDriver(
        window=win,
        state_manager=sm,
        shell_gateway=fake_shell_gw,
    )

    # First dock
    req_bounds = BoundingBox(left=2160, top=0, width=720, height=1800)
    driver.register_and_dock(edge=DockEdge.RIGHT, target_bounds=req_bounds)
    assert driver.is_registered is True
    assert sm.current_state == WorkspaceState.DOCKED
    assert sm.desktop_generation_id == 2

    # Now unregister
    res = driver.unregister_and_release()
    assert res.success is True
    assert driver.is_registered is False
    assert driver.current_edge == DockEdge.NONE
    assert sm.current_state == WorkspaceState.READY_FLOATING
    assert sm.desktop_generation_id == 3

    # Check ABM_REMOVE was sent
    assert fake_shell_gw.calls[-1][0] == ABM_REMOVE


def test_appbar_dock_left_edge():
    fake_win_gw = FakeWindowGateway()
    fake_shell_gw = FakeShellGateway()
    win = NativeWorkspaceWindow(gateway=fake_win_gw)
    sm = WorkspaceStateManager(initial_state=WorkspaceState.READY_FLOATING)

    driver = NativeAppBarDriver(
        window=win,
        state_manager=sm,
        shell_gateway=fake_shell_gw,
    )

    req_bounds = BoundingBox(left=0, top=0, width=720, height=1800)
    res = driver.register_and_dock(edge=DockEdge.LEFT, target_bounds=req_bounds)

    assert res.success is True
    assert res.edge == DockEdge.LEFT
    assert res.final_rect.left == 0
    assert res.final_rect.width == 720


def test_appbar_dock_top_and_bottom_edges():
    fake_win_gw = FakeWindowGateway()
    fake_shell_gw = FakeShellGateway()
    win = NativeWorkspaceWindow(gateway=fake_win_gw)
    sm = WorkspaceStateManager(initial_state=WorkspaceState.READY_FLOATING)

    driver = NativeAppBarDriver(
        window=win,
        state_manager=sm,
        shell_gateway=fake_shell_gw,
    )

    # Top edge
    res_top = driver.register_and_dock(
        edge=DockEdge.TOP,
        target_bounds=BoundingBox(left=0, top=0, width=1920, height=100),
    )
    assert res_top.success is True
    assert res_top.final_rect.height == 100

    # Bottom edge
    res_bot = driver.register_and_dock(
        edge=DockEdge.BOTTOM,
        target_bounds=BoundingBox(left=0, top=980, width=1920, height=100),
    )
    assert res_bot.success is True
    assert res_bot.final_rect.height == 100


def test_appbar_negative_origin_virtual_desktop_coordinates():
    fake_win_gw = FakeWindowGateway()
    fake_shell_gw = FakeShellGateway()
    win = NativeWorkspaceWindow(gateway=fake_win_gw)
    sm = WorkspaceStateManager(initial_state=WorkspaceState.READY_FLOATING)

    driver = NativeAppBarDriver(
        window=win,
        state_manager=sm,
        shell_gateway=fake_shell_gw,
    )

    # Secondary monitor to the left starting at x = -1920
    req_bounds = BoundingBox(left=-1920, top=0, width=480, height=1080)
    res = driver.register_and_dock(edge=DockEdge.LEFT, target_bounds=req_bounds)

    assert res.success is True
    assert res.final_rect.left == -1920
    assert res.final_rect.width == 480


def test_appbar_notification_recording():
    driver = NativeAppBarDriver()
    # Trigger notification handler
    driver._on_appbar_notification(1, 100)  # ABN_POSCHANGED
    driver._on_appbar_notification(0, 200)  # ABN_STATECHANGE

    notifs = driver.get_recorded_notifications()
    assert len(notifs) == 2
    assert notifs[0].notification_code == 1
    assert notifs[0].notification_name == "ABN_POSCHANGED"
    assert notifs[1].notification_code == 0
    assert notifs[1].notification_name == "ABN_STATECHANGE"


@pytest.mark.skipif(not IS_WINDOWS, reason="Live Win32 AppBar test runs only on Windows")
def test_live_appbar_registration_and_removal():
    win = NativeWorkspaceWindow()
    sm = WorkspaceStateManager(initial_state=WorkspaceState.READY_FLOATING)
    driver = NativeAppBarDriver(window=win, state_manager=sm)

    req_bounds = BoundingBox(left=2160, top=0, width=720, height=1800)
    res = driver.register_and_dock(edge=DockEdge.RIGHT, target_bounds=req_bounds)

    try:
        assert res.success is True
        assert driver.is_registered is True
        assert sm.current_state == WorkspaceState.DOCKED
    finally:
        # Guarantee cleanup
        res_unreg = driver.unregister_and_release(destroy_window=True)
        assert res_unreg.success is True
        assert driver.is_registered is False
        assert sm.current_state == WorkspaceState.READY_FLOATING
