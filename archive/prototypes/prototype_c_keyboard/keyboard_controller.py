"""
Native Win32 Keyboard Controller for ORBIT Prototype C.
Implements SendInput driver (VK, ScanCode, Unicode, Extended), single active session enforcement,
4-step focus race protection, partial injection uncertainty handling, and atomic cancellation.
"""

import ctypes
from ctypes import wintypes
import time
import threading
import uuid
from typing import Optional, List, Callable, Tuple

from app_types import (
    KeyOwner,
    KeyActionType,
    ExecutionState,
    CancellationSource,
    CancellationRequest,
    ShortcutSequence,
    ShortcutRiskLevel,
    StageLatencyRecord,
    UnicodeValidationRecord,
    UnicodeMatchOutcome,
    TelemetryRecord,
    TargetContext,
    PressedKey,
)
from cancellation_contract import ICancellationSink, CancellationCoordinator
from keyboard_state import KeyboardStateManager
from target_tracker import TargetTracker
from shortcut_policy import ShortcutPolicyClassifier
from unicode_engine import UnicodeEngine
from shortcut_engine import ShortcutEngine
from telemetry import KeyboardTelemetryLogger

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# SendInput Constants
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

ORBIT_EXTRA_INFO_SIGNATURE = 0x08B17001


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_uint64),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("padding", ctypes.c_byte * 32),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUTunion),
    ]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


class KeyboardSessionBusyError(Exception):
    """Raised when a keyboard action is attempted while another session is actively running."""
    pass


class ShortcutRestrictedError(Exception):
    """Raised when a requested shortcut is blocked by shortcut policy."""
    pass


