# ORBIT Milestone M1.3: Production Keyboard Capability Integration Completion Report

**Milestone**: M1.3 — Production Keyboard Capability Integration  
**Status**: **COMPLETE**  
**Date**: September 6, 2026  
**Environment**: Windows 11 AMD64 (Build 26200), Python 3.13.7  
**Baseline Commit**: `ca87ef8`

---

## 1. Components Integrated from Prototype C

The proven capabilities from Prototype C were selectively adapted and integrated into ORBIT production architecture:

1. **Unicode Engine (`UnicodeEngine`)**:
   - Integrated directly under `src/orbit/adapters/keyboard/unicode.py`.
   - Handles full UTF-16 code unit decomposition, surrogate pairs for non-BMP code points (emojis, mathematical symbols), and variation selectors for `KEYEVENTF_UNICODE` in `wScan`.
   - Evaluates exact vs NFC canonical equivalence between requested and observed text.

2. **Shortcut Policy & 4-Phase Shortcut Engine (`ShortcutPolicy`, `ShortcutExecutor`)**:
   - Integrated under `src/orbit/adapters/keyboard/shortcuts.py`.
   - Implements 3-tier risk classification: `ALLOWED`, `RESTRICTED`, and `MANUAL_CONTROLLED_ONLY`.
   - Implements deterministic 4-phase transaction lifecycle:
     - Phase 1: Modifiers DOWN
     - Phase 2: Action Key DOWN
     - Phase 3: Action Key UP
     - Phase 4: Modifiers UP (in reverse order of injection)
   - Guarantees immediate, safe modifier sanitization if any step is cancelled or fails.

3. **Synthetic Key State Management (`KeyboardStateManager`)**:
   - Integrated under `src/orbit/adapters/keyboard/state.py`.
   - Distinguishes `ORBIT_SYNTHETIC` vs unknown external physical key states.
   - Fail-closed transitions to `UNRESOLVED_LOCKED` upon unconfirmed key release ($M=0$).
   - Administrative recovery token protocol for lockout resolution.

4. **Single Authoritative Native Dispatch Gateway (`NativeKeyboardDispatchGateway`)**:
   - Integrated under `src/orbit/adapters/keyboard/dispatch.py`.
   - Single point of native Win32 `SendInput` execution.
   - Enforces 64-bit AMD64 ABI layout (`KEYBDINPUT`, `INPUT`).
   - Dispatches structured single-key packets and atomic Unicode code unit pairs (DOWN + UP).
   - Captures Win32 error codes (`GetLastError`), timing telemetry, and increments `ActionCounter`.

5. **Target / Focus Validation (`TargetFocusValidator`)**:
   - Integrated under `src/orbit/adapters/keyboard/focus.py`.
   - Checks `IsWindow(hwnd)`, `GetForegroundWindow()`, and process ID verification to guard against focus drift during keystroke streaming.

6. **Streaming Text Typing Executor (`TextTypingExecutor`)**:
   - Integrated under `src/orbit/adapters/keyboard/text.py`.
   - Streams Unicode code points character-by-character with configurable inter-key dwell delays, pre-character cancellation checks, and optional focus validation.

---

## 2. Components Intentionally Not Integrated

1. **Clipboard Preserver / Paste Fallback (`clipboard_preserver.py`)**:
   - **EXCLUDED BY DESIGN**: ORBIT architecture strictly prohibits silent clipboard modification for typing. All text input must flow through native Unicode keystroke injection (`KEYEVENTF_UNICODE`). If clipboard access is needed in future milestones, it will be exposed as an explicit, separate, authorized clipboard capability.
2. **Prototype Cancellation Contract (`cancellation_contract.py`)**:
   - **EXCLUDED**: Superseded by ORBIT core `CancellationToken` and `CancellationSource` hierarchy in `src/orbit/infrastructure/cancellation.py`.
3. **Standalone UI / Prototype Runners (`prototype_ui.py`, `prototype_c_keyboard/*.py`)**:
   - **EXCLUDED**: Prototype C remains frozen at `ca87ef8`. All production validation is integrated into `tests/` and runtime gateway.

---

## 3. Final Production Architecture

```
src/orbit/adapters/keyboard/
├── __init__.py           # Package exports (ProductionKeyboardAdapter, NativeKeyboardDispatchGateway, etc.)
├── adapter.py            # ProductionKeyboardAdapter implementing BaseCapabilityAdapter & KeyboardCapability
├── dispatch.py           # NativeKeyboardDispatchGateway (single authoritative SendInput gateway)
├── focus.py              # TargetFocusValidator (Win32 HWND, PID, and foreground validation)
├── safety.py             # AMD64 ctypes Win32 ABI structs, KeyboardAbiGate, virtual key maps, desktop attachment
├── shortcuts.py          # ShortcutPolicy (risk classifier) & ShortcutExecutor (4-phase modifier engine)
├── state.py              # KeyboardStateManager (ownership tracking, fail-closed lockout, recovery tokens)
├── text.py               # TextTypingExecutor (streaming character injection with cancellation & focus check)
└── unicode.py            # UnicodeEngine (UTF-16 decomposition & canonical match evaluation)
```

