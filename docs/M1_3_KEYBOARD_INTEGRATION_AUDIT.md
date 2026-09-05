# ORBIT Milestone M1.3: Production Keyboard Capability Forensic Integration Audit

## Executive Summary

This audit performs a forensic inspection of **Prototype C (Reliable Keyboard Interaction & Unicode Engine)** relative to the production ORBIT architecture. It establishes the classification, boundaries, and concrete integration plan for building a robust, fail-closed, and safe production keyboard capability under `src/orbit/adapters/keyboard/`.

---

## 1. Prototype C Component Classifications

| Component / File | Classification | Production Role | Key Adaptation Required |
| :--- | :--- | :--- | :--- |
| `unicode_engine.py` | **DIRECTLY_REUSABLE** | UTF-16 code unit decomposition & surrogate handling | Package cleanly under `src/orbit/adapters/keyboard/unicode.py` |
| `shortcut_policy.py` | **REQUIRES_ADAPTATION** | Shortcut risk classification & system allowlist | Formalize production allowlist, integrate with command validation & error types |
| `keyboard_state.py` | **REQUIRES_ADAPTATION** | 3-tier key ownership tracker & selective sanitization | Integrate with ORBIT `UNRESOLVED_LOCKED` state machine and token recovery |
| `shortcut_engine.py` | **REQUIRES_ADAPTATION** | 4-phase modifier transaction sequence engine | Route native calls through `NativeKeyboardDispatchGateway`, integrate cancellation |
| `keyboard_controller.py` | **REQUIRES_ADAPTATION** | Native SendInput driver, typing loop, target validation | Split into Single Dispatch Gateway, Typing Executor, and Production Adapter |
| `target_tracker.py` | **REQUIRES_ADAPTATION** | HWND existence, PID match, and foreground verification | Encapsulate as target verification helper connected to observation context |
| `telemetry.py` | **REQUIRES_ADAPTATION** | Action counting, stage latency profiling (T1–T7), CPS | Connect to ORBIT ActionCounter and event bus telemetry |
| `clipboard_preserver.py` | **UNSAFE_OR_UNSUITABLE_FOR_PRODUCTION** | Clipboard snapshotting and paste fallback | **Excluded from typing**: ORBIT prohibits silent clipboard manipulation |
| `cancellation_contract.py` | **REFERENCE_ONLY** | Prototype-local cancellation coordinator | Superseded by ORBIT core `CancellationToken` infrastructure |
| `prototype_ui.py` / Test harness | **REFERENCE_ONLY** | Standalone Tkinter UI & prototype acceptance runners | Reference for test assertions; production tests live in `tests/` |

---

## 2. Detailed Component Breakdown

### 2.1 `unicode_engine.py`
- **Original Responsibility**: Decomposes Python Unicode strings into discrete 16-bit UTF-16 code units (handling BMP, surrogate pairs for non-BMP emojis, and variation selectors) for `KEYEVENTF_UNICODE` in `wScan`. Evaluates exact vs NFC canonical equivalence.
- **Production Relevance**: Fundamental foundation for robust multilingual and emoji text typing without locale dependencies.
- **Dependencies**: Python standard library `unicodedata`.
- **Threading & Windows Assumptions**: Pure functional computation, thread-safe, zero Win32 calls.
- **Safety Implications**: Prevents string truncation and broken surrogate halves.
- **Validation Evidence**: Formally verified in Prototype C Test C2 (14/14 tests pass).
- **Strategy**: Reusable directly as `orbit.adapters.keyboard.unicode`.

### 2.2 `shortcut_policy.py`
- **Original Responsibility**: Classifies shortcut combinations into `ALLOWED`, `RESTRICTED`, and `MANUAL_CONTROLLED_ONLY`. Blocks destructive system shortcuts (`Win+L`, `Alt+F4`, `Ctrl+Alt+Del`, `Win+D`, `Ctrl+Shift+Esc`).
- **Production Relevance**: Mandatory security gate preventing remote clients or unvetted automation from locking the OS, killing windows, or disrupting the host environment.
- **Dependencies**: None.
- **Threading Assumptions**: Stateless classification function.
- **Safety Implications**: Hard security invariant preventing denial-of-service or privilege escalation via keystroke injection.
- **Validation Evidence**: Formally verified in Prototype C Test C3 / C7.
- **Strategy**: Adapt into `orbit.adapters.keyboard.shortcuts` with a strict, testable allowlist and structured error responses.

### 2.3 `keyboard_state.py`
- **Original Responsibility**: Tracks pressed keys by ownership (`ORBIT_INJECTED_TRACKED`, `USER_PHYSICAL_OBSERVED`, `UNKNOWN`). Sanitizes only ORBIT-injected keys on abort.
- **Production Relevance**: Prevents ORBIT from releasing physically held user keys, while guaranteeing 100% of synthetic keys are tracked and cleaned up on cancellation or session disconnect.
- **Dependencies**: `threading.RLock`.
- **Threading Assumptions**: Multi-threaded access from asyncio worker threads.
- **Safety Implications**: If key release fails ($M=0$), the system must enter `UNRESOLVED_LOCKED` to prevent stuck modifier loops.
- **Strategy**: Adapt into `KeyboardStateManager` in `orbit.adapters.keyboard.state`, linking release failures to `UNRESOLVED_LOCKED` and administrative recovery tokens.