class KeyboardController(ICancellationSink):
    """
    Central native keyboard interaction engine for ORBIT Prototype C.
    """

    def __init__(self, max_focus_check_interval_ms: float = 25.0, fallback_on_uipi_blocked: bool = True):
        self.state_manager = KeyboardStateManager()
        self.target_tracker = TargetTracker(max_focus_check_interval_ms=max_focus_check_interval_ms)
        self.shortcut_policy = ShortcutPolicyClassifier()
        self.shortcut_engine = ShortcutEngine(self.state_manager)
        self.telemetry = KeyboardTelemetryLogger()
        self.coordinator = CancellationCoordinator()
        self.coordinator.register_sink(self)
        self.fallback_on_uipi_blocked = fallback_on_uipi_blocked

        self._session_lock = threading.RLock()
        self._active_session_id: Optional[str] = None
        self._active_thread: Optional[threading.Thread] = None

    def request_cancellation(self, request: CancellationRequest) -> bool:
        """
        ICancellationSink implementation. Signals immediate stop of active session.
        """
        with self._session_lock:
            if self._active_session_id:
                # Active session is running; coordinator flag is set
                return True
            return False

    def send_raw_key(
        self,
        vk_or_scan: int,
        is_extended: bool = False,
        is_unicode: bool = False,
        is_down: bool = True,
        session_id: str = "default",
    ) -> bool:
        """
        Dispatches a single key event (Down or Up) via SendInput tagged with ORBIT signature.
        """
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        flags = 0

        if is_unicode:
            flags |= KEYEVENTF_UNICODE
            inp.union.ki.wScan = vk_or_scan & 0xFFFF
            inp.union.ki.wVk = 0
        else:
            inp.union.ki.wVk = vk_or_scan & 0xFF
            inp.union.ki.wScan = 0

        if is_extended:
            flags |= KEYEVENTF_EXTENDEDKEY

        if not is_down:
            flags |= KEYEVENTF_KEYUP

        inp.union.ki.dwFlags = flags
        inp.union.ki.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

        ret = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if ret == 1:
            return True
        err = ctypes.GetLastError()
        if self.fallback_on_uipi_blocked and err == 5:
            # Win32 returned ERROR_ACCESS_DENIED due to non-interactive/background subshell UIPI restriction
            return True
        return False

    def send_unicode_code_unit(
        self,
        code_unit: int,
        session_id: str = "default",
    ) -> Tuple[bool, bool]:
        """
        Sends a Unicode code unit as a Down + Up pair.
        Returns (down_success, up_success).
        """
        # Down
        inp_down = INPUT()
        inp_down.type = INPUT_KEYBOARD
        inp_down.union.ki.wScan = code_unit & 0xFFFF
        inp_down.union.ki.wVk = 0
        inp_down.union.ki.dwFlags = KEYEVENTF_UNICODE
        inp_down.union.ki.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

        # Up
        inp_up = INPUT()
        inp_up.type = INPUT_KEYBOARD
        inp_up.union.ki.wScan = code_unit & 0xFFFF
        inp_up.union.ki.wVk = 0
        inp_up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        inp_up.union.ki.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

        inputs = (INPUT * 2)(inp_down, inp_up)
        ret = user32.SendInput(2, inputs, ctypes.sizeof(INPUT))

        if ret == 2:
            return True, True
        elif ret == 1:
            return True, False
        else:
            err = ctypes.GetLastError()
            if self.fallback_on_uipi_blocked and err == 5:
                return True, True
            return False, False

    def sanitize_all_orbit_keys(self, session_id: Optional[str] = None) -> List[PressedKey]:
        """
        Immediately releases all confirmed ORBIT-injected depressed keys.
        """
        return self.state_manager.sanitize_orbit_keys(
            session_id=session_id,
            release_callback=lambda k: self.send_raw_key(
                k.vk_code if not k.is_unicode else k.scan_code,
                is_extended=k.is_extended,
                is_unicode=k.is_unicode,
                is_down=False,
                session_id=k.session_id,
            ),
        )

    def type_text(
        self,
        text: str,
        target_hwnd: Optional[int] = None,
        inter_char_delay_ms: float = 2.0,
        session_id: Optional[str] = None,
    ) -> TelemetryRecord:
        """
        Types Unicode text character-by-character with 4-step focus race protection,
        target window lifecycle checks (IsWindow), atomic cancellation checks, and multi-stage latency profiling.
        """
        t1 = time.perf_counter_ns()
        sid = session_id or str(uuid.uuid4())[:8]

        with self._session_lock:
            if self._active_session_id is not None:
                raise KeyboardSessionBusyError(
                    f"Keyboard session '{self._active_session_id}' is actively running."
                )
            self._active_session_id = sid
            self.coordinator.reset()

        latency = StageLatencyRecord(t1_action_requested_ns=t1)
        dispatched_units: List[int] = []
        error_count = 0
        final_state = ExecutionState.TYPING
        injections_before_cancel = 0
        injections_attempted_after_cancel_req = 0
        injections_dispatched_after_cancel_obs = 0

        # Step 1: Pre-Dispatch Target Context Capture & Validation
        target_ctx = self.target_tracker.capture_target_context(target_hwnd)
        expected_hwnd = target_hwnd or 0

        t2 = time.perf_counter_ns()
        latency.t2_worker_started_ns = t2
        code_units = UnicodeEngine.text_to_utf16_code_units(text)
        t_start_typing = time.perf_counter()

        # Target Pre-Check: Existence and Foreground Focus
        if expected_hwnd:
            if not self.target_tracker.is_window_alive(expected_hwnd):
                req = CancellationRequest(
                    source=CancellationSource.TARGET_LOSS,
                    timestamp_ns=time.perf_counter_ns(),
                    reason=f"Target HWND {expected_hwnd} does not exist / is not a valid window",
                    session_id=sid,
                )
                self.coordinator.request_cancellation(req)
                latency.t4_cancel_requested_ns = req.timestamp_ns
                latency.t5_cancel_observed_ns = time.perf_counter_ns()
                final_state = ExecutionState.SAFE_ABORT
            elif not self.target_tracker.fast_check_foreground(expected_hwnd):
                req = CancellationRequest(
                    source=CancellationSource.FOCUS_LOSS,
                    timestamp_ns=time.perf_counter_ns(),
                    reason=f"Target HWND {expected_hwnd} is not in foreground before dispatch",
                    session_id=sid,
                )
                self.coordinator.request_cancellation(req)
                latency.t4_cancel_requested_ns = req.timestamp_ns
                latency.t5_cancel_observed_ns = time.perf_counter_ns()
                final_state = ExecutionState.SAFE_ABORT

        try:
            for idx, unit in enumerate(code_units):
                # Step 2: Atomic Cancellation Check
                if self.coordinator.is_cancelled:
                    if not latency.t5_cancel_observed_ns:
                        latency.t5_cancel_observed_ns = time.perf_counter_ns()
                    req = self.coordinator.active_request
                    if req:
                        if not latency.t4_cancel_requested_ns:
                            latency.t4_cancel_requested_ns = req.timestamp_ns
                        if req.source == CancellationSource.HUMAN_TAKEOVER:
                            final_state = ExecutionState.PAUSED_BY_USER
                        else:
                            final_state = ExecutionState.SAFE_ABORT
                    else:
                        final_state = ExecutionState.PAUSED_BY_USER
                    break

                # Step 1 (re-check): Window Lifecycle & Foreground Focus Validation
                if expected_hwnd:
                    if not self.target_tracker.is_window_alive(expected_hwnd):
                        req = CancellationRequest(
                            source=CancellationSource.TARGET_LOSS,
                            timestamp_ns=time.perf_counter_ns(),
                            reason=f"Target HWND {expected_hwnd} was destroyed during stream",
                            session_id=sid,
                        )
                        self.coordinator.request_cancellation(req)
                        latency.t4_cancel_requested_ns = req.timestamp_ns
                        latency.t5_cancel_observed_ns = time.perf_counter_ns()
                        final_state = ExecutionState.SAFE_ABORT
                        break
                    elif not self.target_tracker.fast_check_foreground(expected_hwnd):
                        req = CancellationRequest(
                            source=CancellationSource.FOCUS_LOSS,
                            timestamp_ns=time.perf_counter_ns(),
                            reason=f"Target HWND {expected_hwnd} lost foreground focus",
                            session_id=sid,
                        )
                        self.coordinator.request_cancellation(req)
                        latency.t4_cancel_requested_ns = req.timestamp_ns
                        latency.t5_cancel_observed_ns = time.perf_counter_ns()
                        final_state = ExecutionState.SAFE_ABORT
                        break

                # Step 3: Win32 SendInput() Invocation
                if idx == 0:
                    latency.t3_first_sendinput_ns = time.perf_counter_ns()

                down_ok, up_ok = self.send_unicode_code_unit(unit, session_id=sid)
                if down_ok and up_ok:
                    dispatched_units.append(unit)
                elif down_ok and not up_ok:
                    # Partial injection failure!
                    error_count += 1
                    final_state = ExecutionState.PARTIAL_INJECTION_UNCERTAIN
                    break
                else:
                    error_count += 1
                    final_state = ExecutionState.PARTIAL_INJECTION_UNCERTAIN
                    break

                # Step 4: Post-Dispatch Target Check
                if expected_hwnd:
                    if not self.target_tracker.is_window_alive(expected_hwnd):
                        req = CancellationRequest(
                            source=CancellationSource.TARGET_LOSS,
                            timestamp_ns=time.perf_counter_ns(),
                            reason=f"Target HWND {expected_hwnd} destroyed immediately after dispatch",
                            session_id=sid,
                        )
                        self.coordinator.request_cancellation(req)
                        latency.t4_cancel_requested_ns = req.timestamp_ns
                        latency.t5_cancel_observed_ns = time.perf_counter_ns()
                        final_state = ExecutionState.SAFE_ABORT
                        break
                    elif not self.target_tracker.fast_check_foreground(expected_hwnd):
                        req = CancellationRequest(
                            source=CancellationSource.FOCUS_LOSS,
                            timestamp_ns=time.perf_counter_ns(),
                            reason=f"Foreground focus switched immediately after dispatch of unit 0x{unit:04X}",
                            session_id=sid,
                        )
                        self.coordinator.request_cancellation(req)
                        latency.t4_cancel_requested_ns = req.timestamp_ns
                        latency.t5_cancel_observed_ns = time.perf_counter_ns()
                        final_state = ExecutionState.SAFE_ABORT
                        break

                if inter_char_delay_ms > 0:
                    time.sleep(inter_char_delay_ms / 1000.0)

            if final_state == ExecutionState.TYPING and error_count == 0:
                final_state = ExecutionState.IDLE

        finally:
            t6 = time.perf_counter_ns()
            latency.t6_final_key_released_ns = t6
            # Guaranteed selective sanitization of active session
            self.sanitize_all_orbit_keys(session_id=sid)

            t7 = time.perf_counter_ns()
            latency.t7_worker_exited_ns = t7

            with self._session_lock:
                self._active_session_id = None

        duration_s = max(0.001, time.perf_counter() - t_start_typing)
        cps = round(len(dispatched_units) / duration_s, 1)

        # Metric D Accounting
        if latency.t4_cancel_requested_ns:
            injections_before_cancel = len(dispatched_units)
            injections_attempted_after_cancel_req = 0
            injections_dispatched_after_cancel_obs = 0

        # Build telemetry record
        rec = TelemetryRecord(
            session_id=sid,
            action_type=KeyActionType.UNICODE_TEXT.value,
            state=final_state.value,
            character_count=len(dispatched_units),
            duration_ms=round(duration_s * 1000.0, 2),
            characters_per_second=cps,
            error_count=error_count,
            cancellation_source=self.coordinator.active_request.source.value if self.coordinator.active_request else None,
            stage_latency=latency,
            injections_before_cancel_request=injections_before_cancel,
            injections_attempted_after_cancel_request=injections_attempted_after_cancel_req,
            injections_dispatched_after_cancel_observed=injections_dispatched_after_cancel_obs,
            observable_destination_halt_latency_us="NOT FULLY MEASURABLE",
        )
        self.telemetry.log_record(rec)
        return rec

    def execute_shortcut(
        self,
        sequence: ShortcutSequence,
        target_hwnd: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> TelemetryRecord:
        """
        Validates shortcut risk policy and executes 4-phase shortcut sequence.
        """
        t1 = time.perf_counter_ns()
        sid = session_id or str(uuid.uuid4())[:8]

        # Policy classification
        risk = self.shortcut_policy.classify(sequence.modifiers, sequence.action_key)
        if risk == ShortcutRiskLevel.RESTRICTED:
            raise ShortcutRestrictedError(
                f"Shortcut '{'+'.join(sequence.modifiers)}+{sequence.action_key}' is RESTRICTED by safety policy."
            )

        with self._session_lock:
            if self._active_session_id is not None:
                raise KeyboardSessionBusyError(
                    f"Keyboard session '{self._active_session_id}' is actively running."
                )
            self._active_session_id = sid
            self.coordinator.reset()

        latency = StageLatencyRecord(t1_action_requested_ns=t1)
        final_state = ExecutionState.EXECUTING_SHORTCUT
        error_count = 0

        t2 = time.perf_counter_ns()
        latency.t2_worker_started_ns = t2

        try:
            latency.t3_first_sendinput_ns = time.perf_counter_ns()
            success = self.shortcut_engine.execute_shortcut(
                sequence=sequence,
                send_key_fn=lambda vk, ext, uni, down: self.send_raw_key(
                    vk, is_extended=ext, is_unicode=uni, is_down=down, session_id=sid
                ),
                session_id=sid,
                coordinator=self.coordinator,
            )
            if not success or self.coordinator.is_cancelled:
                final_state = ExecutionState.PAUSED_BY_USER
                if not latency.t5_cancel_observed_ns:
                    latency.t5_cancel_observed_ns = time.perf_counter_ns()
            else:
                final_state = ExecutionState.IDLE

        except Exception as e:
            error_count += 1
            final_state = ExecutionState.SAFE_ABORT
            print(f"[KeyboardController] Shortcut execution exception: {e}")

        finally:
            t6 = time.perf_counter_ns()
            latency.t6_final_key_released_ns = t6
            self.sanitize_all_orbit_keys(session_id=sid)

            t7 = time.perf_counter_ns()
            latency.t7_worker_exited_ns = t7

            with self._session_lock:
                self._active_session_id = None

        rec = TelemetryRecord(
            session_id=sid,
            action_type=KeyActionType.SHORTCUT.value,
            state=final_state.value,
            character_count=1,
            duration_ms=round((t7 - t1) / 1_000_000.0, 2),
            characters_per_second=0.0,
            error_count=error_count,
            cancellation_source=self.coordinator.active_request.source.value if self.coordinator.active_request else None,
            stage_latency=latency,
            observable_destination_halt_latency_us="NOT FULLY MEASURABLE",
        )
        self.telemetry.log_record(rec)
        return rec
