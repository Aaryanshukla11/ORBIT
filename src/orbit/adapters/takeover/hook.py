"""Native Win32 Low-Level Input Hook Monitor running on a dedicated message-pump thread."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import sys
import threading
import time
from typing import Callable, Optional

from orbit.adapters.takeover.classifier import TakeoverClassifier, TakeoverEvidence
from orbit.adapters.takeover.safety import (
    HOOKPROC,
    KBDLLHOOKSTRUCT,
    MSLLHOOKSTRUCT,
    TakeoverAbiGate,
    WH_KEYBOARD_LL,
    WH_MOUSE_LL,
    WM_QUIT,
    kernel32,
    user32,
)

logger = logging.getLogger(__name__)


class NativeHookInstallationError(Exception):
    """Raised when low-level hook installation fails."""


class NativeInputMonitor:
    """Manages dedicated background OS thread for WH_MOUSE_LL and WH_KEYBOARD_LL message pump."""

    def __init__(self) -> None:
        self._mouse_hook = None
        self._keyboard_hook = None
        self._hook_thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._is_running = False
        self._event_counter = 0
        self._callback: Optional[Callable[[TakeoverEvidence], None]] = None

        # Keep permanent references to HOOKPROC callbacks to prevent GC collection
        self._mouse_proc = HOOKPROC(self._low_level_mouse_handler)
        self._keyboard_proc = HOOKPROC(self._low_level_keyboard_handler)

        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def is_hooked(self) -> bool:
        return bool(self._mouse_hook and self._keyboard_hook)

    def start(self, on_event_callback: Callable[[TakeoverEvidence], None]) -> None:
        """Starts the input monitor on a dedicated message pump thread."""
        with self._lock:
            if self._is_running:
                return

            abi_res = TakeoverAbiGate.validate_abi()
            if not abi_res.is_valid:
                raise NativeHookInstallationError(f"ABI Validation failed: {abi_res.error_message}")

            self._callback = on_event_callback
            self._is_running = True
            ready_event = threading.Event()
            install_error = []

            def _thread_entry():
                try:
                    self._thread_id = kernel32.GetCurrentThreadId()
                    h_inst = kernel32.GetModuleHandleW(None)

                    self._mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, h_inst, 0)
                    self._keyboard_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._keyboard_proc, h_inst, 0)

                    if not self._mouse_hook or not self._keyboard_hook:
                        err = ctypes.get_last_error()
                        install_error.append(f"SetWindowsHookExW failed (mouse={bool(self._mouse_hook)}, kbd={bool(self._keyboard_hook)}, win32_err={err})")
                        ready_event.set()
                        return

                    logger.info("Low-level native hooks successfully installed on thread %d", self._thread_id)
                    ready_event.set()

                    # Standard Win32 message pump required for low-level hooks
                    msg = (wintypes.DWORD * 12)()
                    while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
                        pass

                except Exception as ex:
                    logger.exception("Exception in native hook thread: %s", ex)
                    install_error.append(str(ex))
                    ready_event.set()
                finally:
                    self._cleanup_hooks()
                    logger.info("Native hook thread %d exited", self._thread_id or 0)

            self._hook_thread = threading.Thread(
                target=_thread_entry,
                name="OrbitNativeTakeoverHookThread",
                daemon=True,
            )
            self._hook_thread.start()

            if not ready_event.wait(timeout=3.0):
                self.stop()
                raise NativeHookInstallationError("Timed out waiting for native hook thread startup")

            if install_error:
                self.stop()
                raise NativeHookInstallationError(f"Failed to install native hooks: {install_error[0]}")

    def stop(self) -> None:
        """Stops the message pump and removes native hooks."""
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False

            if self._thread_id:
                user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

            if self._hook_thread and self._hook_thread.is_alive():
                self._hook_thread.join(timeout=1.5)

            self._cleanup_hooks()
            self._hook_thread = None
            self._thread_id = None
            self._callback = None
            logger.info("Low-level native hooks uninstalled")

    def _cleanup_hooks(self) -> None:
        if self._mouse_hook:
            try:
                user32.UnhookWindowsHookEx(self._mouse_hook)
            except Exception:
                pass
            self._mouse_hook = None

        if self._keyboard_hook:
            try:
                user32.UnhookWindowsHookEx(self._keyboard_hook)
            except Exception:
                pass
            self._keyboard_hook = None

    def _low_level_mouse_handler(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code >= 0 and self._is_running and self._callback:
            t_recv = time.perf_counter_ns()
            try:
                info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                self._event_counter += 1
                evidence = TakeoverClassifier.classify_mouse(
                    event_id=self._event_counter,
                    timestamp_ns=t_recv,
                    w_param=w_param,
                    info=info,
                )
                self._callback(evidence)
            except Exception as ex:
                logger.warning("Error in mouse hook callback: %s", ex)

        return user32.CallNextHookEx(self._mouse_hook, n_code, w_param, l_param)

    def _low_level_keyboard_handler(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code >= 0 and self._is_running and self._callback:
            t_recv = time.perf_counter_ns()
            try:
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                self._event_counter += 1
                evidence = TakeoverClassifier.classify_keyboard(
                    event_id=self._event_counter,
                    timestamp_ns=t_recv,
                    w_param=w_param,
                    info=info,
                )
                self._callback(evidence)
            except Exception as ex:
                logger.warning("Error in keyboard hook callback: %s", ex)

        return user32.CallNextHookEx(self._keyboard_hook, n_code, w_param, l_param)