The production keyboard adapter connects to:
- **Capability Registry** (`CapabilityRegistry`)
- **Runtime Orchestrator** (`OrbitOrchestrator`)
- **Event Bus** (`EventBus` emitting `KEYBOARD_TYPED`, `SHORTCUT_EXECUTED`, `KEYBOARD_KEY_STATE_CHANGED`, `KEYBOARD_LOCKOUT_CHANGED`)
- **FastAPI / WebSocket Gateway** (`WebSocketManager` routing typed keyboard commands)
- **Session Lifecycle** (Safe sanitization of ORBIT-owned keys on client disconnect)

---

## 4. Native Dispatch Model

All keyboard injection flows exclusively through `NativeKeyboardDispatchGateway`:
- **Single Gate Invariant**: No direct `user32.SendInput` calls exist anywhere else in the production codebase.
- **ABI Gate Verification**: Verifies `sizeof(KEYBDINPUT) == 24`, `sizeof(INPUT) == 40`, and field alignments before permitting any injection.
- **Typed Dispatch Result**: Returns `KeyboardDispatchResult(requested=N, accepted=M, win32_error=err, elapsed_ms=t)`:
  - If $M = N$: Dispatch accepted.
  - If $M = 0$: Dispatch rejected (e.g., UIPI / desktop isolation / invalid parameters).
  - If $0 < M < N$: Partial dispatch (unresolved fail-closed state entered).
- **Telemetry**: Increments `ActionCounter.increment_sendinput(M)` for every accepted packet.

---

## 5. Keyboard State and Ownership Model

- **Explicit Synthetic Key Tracking**: `KeyboardStateManager` tracks only keys synthetically pressed by ORBIT (`KeyOwnership.ORBIT_SYNTHETIC`).
- **No Physical Key Assumption**: ORBIT never assumes knowledge of physical user key switches.
- **Fail-Closed Unresolved State**: If any key release ($M=0$) fails or encounters an exception, the state manager enters `UNRESOLVED_LOCKED`. In this locked state:
  - All subsequent keyboard transactions are immediately rejected.
  - An administrative recovery token is generated.
  - The adapter's health status drops to `DEGRADED` / `FAILED`.
  - Lockout can only be cleared via `recover_locked_state(token)` or emergency sanitization.

---

## 6. Modifier Transaction Safety Model

`ShortcutExecutor` implements the strict 4-phase modifier transaction lifecycle:
- **Phase 1 (Modifiers DOWN)**: Injects modifier keys (e.g., `CTRL`, `ALT`, `SHIFT`, `WIN`). Recorded as `ORBIT_SYNTHETIC`.
- **Phase 2 (Action DOWN)**: Injects the target non-modifier key (e.g., `C`, `V`, `T`).
- **Phase 3 (Action UP)**: Injects action key release.
- **Phase 4 (Modifiers UP)**: Releases modifier keys in **reverse order** of press.
- **Cancellation & Failure Handling**: If cancellation occurs or native dispatch fails at any phase, all currently held ORBIT modifiers are immediately sanitized. If sanitization fails, the state transitions to `UNRESOLVED_LOCKED`.

---

## 7. Shortcut Policy

`ShortcutPolicy` enforces a strict 3-tier security classification:
- **ALLOWED**: Common, safe application shortcuts (e.g., `ctrl+c`, `ctrl+v`, `ctrl+x`, `ctrl+z`, `ctrl+y`, `ctrl+a`, `ctrl+s`, `ctrl+f`, `ctrl+t`, `ctrl+w`, `ctrl+n`, `ctrl+shift+t`, `alt+left`, `alt+right`).
- **RESTRICTED**: Potentially disruptive window/tab navigation shortcuts (e.g., `alt+tab`, `alt+escape`, `win+tab`, `ctrl+tab`). Accessible only with explicit operator authorization.
- **MANUAL_CONTROLLED_ONLY / DENIED**: Destructive system shortcuts (e.g., `win+l` lock screen, `alt+f4` terminate window, `ctrl+alt+delete`, `win+d` minimize all, `ctrl+shift+escape` task manager). **Strictly blocked** from automated or remote WebSocket dispatch.

---

## 8. Unicode / Text Input Strategy

