# ORBIT Milestone M1.4: Human Takeover Test Matrix

**Milestone**: M1.4 — Production Human Takeover Integration  
**Status**: **TEST MATRIX DEFINED**  
**Date**: September 6, 2026  

---

## 1. Unit Tests

| Test ID | Test Name | Target Module | Description | Expected Outcome |
| :--- | :--- | :--- | :--- | :--- |
| **UT-TKV-1** | `test_classifier_physical_mouse_move` | `classifier.py` | Feed `MSLLHOOKSTRUCT` with `flags=0`, `dwExtraInfo=0` | Classified as `USER_PHYSICAL`, reason `Physical mouse movement` |
| **UT-TKV-2** | `test_classifier_physical_mouse_click` | `classifier.py` | Feed `WM_LBUTTONDOWN` with `flags=0` | Classified as `USER_PHYSICAL`, reason `Physical mouse click` |
| **UT-TKV-3** | `test_classifier_physical_keystroke` | `classifier.py` | Feed `WM_KEYDOWN` with `flags=0` | Classified as `USER_PHYSICAL`, reason `Physical keystroke` |
| **UT-TKV-4** | `test_classifier_orbit_synthetic_mouse` | `classifier.py` | Feed `flags=LLMHF_INJECTED`, `dwExtraInfo=0x08B17001` | Classified as `ORBIT_EXPECTED` (Ignored / No Takeover) |
| **UT-TKV-5** | `test_classifier_orbit_synthetic_keyboard` | `classifier.py` | Feed `flags=LLKHF_INJECTED`, `dwExtraInfo=0x08B17001` | Classified as `ORBIT_EXPECTED` (Ignored / No Takeover) |
| **UT-TKV-6** | `test_classifier_foreign_ambiguous_injection` | `classifier.py` | Feed `flags=LLMHF_INJECTED`, `dwExtraInfo=0x1234` | Classified as `INPUT_AMBIGUOUS` $\to$ Triggers Takeover |
| **UT-TKV-7** | `test_state_machine_valid_lifecycle` | `state.py` | `IDLE` $\to$ `ACTIVE_TASK` $\to$ `TAKEOVER_ACTIVE` $\to$ `RELEASE_PENDING` $\to$ `IDLE` | All transitions succeed |
| **UT-TKV-8** | `test_state_machine_invalid_transitions` | `state.py` | Attempt invalid jump from `STOPPED` to `RELEASE_PENDING` | Raises `StateTransitionError` |
| **UT-TKV-9** | `test_state_machine_quiet_period_timer` | `state.py` | Verify 1000ms inactivity transitions from `TAKEOVER_ACTIVE` to `RELEASE_PENDING` | State becomes `RELEASE_PENDING` |
| **UT-TKV-10** | `test_state_machine_duplicate_takeover_dedup` | `state.py` | Feed multiple takeover triggers in rapid succession ($<1\text{ ms}$) | Only first triggers state transition; timer refreshed |
| **UT-TKV-11** | `test_cancellation_idempotency` | `runtime/cancellation.py` | Call `CancellationSource.cancel()` multiple times | Safe idempotent behavior |
| **UT-TKV-12** | `test_telemetry_latency_aggregation` | `telemetry.py` | Log sample latencies and verify min, mean, P95, max calculations | Mathematical accuracy verified |

---

## 2. Integration Tests

| Test ID | Test Name | Target Flow | Description | Expected Outcome |
| :--- | :--- | :--- | :--- | :--- |
| **IT-TKV-1** | `test_takeover_cancels_active_task` | `Orchestrator + Takeover` | Active task running; takeover event triggered | Active task cancelled; system state becomes `HUMAN_TAKEOVER_ACTIVE` |
| **IT-TKV-2** | `test_takeover_during_pointer_movement` | `Pointer + Takeover` | Cursor moving; takeover event triggered before dispatch | Movement returns `CANCELLED_BEFORE_DISPATCH`; 0 SendInput |
| **IT-TKV-3** | `test_takeover_during_pointer_click_dwell` | `Pointer + Takeover` | Button DOWN dispatched, dwelling; takeover triggered | `emergency_sanitize()` releases button; logs `CANCELLED_DURING_DWELL_SANITIZED` |
| **IT-TKV-4** | `test_takeover_during_keyboard_text_typing` | `Keyboard + Takeover` | Typing multi-character string; takeover triggered | Loop stops immediately; `finally:` block sanitizes all keys |
| **IT-TKV-5** | `test_takeover_during_keyboard_shortcut` | `Keyboard + Takeover` | Modifiers DOWN, action key pending; takeover triggered | Modifiers released in reverse order; 0 stuck modifier keys |
| **IT-TKV-6** | `test_global_emergency_safety_stop` | `SafetyCoordinator` | Invoking `emergency_stop_all()` during takeover | Both pointer and keyboard adapters have `emergency_release_all()` called |
| **IT-TKV-7** | `test_takeover_operator_release_flow` | `Orchestrator + Gateway` | System in `HUMAN_TAKEOVER_ACTIVE`; operator sends `RELEASE_TAKEOVER` | System transitions back to `IDLE` |
| **IT-TKV-8** | `test_takeover_hook_lifecycle` | `NativeInputMonitor` | Initialize adapter $\to$ start monitoring $\to$ stop monitoring $\to$ shutdown | Zero resource or thread leaks |

---

## 3. Controlled Live Windows Tests

*Note: These tests execute against dedicated test windows on Windows 11 AMD64.*

| Test ID | Test Name | Target OS Mechanism | Description | Verification Boundary |
| :--- | :--- | :--- | :--- | :--- |
| **LIVE-TKV-1** | `test_live_hook_installation` | Win32 `SetWindowsHookExW` | Install `WH_MOUSE_LL` and `WH_KEYBOARD_LL` on background thread | Hook handles are non-null; thread message pump runs |
| **LIVE-TKV-2** | `test_live_orbit_synthetic_pointer_bypass` | Win32 `SendInput` + Hook | Dispatch synthetic mouse move tagged with `0x08B17001` | Hook receives event; identifies `ORBIT_EXPECTED`; does NOT trigger takeover |
| **LIVE-TKV-3** | `test_live_orbit_synthetic_keyboard_bypass` | Win32 `SendInput` + Hook | Dispatch synthetic key press tagged with `0x08B17001` | Hook receives event; identifies `ORBIT_EXPECTED`; does NOT trigger takeover |
| **LIVE-TKV-4** | `test_live_preemption_and_sanitization` | Live Hardware Preemption | Inject un-tagged event during simulated action | Takeover fires in $<2\text{ ms}$; held keys released; state locked |
| **LIVE-TKV-5** | `test_live_clean_unhook_on_shutdown` | Win32 `UnhookWindowsHookEx` | Stop monitor and verify hook uninstallation | Hooks uninstalled; message pump terminates; thread joined cleanly |

---

## 4. Test Matrix Summary

- **Total Planned Unit Tests**: 12
- **Total Planned Integration Tests**: 8
- **Total Planned Live Windows Tests**: 5
- **Total M1.4 Test Suite**: 25 tests
