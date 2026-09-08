"""
Accessibility Observation Coordinator for ORBIT Prototype D v1.3.1.
Coordinates independent Win32Control, MSAA, and UIAutomation providers with soft-timeout watchdogs,
health management, circuit-breaker quarantine, and partial-result retention.
"""

import threading
import time
import ctypes
from typing import List, Tuple, Dict, Any, Optional

from app_types import (
    UIElementObservation,
    ProviderResult,
    ProviderStatus,
    ProviderErrorReason,
    ProviderHealthState,
)
from win32_control_provider import Win32ControlProvider
from msaa_provider import MSAAProvider
from uia_provider import UIAutomationProvider
from provider_health import ProviderWorkerHealthManager

from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
ole32 = ctypes.windll.ole32
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
if hasattr(user32, "OpenInputDesktop"):
    user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
    user32.SetThreadDesktop.restype = wintypes.BOOL
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.CloseDesktop.restype = wintypes.BOOL


class AccessibilityCoordinator:
    """
    Coordinates independent accessibility providers, managing watchdog soft timeouts,
    source separation, and health circuit breakers.
    """

    def __init__(self, timeout_ms: float = 1000.0, quarantine_threshold: int = 3):
        self.timeout_ms = timeout_ms
        self.uia_provider = UIAutomationProvider()
        self.win32_provider = Win32ControlProvider()
        self.msaa_provider = MSAAProvider()
        self.health_manager = ProviderWorkerHealthManager(quarantine_threshold=quarantine_threshold)

    def collect_accessibility_observations(
        self,
        hwnd: int,
        generation_id: int = 0,
        custom_timeout_ms: Optional[float] = None,
        enabled_providers: Optional[Tuple[str, ...]] = None,
    ) -> Tuple[Tuple[UIElementObservation, ...], Tuple[ProviderResult, ...]]:
        """
        Dispatches UIAutomation, Win32Control, and MSAA providers independently with watchdog soft timeouts.
        Returns (merged_element_tuple, provider_results_tuple).
        """
        timeout_limit = custom_timeout_ms if custom_timeout_ms is not None else self.timeout_ms
        provider_results: List[ProviderResult] = []
        all_elements: List[UIElementObservation] = []

        all_provider_instances = [
            ("UI_AUTOMATION", self.uia_provider),
            ("WIN32_CONTROL", self.win32_provider),
            ("MSAA", self.msaa_provider),
        ]

        if enabled_providers:
            providers = [p for p in all_provider_instances if p[0] in enabled_providers]
        else:
            providers = all_provider_instances

        # Check thread affinity: same-thread HWND must execute in-thread to avoid message queue deadlock
        win_tid = user32.GetWindowThreadProcessId(hwnd, None) if hwnd else 0
        cur_tid = kernel32.GetCurrentThreadId()
        is_same_thread = (win_tid == cur_tid and win_tid != 0)

        for name, provider in providers:
            # If UI_AUTOMATION already produced high-confidence elements, skip legacy MSAA
            if name == "MSAA" and all_elements:
                continue

            # Check circuit breaker quarantine
            if not self.health_manager.is_provider_allowed(name):
                res = ProviderResult(
                    provider_name=name,
                    status=ProviderStatus.UNAVAILABLE,
                    error_reason=ProviderErrorReason.PROVIDER_UNAVAILABLE,
                    elements=(),
                    is_partial=False,
                    duration_ms=0.0,
                    timeout_occurred=False,
                    error_message=f"Provider '{name}' is QUARANTINED due to consecutive timeouts",
                    worker_state="QUARANTINED_SUPPRESSED",
                )
                provider_results.append(res)
                continue

            worker_id = self.health_manager.record_worker_start(name)
            t0 = time.perf_counter()
            try:
                res = provider.traverse_window(
                    hwnd=hwnd,
                    max_depth=5,
                    cancellation_event=None,
                    generation_id=generation_id,
                )
                elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                self.health_manager.record_worker_success(name, worker_id, elapsed_ms)
                provider_results.append(res)
                all_elements.extend(res.elements)
            except Exception as e:
                elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                res_err = ProviderResult(
                    provider_name=name,
                    status=ProviderStatus.FAILED,
                    error_reason=ProviderErrorReason.PROVIDER_EXCEPTION,
                    elements=(),
                    is_partial=False,
                    duration_ms=elapsed_ms,
                    timeout_occurred=False,
                    error_message=str(e),
                    worker_state="WORKER_EXIT_CONFIRMED",
                )
                provider_results.append(res_err)

        return tuple(all_elements), tuple(provider_results)

    observe_window = collect_accessibility_observations