- **Native Unicode Injection**: All text typing uses `KEYEVENTF_UNICODE` in `wScan` with `wVk = 0`.
- **No Locale Dependency**: `KEYEVENTF_UNICODE` bypasses the host keyboard layout (QWERTY, AZERTY, Dvorak, etc.), delivering exact Unicode characters directly to the target application's message queue.
- **Surrogate Pair Decomposition**: Characters with code points $> 0xFFFF$ (such as emojis `😀`, `🚀`, `🎉`) are decomposed into high and low UTF-16 surrogates (`(high_down, high_up), (low_down, low_up)`).
- **Zero Clipboard Pollution**: Does not touch, alter, or rely on the system clipboard.

---

## 9. Focus Verification Model

`TargetFocusValidator` provides multi-stage focus checking:
- `is_valid_target(hwnd)`: Verifies window handle existence using `user32.IsWindow(hwnd)`.
- `is_target_foreground(hwnd)`: Verifies `GetForegroundWindow() == hwnd` (or parent/owner relationship).
- `verify_target(hwnd, expected_pid)`: Verifies HWND existence, foreground status, and PID matching to guard against recycled HWNDs.
- **Honest Evidence Boundaries**: The adapter acknowledges that User32 `SendInput` injects into the active input queue of the current foreground thread. Passing focus validation does not guarantee that the target UI control inside the window accepts text.

---

## 10. Cancellation and Emergency Cleanup Behavior

- **Pre-Dispatch Checks**: `cancellation_token.is_cancelled()` is checked before every key press, text character, and shortcut phase.
- **Emergency Sanitization**: `emergency_release_all()` iterates through all tracked `ORBIT_SYNTHETIC` keys and dispatches `KEYEVENTF_KEYUP`.
- **Session Disconnect Cleanup**: When a WebSocket client disconnects or session is terminated, `WebSocketManager.disconnect()` and `SessionManager` invoke `emergency_release_all()` on the keyboard adapter to ensure zero stuck synthetic keys.

---

## 11. Desktop / Thread Context Findings

Following the evidence-driven protocol:
- `ensure_thread_input_desktop()` is available in `src/orbit/adapters/keyboard/safety.py` and `src/orbit/adapters/pointer/safety.py`.
- Native `SendInput` on Windows 11 executes reliably from asyncio worker threads (`asyncio.to_thread`) when attached to the active input desktop.
- Classification: **LIVE_OS_VALIDATED**.

---

## 12. Live Windows Validation Evidence

Live validation was executed against dedicated controlled test targets (`test_keyboard_live_validation.py`):
1. **ASCII and Multilingual Typing**: Verified live typing of English, accented, and non-BMP emoji characters (`Hello World! 🚀 123`).
2. **Shortcut Dispatch**: Verified live execution of allowlisted shortcut `ctrl+a` and `ctrl+c`.
3. **Cancellation Resilience**: Verified that cancellation during multi-character typing cleanly stops execution and leaves 0 held keys.
4. **Emergency Sanitization**: Verified that synthetic key down followed by `emergency_release_all()` clears all held keys without affecting physical state.

---

## 13. Remaining Windows Platform Limitations

1. **UAC / Elevated Windows (UIPI)**: Keystroke injection from a non-elevated ORBIT process to an elevated (Administrator) window will be rejected by Windows UIPI ($M=0$, `GetLastError` returning `ERROR_ACCESS_DENIED`). This is safely reported as an unrecoverable action failure.
2. **Secure Desktop (Winlogon / UAC Prompts / Lock Screen)**: `SendInput` cannot inject keystrokes into the Secure Desktop.
3. **DirectX / RawInput Applications**: Games or low-level input readers using raw input or DirectInput may ignore `KEYEVENTF_UNICODE` packets.

---

## 14. Exact Test Counts

| Test Suite | Total Executed | Passed | Failed | Status |
| :--- | :---: | :---: | :---: | :---: |
| **ORBIT Production Pytest Suite** | **152** | **152** | **0** | **PASS** |
| **Prototype C Formal Acceptance Suite (C1–C14)** | **14** | **14** | **0** | **PASS** |
| **Prototype E Phase 2C Validation Suite** | **71** | **71** | **0** | **PASS** |
| **Prototype D Formal Acceptance Suite (D1–D15)** | **15** | **15** | **0** | **PASS** |

---

## 15. Frozen Prototype Boundary Verification

Verification command:
```powershell
git diff ca87ef8 -- prototypes/prototype_a_workspace/ prototypes/prototype_b_human_takeover/ prototypes/prototype_c_keyboard/ prototypes/prototype_d_observation/
```

**Result**: **0 files modified, 0 lines diff**.  
All four frozen prototypes (A, B, C, D) remain 100% untouched relative to baseline commit `ca87ef8`.

---

## Milestone Verdict

**ORBIT Milestone M1.3 — Production Keyboard Capability Integration is COMPLETE and FULLY VALIDATED.**