### 2.4 `shortcut_engine.py`
- **Original Responsibility**: Executes 4-phase shortcut sequence: Phase 1 (Modifiers Down) $\rightarrow$ Phase 2 (Action Down) $\rightarrow$ Phase 3 (Action Up) $\rightarrow$ Phase 4 (Modifiers Up in reverse order).
- **Production Relevance**: Ensures clean modifier-key transitions with zero orphaned modifier keys.
- **Dependencies**: `KeyboardStateManager`, Win32 virtual key constants.
- **Threading Assumptions**: Executed on worker threads.
- **Safety Implications**: Partial failure during Phase 2/3 must immediately trigger safe sanitization of Phase 1 modifiers.
- **Strategy**: Adapt into `ShortcutExecutor` in `orbit.adapters.keyboard.shortcuts`.

### 2.5 `keyboard_controller.py`
- **Original Responsibility**: Raw `user32.SendInput` driver, character-by-character typing loop, target validation, and cancellation polling.
- **Production Relevance**: Contains core SendInput packet construction (`KEYBDINPUT`, `INPUT_KEYBOARD`, `KEYEVENTF_UNICODE`, `KEYEVENTF_EXTENDEDKEY`, `KEYEVENTF_KEYUP`).
- **Threading & Windows Assumptions**: Win32 `SendInput` called across background worker threads. Requires Win32 input-desktop attachment (`ensure_thread_input_desktop()`) to avoid `ERROR_ACCESS_DENIED`.
- **Safety Implications**: All dispatches must route through a single authoritative gateway with ABI gate validation.
- **Strategy**: Refactor into:
  1. `NativeKeyboardDispatchGateway` (in `dispatch.py` or `safety.py`).
  2. `TextTypingExecutor` (in `text.py`).
  3. `ProductionKeyboardAdapter` (in `adapter.py`).

### 2.6 `target_tracker.py`
- **Original Responsibility**: Validates target HWND existence (`IsWindow`), foreground status (`GetForegroundWindow`), and process name (`QueryFullProcessImageNameW`).
- **Production Relevance**: Mitigates focus race conditions during long text typing.
- **Safety Implications**: TOCTOU inherent to Windows GUI; checks reduce accidental background typing but do not guarantee target effect.
- **Strategy**: Implement as focus/target validator in `orbit.adapters.keyboard.focus`.

### 2.7 `clipboard_preserver.py`
- **Original Responsibility**: Snapshots clipboard, sets text, pastes, restores clipboard.
- **Classification**: **UNSAFE_OR_UNSUITABLE_FOR_PRODUCTION** for automated text typing.
- **Rationale**: ORBIT core design rules strictly forbid silent clipboard manipulation. All text typing must use `KEYEVENTF_UNICODE`. Clipboard access may only exist as an explicit, future clipboard capability if requested.

### 2.8 `cancellation_contract.py`
- **Classification**: **REFERENCE_ONLY**.
- **Rationale**: Superseded by ORBIT's production `CancellationToken` in `src/orbit/infrastructure/cancellation.py`.

---

## 3. Production Architecture Blueprint

```
src/orbit/adapters/keyboard/
├── __init__.py           # Package exports (ProductionKeyboardAdapter, etc.)
├── adapter.py            # ProductionKeyboardAdapter implementing KeyboardCapability
├── dispatch.py           # NativeKeyboardDispatchGateway (single SendInput gateway)
├── state.py              # KeyboardStateManager (synthetic key & modifier ownership)
├── shortcuts.py          # ShortcutPolicy, ShortcutExecutor (4-phase sequence)
├── unicode.py            # UnicodeEngine (UTF-16 code units & surrogate decomposition)
├── focus.py              # TargetFocusValidator (HWND, PID, foreground checks)
└── safety.py             # ABI verification, virtual key definitions, desktop attachment
```

---

## 4. Key Invariants & Ground Truths

1. **Single Native Dispatch Gateway**: Exactly 1 function in production calls `user32.SendInput` for keyboard events.
2. **Desktop Attachment Invariant**: Worker threads executing keyboard `SendInput` must have valid interactive input-desktop access via `ensure_thread_input_desktop()`.
3. **Synthetic Ownership Isolation**: ORBIT only tracks and releases keys it synthetically pressed. It never releases user physical keys.
4. **Fail-Closed Hard Lockout**: Any unconfirmed key release enters `UNRESOLVED_LOCKED` and requires administrative token recovery.
5. **No Silent Clipboard Tampering**: Text input uses Unicode virtual injection exclusively.
