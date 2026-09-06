"""Unit tests for NativeWorkspaceWindow lifecycle and window procedure routing."""

import pytest
from orbit.adapters.workspace.abi import IS_WINDOWS, RECT
from orbit.adapters.workspace.window import (
    NativeWorkspaceWindow,
    Win32WindowGateway,
)
from orbit.models.common import BoundingBox


class FakeWindowGateway(Win32WindowGateway):
    """Deterministic fake gateway simulating Win32 User32/Kernel32 APIs."""

    def __init__(
        self,
        should_register_class: bool = True,
        should_create_window: bool = True,
        should_set_pos: bool = True,
        should_destroy: bool = True,
    ) -> None:
        self.should_register_class = should_register_class
        self.should_create_window = should_create_window
        self.should_set_pos = should_set_pos
        self.should_destroy = should_destroy

        self.registered_classes = []
        self.unregistered_classes = []
        self.created_windows = {}
        self.destroyed_windows = []
        self.positions = []
        self._next_atom = 100
        self._next_hwnd = 1000

    def get_module_handle(self) -> int:
        return 4096

    def register_class(self, wc) -> int:
        if not self.should_register_class:
            return 0
        self._next_atom += 1
        self.registered_classes.append((self._next_atom, wc.lpszClassName))
        return self._next_atom

    def unregister_class(self, class_name: str, h_instance: int) -> bool:
        self.unregistered_classes.append((class_name, h_instance))
        return True

    def create_window(self, ex_style, class_name, window_name, style, x, y, w, h, h_instance) -> int:
        if not self.should_create_window:
            return 0
        self._next_hwnd += 1
        hwnd = self._next_hwnd
        self.created_windows[hwnd] = {
            "ex_style": ex_style,
            "class_name": class_name,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
        }
        return hwnd

    def destroy_window(self, hwnd: int) -> bool:
        if not self.should_destroy:
            return False
        self.destroyed_windows.append(hwnd)
        if hwnd in self.created_windows:
            del self.created_windows[hwnd]
        return True

    def set_window_pos(self, hwnd: int, hwnd_insert_after: int, x: int, y: int, w: int, h: int, flags: int) -> bool:
        if not self.should_set_pos:
            return False
        self.positions.append((hwnd, x, y, w, h, flags))
        return True

    def get_window_rect(self, hwnd: int) -> RECT:
        if hwnd in self.created_windows:
            w_info = self.created_windows[hwnd]
            return RECT(w_info["x"], w_info["y"], w_info["x"] + w_info["w"], w_info["y"] + w_info["h"])
        return RECT(0, 0, 400, 600)

    def is_window(self, hwnd: int) -> bool:
        return hwnd in self.created_windows

    def def_window_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        return 0

    def get_last_error(self) -> int:
        return 0


def test_window_creation_success():
    gw = FakeWindowGateway()
    win = NativeWorkspaceWindow(gateway=gw)
    hwnd = win.create(bounds=BoundingBox(left=100, top=100, width=500, height=800))
    assert hwnd == 1001
    assert win.is_created is True
    assert win.hwnd == 1001
    assert len(gw.registered_classes) == 1


def test_window_class_registration_failure_raises():
    gw = FakeWindowGateway(should_register_class=False)
    win = NativeWorkspaceWindow(gateway=gw)
    with pytest.raises(RuntimeError, match="Failed to register Win32 window class"):
        win.create()
    assert win.is_created is False
    assert win.hwnd == 0


def test_window_creation_failure_unregisters_class_and_fails_closed():
    gw = FakeWindowGateway(should_create_window=False)
    win = NativeWorkspaceWindow(gateway=gw)
    with pytest.raises(RuntimeError, match="Failed to create native Win32 window"):
        win.create()
    assert win.is_created is False
    assert win.hwnd == 0
    # Cleaned up registered class
    assert len(gw.unregistered_classes) == 1


def test_window_positioning():
    gw = FakeWindowGateway()
    win = NativeWorkspaceWindow(gateway=gw)
    win.create(bounds=BoundingBox(left=0, top=0, width=400, height=600))
    rc = RECT(2160, 0, 2880, 1800)
    ok = win.set_position(rc, topmost=True, activate=False)
    assert ok is True
    assert len(gw.positions) == 1
    assert gw.positions[0] == (1001, 2160, 0, 720, 1800, 0x0040 | 0x0010)


def test_window_destruction_cleans_class_and_hwnd():
    gw = FakeWindowGateway()
    win = NativeWorkspaceWindow(gateway=gw)
    win.create()
    assert win.is_created is True
    assert win.hwnd != 0

    ok = win.destroy()
    assert ok is True
    assert win.is_created is False
    assert win.hwnd == 0
    assert len(gw.destroyed_windows) == 1
    assert len(gw.unregistered_classes) == 1


def test_window_notification_listener_routing():
    gw = FakeWindowGateway()
    win = NativeWorkspaceWindow(gateway=gw)
    notifications = []

    def on_notif(code, lparam):
        notifications.append((code, lparam))

    win.add_notification_listener(on_notif)
    # Simulate window proc invocation with callback message
    res = win._window_proc_handler(win.hwnd, win.callback_message, 1, 42)
    assert res == 0
    assert len(notifications) == 1
    assert notifications[0] == (1, 42)
    assert len(win.get_recorded_notifications()) == 1


@pytest.mark.skipif(not IS_WINDOWS, reason="Live Win32 window test runs only on Windows")
def test_live_window_creation_and_destruction():
    win = NativeWorkspaceWindow()
    hwnd = win.create(bounds=BoundingBox(left=100, top=100, width=300, height=300), visible=False)
    assert hwnd != 0
    assert win.is_created is True

    rc = RECT(100, 100, 400, 400)
    pos_ok = win.set_position(rc, topmost=False)
    assert pos_ok is True

    destroy_ok = win.destroy()
    assert destroy_ok is True
    assert win.is_created is False
