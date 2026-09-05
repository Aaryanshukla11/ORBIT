"""
Native Win32 Child Control Provider for ORBIT Prototype D v1.3.1.
Accurately named Win32 child HWND enumerator using EnumChildWindows, GetClassNameW, and GetWindowTextW.
STRICT RULE: Emits evidence tagged as WIN32_CONTROL; NEVER relabeled as UI_AUTOMATION.
"""

import ctypes
from ctypes import wintypes
import time
import threading
from typing import List, Optional, Tuple, Any

from app_types import (
    Rect,
    UIElementObservation,
    ProviderResult,
    ProviderStatus,
    ProviderErrorReason,
    ConfidenceLevel,
    EvidenceSource,
)

user32 = ctypes.windll.user32

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL

user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

user32.IsWindowEnabled.argtypes = [wintypes.HWND]
user32.IsWindowEnabled.restype = wintypes.BOOL

user32.GetFocus.argtypes = []
user32.GetFocus.restype = wintypes.HWND

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
user32.EnumChildWindows.restype = wintypes.BOOL


class Win32ControlProvider:
    """
    Independent Win32 Child Control Provider (HWND Tree Enumerator).
    """

    def traverse_window(
        self,
        hwnd: int,
        max_depth: int = 5,
        cancellation_event: Optional[threading.Event] = None,
        generation_id: int = 0,
    ) -> ProviderResult:
        """
        Traverses child HWND controls for the target window handle.
        """
        t0 = time.perf_counter()
        if not hwnd or not user32.IsWindow(hwnd):
            return ProviderResult(
                provider_name="WIN32_CONTROL",
                status=ProviderStatus.FAILED,
                error_reason=ProviderErrorReason.INVALID_HWND,
                elements=(),
                is_partial=False,
                duration_ms=0.0,
                timeout_occurred=False,
                error_message=f"HWND {hwnd} is invalid or destroyed",
                worker_state="WORKER_EXIT_CONFIRMED",
            )

        elements: List[UIElementObservation] = []
        timed_out = False

        try:
            def enum_cb(child_hwnd, lparam):
                nonlocal timed_out
                if cancellation_event and cancellation_event.is_set():
                    timed_out = True
                    return False

                if user32.IsWindowVisible(child_hwnd):
                    r = wintypes.RECT()
                    user32.GetWindowRect(child_hwnd, ctypes.byref(r))
                    w = r.right - r.left
                    h = r.bottom - r.top
                    if w > 0 and h > 0:
                        buf_class = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(child_hwnd, buf_class, 256)
                        cls_name = buf_class.value

                        buf_text = ctypes.create_unicode_buffer(512)
                        user32.GetWindowTextW(child_hwnd, buf_text, 512)
                        text = buf_text.value

                        is_en = bool(user32.IsWindowEnabled(child_hwnd))
                        rect = Rect(left=r.left, top=r.top, right=r.right, bottom=r.bottom)

                        elem = UIElementObservation(
                            element_id=f"win32_{hwnd}_{child_hwnd}_{len(elements)}",
                            evidence_source=EvidenceSource.WIN32_CONTROL.value,
                            name=text if text else None,
                            role=cls_name,
                            control_type=cls_name,
                            automation_id=f"hwnd_{child_hwnd}",
                            bounds=rect,
                            is_enabled=is_en,
                            is_focused=(user32.GetFocus() == child_hwnd),
                            is_offscreen=False,
                            timestamp_ns=time.perf_counter_ns(),
                            generation_id=generation_id,
                            confidence=ConfidenceLevel.PARTIALLY_CONFIRMED,
                            class_name=cls_name,
                            native_hwnd=child_hwnd,
                        )
                        elements.append(elem)
                return True

            cb = WNDENUMPROC(enum_cb)
            user32.EnumChildWindows(hwnd, cb, 0)

        except Exception as e:
            t1 = time.perf_counter()
            return ProviderResult(
                provider_name="WIN32_CONTROL",
                status=ProviderStatus.PARTIAL_SUCCESS if elements else ProviderStatus.FAILED,
                error_reason=ProviderErrorReason.PROVIDER_EXCEPTION,
                elements=tuple(elements),
                is_partial=True,
                duration_ms=round((t1 - t0) * 1000.0, 2),
                timeout_occurred=False,
                error_message=str(e),
                worker_state="WORKER_EXIT_CONFIRMED",
            )

        t1 = time.perf_counter()
        duration_ms = round((t1 - t0) * 1000.0, 2)
        if cancellation_event and cancellation_event.is_set():
            timed_out = True

        status = ProviderStatus.SUCCESS if elements and not timed_out else (
            ProviderStatus.PARTIAL_SUCCESS if elements else (
                ProviderStatus.TIMEOUT if timed_out else ProviderStatus.UNAVAILABLE
            )
        )

        return ProviderResult(
            provider_name="WIN32_CONTROL",
            status=status,
            error_reason=ProviderErrorReason.NONE if status in (ProviderStatus.SUCCESS, ProviderStatus.PARTIAL_SUCCESS) else ProviderErrorReason.PROVIDER_UNAVAILABLE,
            elements=tuple(elements),
            is_partial=timed_out or (len(elements) == 0),
            duration_ms=duration_ms,
            timeout_occurred=timed_out,
            error_message=None,
            worker_state="WORKER_EXIT_CONFIRMED",
        )
