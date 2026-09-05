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

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = ctypes.c_ulong


class AccessibilityCoordinator:
    """
    Coordinates independent accessibility providers, managing watchdog soft timeouts,
    source separation, and health circuit breakers.
    """

    def __init__(self, timeout_ms: float = 150.0, quarantine_threshold: int = 3):
        self.timeout_ms = timeout_ms
        self.win32_provider = Win32ControlProvider()
        self.msaa_provider = MSAAProvider()
        self.uia_provider = UIAutomationProvider()
        self.health_manager = ProviderWorkerHealthManager(quarantine_threshold=quarantine_threshold)

    def collect_accessibility_observations(
        self,
        hwnd: int,
        generation_id: int = 0,
        custom_timeout_ms: Optional[float] = None,
        enabled_providers: Optional[Tuple[str, ...]] = None,
    ) -> Tuple[Tuple[UIElementObservation, ...], Tuple[ProviderResult, ...]]:
        """
        Dispatches Win32Control, MSAA, and UIA providers independently with watchdog soft timeouts.
        Returns (merged_element_tuple, provider_results_tuple).
        """
        timeout_limit = custom_timeout_ms if custom_timeout_ms is not None else self.timeout_ms
        provider_results: List[ProviderResult] = []
        all_elements: List[UIElementObservation] = []

        all_provider_instances = [
            ("WIN32_CONTROL", self.win32_provider),
            ("MSAA", self.msaa_provider),
            ("UI_AUTOMATION", self.uia_provider),
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
            # Check circuit breaker quarantine
            if not self.health_manager.is_provider_allowed(name):
                # Quarantined due to repeated unresolved timeouts
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

            if is_same_thread:
                # Direct in-thread execution prevents Win32 message-queue deadlock on local GUI thread
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
                continue

            result_container: List[ProviderResult] = []
            cancel_event = threading.Event()

            def worker_fn():
                try:
                    ole32.CoInitialize(None)
                except Exception:
                    pass
                try:
                    res = provider.traverse_window(
                        hwnd=hwnd,
                        max_depth=5,
                        cancellation_event=cancel_event,
                        generation_id=generation_id,
                    )
                    result_container.append(res)
                except Exception as e:
                    res_err = ProviderResult(
                        provider_name=name,
                        status=ProviderStatus.FAILED,
                        error_reason=ProviderErrorReason.PROVIDER_EXCEPTION,
                        elements=(),
                        is_partial=False,
                        duration_ms=0.0,
                        timeout_occurred=False,
                        error_message=str(e),
                        worker_state="WORKER_EXIT_CONFIRMED",
                    )
                    result_container.append(res_err)
                finally:
                    try:
                        ole32.CoUninitialize()
                    except Exception:
                        pass

            t = threading.Thread(target=worker_fn, daemon=True)
            t_start = time.perf_counter()
            t.start()
            t.join(timeout=timeout_limit / 1000.0)
            elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

            if t.is_alive():
                # SOFT TIMEOUT REACHED
                cancel_event.set()
                self.health_manager.record_worker_timeout(name, worker_id, elapsed_ms)

                # If partial nodes were populated
                partial_elems = result_container[0].elements if result_container else ()
                res_timeout = ProviderResult(
                    provider_name=name,
                    status=ProviderStatus.PARTIAL_SUCCESS if partial_elems else ProviderStatus.TIMEOUT,
                    error_reason=ProviderErrorReason.NONE,
                    elements=partial_elems,
                    is_partial=True,
                    duration_ms=elapsed_ms,
                    timeout_occurred=True,
                    error_message=f"Soft timeout exceeded ({elapsed_ms:.1f}ms > {timeout_limit}ms); worker abandoned",
                    worker_state="WORKER_STILL_ACTIVE",
                )
                provider_results.append(res_timeout)
                all_elements.extend(partial_elems)
            else:
                # Clean worker completion
                self.health_manager.record_worker_success(name, worker_id, elapsed_ms)
                if result_container:
                    res_ok = result_container[0]
                    provider_results.append(res_ok)
                    all_elements.extend(res_ok.elements)
                else:
                    res_empty = ProviderResult(
                        provider_name=name,
                        status=ProviderStatus.UNAVAILABLE,
                        error_reason=ProviderErrorReason.PROVIDER_UNAVAILABLE,
                        elements=(),
                        is_partial=False,
                        duration_ms=elapsed_ms,
                        timeout_occurred=False,
                        error_message="Worker returned empty container",
                        worker_state="WORKER_EXIT_CONFIRMED",
                    )
                    provider_results.append(res_empty)

        return tuple(all_elements), tuple(provider_results)

    observe_window = collect_accessibility_observations
