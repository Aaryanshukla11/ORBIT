# ORBIT System Architecture v1.0 — Risk Register & Adversarial Review

**Document Version:** 1.0.0  
**Status:** Approved Architectural Baseline  
**Author:** Google DeepMind / ORBIT Core Systems Engineering  

---

## 1. Executive Summary

This document establishes the comprehensive risk catalog, failure modes, detection strategies, and mitigation protocols for the **ORBIT Desktop Assistant Architecture v1.0**. Because ORBIT interacts directly with low-level Win32 input pipelines, system-level AppBar reservations, continuous screen capture, and non-deterministic local/cloud foundation models, traditional software safety guarantees are insufficient.

This register addresses both runtime technical risks (concurrency deadlocks, UIPI privilege boundaries, native thread message pump starvation) and semantic safety risks (unauthorized action dispatch, hallucinated OS commands, preemption races).

---

## 2. Risk Taxonomy & Severity Matrix

| Risk ID | Category | Risk Description | Severity | Likelihood | Mitigation Strategy |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **R-01** | **Win32 Hook Starvation** | `WH_MOUSE_LL` / `WH_KEYBOARD_LL` hook procedure blocks the OS message pump, causing Windows to silently unhook the hook chain. | **CRITICAL** | Medium | Dedicated hook thread executing standard Win32 `GetMessage`/`DispatchMessage` pump with zero async/blocking I/O in the callback. Signal dispatch via lock-free atomic `SetEvent`. |
| **R-02** | **UIPI Privilege Boundary Violation** | Target window is elevated (Run as Administrator) while ORBIT runs as medium integrity. `SendInput` or `SetForegroundWindow` silently fails or is blocked by User Interface Privilege Isolation. | **HIGH** | High | Pre-action integrity probe via `GetWindowThreadProcessId` + `OpenProcessToken` to detect target elevation. Explicit operator escalation prompt or graceful rejection before input dispatch. |
| **R-03** | **Per-Monitor V2 DPI Coordinate Drift** | Mixed-DPI multi-monitor topology causes client-to-screen coordinate miscalculations, targeting wrong UI elements or off-screen coordinates. | **CRITICAL** | Low | Native `DpiAwarenessContext.PER_MONITOR_AWARE_V2` process declaration + strict conversion to 65535 normalized absolute virtual desktop space via `VirtualDesktopMetrics`. |
| **R-04** | **AppBar WorkArea Collision** | Multiple instances or abrupt ORBIT crashes leave desktop work area permanently reduced, or shell restarts (Explorer crash) destroy the AppBar registration. | **MEDIUM** | Medium | Listen for `WM_TASKBARCREATED` broadcast message; register `ABM_REMOVE` in `atexit` and `win32_exception_handler`; atomic restoration of original `SPI_SETWORKAREA`. |
| **R-05** | **Preemption Race Condition** | Human moves mouse or presses key during multi-step macro execution (drag/type), causing agent input to interleave with human input. | **CRITICAL** | High | Hardware-level hardware flag detection (`LLMHF_INJECTED == 0`) triggers instant atomic cancellation token $<50\,\mu\text{s}$. Hard lockout halts further queue dispatch. |
| **R-06** | **Deadlock on Async / Native Loop** | Python `asyncio` event loop blocks on synchronous native ctypes call (e.g., `SendInput`, `GetDC`, `GetMessage`), freezing WebSocket gateway and telemetry. | **HIGH** | Medium | Strict separation: All Win32 native blocking routines run in dedicated OS threads (`threading.Thread`) or isolated worker processes; communication via `asyncio.to_thread` and thread-safe queues. |
| **R-07** | **Memory Leak in Observation Capture** | High-frequency screen capture (Desktop Duplication API / GDI / WinRT) leaks DirectX textures, GDI device contexts, or shared memory buffers. | **HIGH** | Medium | Context-managed frame lifecycle with zero-copy buffer pooling (`SharedMemoryPool`), deterministic `.release()` / `.close()` calls, and high-watermark memory limits. |
| **R-08** | **Event Desynchronization (Out-of-Order)** | Network latency or async task scheduling delivers `ACTION_COMPLETED` before `ACTION_STARTED` or drops state transition events. | **MEDIUM** | Low | Monotonically increasing 64-bit sequence counters (`event_seq`), explicit correlation IDs (`action_id`), and state machine validation enforcing strict state progression. |
| **R-09** | **Frontend Disconnection During Active Task** | Operator closes browser UI or WebSocket drops while agent is executing an unverified or multi-step action. | **HIGH** | Medium | Configurable safety policy: System defaults to immediate `AGENT_PAUSED` or `HARD_CANCEL` on client disconnect. Execution requires active heartbeat (`ping`/`pong`) within 5000ms. |
| **R-10** | **Model Hallucination / Hazardous Execution** | Foundation model generates destructive actions (e.g., `rmdir /s /q`, formatting drives, clicking unauthorized system toggles). | **CRITICAL** | Medium | Multi-tier validation: 3-tier action classification (Tier 1 Safe, Tier 2 Constrained, Tier 3 High-Impact). Tier 3 requires cryptographically valid operator confirmation token. |
| **R-11** | **Direct Prototype Coupling Leak** | Core runtime directly imports prototype-specific internal structs, preventing standalone testing, mock injection, or future capability upgrades. | **HIGH** | High | Strict `orbit.contracts` abstract Protocol interfaces. Core runtime depends ONLY on contracts; `orbit.adapters` bridge to prototypes with zero prototype modifications. |
| **R-12** | **Indeterminate Hardware State on Abort** | Agent cancelled midway through mouse drag (`MOUSEEVENTF_LEFTDOWN` dispatched) leaving left mouse button virtually stuck down. | **CRITICAL** | Medium | Fail-closed hardware reset routine (`NativeDispatchGateway.emergency_release_all()`) dispatches virtual key/button UP events on any cancellation, error, or unhandled exception. |
| **R-13** | **WebSocket Gateway Unauthorized Local Access** | Malicious local process connects to ORBIT WebSocket port (`127.0.0.1:8765`) and injects arbitrary task/action commands. | **HIGH** | Low | Ephemeral session tokens generated on runtime startup and exchanged during HTTP handshake; WebSocket rejects unauthenticated connection requests. |
| **R-14** | **Target Window Z-Order Shift** | Between screen capture observation and pointer click dispatch (100–300ms), a pop-up window or notification steals focus, causing mis-click. | **HIGH** | Medium | Target validation probe: Check `WindowFromPoint` or `GetForegroundWindow` immediately prior to `SendInput`. If target HWND changed, fail action with `HWND_MISMATCH`. |
| **R-15** | **Keyboard State Desynchronization** | Shift, Ctrl, Alt, or CapsLock virtual state gets inverted due to asynchronous user keystrokes during text streaming. | **MEDIUM** | Medium | Query `GetKeyState` / `GetAsyncKeyState` before keystroke sequences; use raw Unicode injection (`KEYEVENTF_UNICODE`) for character emission to bypass modifier state dependencies. |
| **R-16** | **Unbounded Task Queue Growth** | LLM planner generates endless sub-plans or operator spams tasks faster than execution rate, consuming excessive memory. | **LOW** | Low | Fixed-capacity task and action queues with backpressure; rejected submissions return `QUEUE_FULL` status. |
| **R-17** | **Process Crash on Native Access Violation** | Ctypes structure mismatch or invalid pointer dereference causes hard `STATUS_ACCESS_VIOLATION` (0xC0000005), crashing the Python runtime. | **HIGH** | Low | Rigorous ctypes struct alignment and size checks verified in Prototype E Phase 2A; compile-time size assertions at adapter initialization; optional out-of-process isolation. |
| **R-18** | **Unresolved Lockout Deadlock** | Runtime enters `UNRESOLVED_LOCKED` fail-closed state but frontend provides no recovery path, requiring hard task termination. | **MEDIUM** | Low | Explicit `CONFIRM_OPERATOR_MANUAL_RESET` recovery command in WebSocket protocol allows operator to safely clear hardware locks after verifying physical desktop state. |

---

## 3. Adversarial Architectural Review

The following section addresses the 7 mandatory architectural challenge inquiries with concrete implementation invariants and fail-safe designs.

---

### Challenge 1: Coupling & Direct Prototype Dependencies
**Question:** *Could importing prototype modules directly create dependency, lifecycle, or initialization conflicts in the product core?*

**Adversarial Finding:**  
Directly importing prototype files (e.g., `from prototypes.prototype_e_pointer.native_dispatch_gateway import NativeDispatchGateway`) creates severe architectural liabilities:
1. Prototype code contains test-specific global singletons and fixed assumptions.
2. Prototypes A–D are frozen at commit `ca87ef8` and cannot be patched if interface signatures evolve.
3. Core unit tests would be forced to pull in heavy Win32 ctypes bindings and native hooks.

**Resolution & Invariants:**
1. **Contract Isolation:** ORBIT Core components depend strictly on abstract Python Protocols defined in `orbit.contracts` (`PointerCapability`, `KeyboardCapability`, `ObservationCapability`, `WorkspaceCapability`, `HumanTakeoverCapability`).
2. **Adapter Layer Isolation:** An explicit adapter package (`orbit.adapters`) implements these protocols. Adapters encapsulate prototype loading, normalize data types into standard Pydantic models, and wrap prototype exceptions in standardized `OrbitCapabilityError` hierarchies.
3. **Mockability:** Core runtime can be fully unit-tested with 100% mocked capabilities in Linux/CI environments without importing a single Win32 module.

---

### Challenge 2: Async Architecture & Win32 OS Coexistence
**Question:** *Will async WebSocket event handling, LLM streaming, and low-level Win32 OS message pumps safely coexist without deadlocking or starving each other?*

**Adversarial Finding:**  
Windows message hooks (`SetWindowsHookExW`) require a synchronous, uninterrupted Win32 message pump (`GetMessageW` $\to$ `TranslateMessage` $\to$ `DispatchMessageW`). If this pump runs on the Python `asyncio` event loop thread, any `await`, disk I/O, or LLM network call will freeze the message pump. Windows will detect hook timeout ($>200\,\text{ms}$) and silently remove the hook, disabling human takeover protection without notification.

**Resolution & Invariants:**
```
┌──────────────────────────────────────────────────────────────┐
│                      ORBIT THREAD TOPOLOGY                   │
├──────────────────────────────┬───────────────────────────────┤
│ THREAD 1: Async Main Loop    │ FastAPI / WebSockets          │
│                              │ Task Orchestrator             │
│                              │ Planner / Model Router        │
├──────────────────────────────┼───────────────────────────────┤
│ THREAD 2: Win32 Hook Pump    │ WH_MOUSE_LL / WH_KEYBOARD_LL  │
│                              │ Synchronous Win32 Message Pump│
│                              │ Lock-Free Preemption Trigger  │
├──────────────────────────────┼───────────────────────────────┤
│ THREAD 3: OS Action Executor │ Native Win32 SendInput        │
│                              │ Direct HWND Manipulation      │
│                              │ AppBar Shell Registration     │
├──────────────────────────────┼───────────────────────────────┤
│ THREAD 4: Vision Pipeline    │ Screen Capture Worker         │
│                              │ Frame Encoding / Pooling      │
└──────────────────────────────┴───────────────────────────────┘
```
- The Win32 hook pump runs in a dedicated background daemon thread (`HookPumpThread`).
- Input preemption signals are written to an atomic `threading.Event` or lock-free C flag.
- The `asyncio` main loop monitors cancellation tokens without blocking.

---

### Challenge 3: Event Ordering & Race Conditions
**Question:** *What happens if network latency or async queue scheduling causes an `ACTION_COMPLETED` event to arrive at the client before an older `ACTION_STARTED` event, or if events arrive out of order?*

**Adversarial Finding:**  
Asynchronous UI updates can lead to race conditions where the frontend renders a stale state (e.g., showing an action as "Executing" after it has already "Completed" or "Failed").

**Resolution & Invariants:**
1. **Monotonic Sequence Numbering:** Every WebSocket envelope contains a strictly increasing 64-bit integer `event_seq`.
2. **Correlation & Causation IDs:** Every event links directly to its parent `task_id` and triggering `action_id`.
3. **Client-Side State Monotonicity:** The frontend UI state machine rejects or ignores state transitions with `event_seq < current_rendered_seq` for that specific action ID.
4. **Single Outbound Dispatch Channel:** WebSocket events from the core runtime are serialized through an ordered `asyncio.Queue` per client connection, ensuring strictly FIFO network delivery.

---

### Challenge 4: Cancellation Timing & Multi-Subsystem Abort
**Question:** *What happens when an emergency cancellation occurs during: (a) heavy screen observation, (b) deep LLM planning, (c) active pointer movement, (d) multi-keystroke text injection, or (e) frontend disconnection?*

**Adversarial Finding:**  
If cancellation occurs while the pointer is physically down or modifier keys are depressed, the system leaves the OS in a corrupted hardware state (virtual buttons permanently stuck).

**Resolution & Invariants:**
- **Cooperative Cancellation Tokens:** Every execution pipeline checks `cancellation_token.is_cancelled()` before and after every micro-step.
- **Subsystem-Specific Abort Handlers:**
  - *Observation:* Instantly discard pending frame encoding; release DirectX swapchain lock.
  - *Planning:* Abort LLM HTTP request stream immediately; discard reasoning buffer.
  - *Pointer Movement:* Abort trajectory interpolation at current coordinate; do NOT jump cursor.
  - *Pointer Click / Drag:* Trigger immediate `emergency_release_all()` (`MOUSEEVENTF_LEFTUP | MOUSEEVENTF_RIGHTUP | MOUSEEVENTF_MIDDLEUP`).
  - *Keyboard Streaming:* Abort character loop; dispatch key-up events for all modifier keys (`VK_SHIFT`, `VK_CONTROL`, `VK_MENU`).
  - *Frontend Disconnect:* Immediately halt active task; trigger hardware sanitization.

---

### Challenge 5: Human Takeover Latency & Preemption
**Question:** *Can a physical human intervention (moving the mouse or striking a key) immediately and reliably preempt agent actions without latency?*

**Adversarial Finding:**  
If the takeover detection relies on async polling or queue processing, a physical human mouse movement could take $50\text{--}200\,\text{ms}$ to stop an agent action, during which the agent could execute an unintended click.

**Resolution & Invariants:**
1. **Low-Level Hook Priority:** `WH_MOUSE_LL` and `WH_KEYBOARD_LL` execute at the kernel-to-userland transition before messages reach target window queues.
2. **Sub-Millisecond Preemption:** When `LLMHF_INJECTED == 0` (physical hardware event), the hook callback immediately sets `takeover_event.set()` ($<50\,\mu\text{s}$).
3. **Execution Gate:** Prior to every single `SendInput` call, `NativeDispatchGateway` checks the hardware preemption atomic flag. If set, the dispatch is aborted instantly with `PREEMPTED_BY_HUMAN`.
4. **Physical Lockout:** Agent is placed into `HUMAN_TAKEOVER_ACTIVE` state, ignoring all further queued actions until explicitly released by the operator.

---

### Challenge 6: Failure Isolation & Blast Radius Control
**Question:** *Can a Win32 pointer failure, screen capture exception, or AppBar crash bring down the entire ORBIT server process?*

**Adversarial Finding:**  
Uncaught native exceptions in ctypes calls can crash the Python interpreter (`0xC0000005`), terminating the WebSocket server and disconnecting the client without error reporting.

**Resolution & Invariants:**
1. **Adapter-Level Exception Sandboxing:** All native ctypes calls are wrapped in robust exception guards. Native OS error codes (`GetLastError()`) are converted into structured `OrbitNativeError` instances.
2. **Fail-Closed State Isolation:** A capability error transitions only the active *Action* to `ACTION_FAILED`. The *Task Orchestrator* can then decide to retry, replan, or prompt the user.
3. **Runtime Resilience:** The WebSocket Gateway and Task Runtime remain alive even if an individual capability fails, allowing full telemetry and diagnostic logs to be transmitted to the UI.

---

### Challenge 7: Frontend Disconnection & Headless Execution Policy
**Question:** *Does ORBIT continue executing actions if the frontend disconnects (network glitch, tab closed, crash)?*

**Adversarial Finding:**  
If an agent continues executing autonomous desktop actions with no active UI monitoring or operator oversight, high-risk unintended operations could occur without human visibility.

**Resolution & Invariants:**
1. **Fail-Safe Disconnection Policy:** When the last authorized client WebSocket disconnects, the runtime enters `DISCONNECTED_SAFE_MODE`.
2. **Immediate Task Pause:** In-flight tasks are immediately transitioned to `TASK_PAUSED` or `TASK_CANCELLED` based on the configured security policy (`PAUSE_ON_DISCONNECT = True` by default).
3. **Hardware State Release:** Active buttons and keys are physically released via `emergency_release_all()`.
4. **Session Resumption:** When the client reconnects with the same `session_token`, the current state snapshot and execution timeline are re-synchronized, and the user can review and resume the paused task.

---

## 4. Verification & Audit Sign-Off

The mitigations outlined in this Risk Register have been mapped directly into:
- `orbit_system_architecture_v1.md` (Thread topology & security model)
- `websocket_protocol_v1.md` (Sequence numbers, error frames, disconnect policies)
- `capability_adapter_contracts.md` (Fail-closed models & exception hierarchies)
- `runtime_state_machine.md` (Hard lockout `UNRESOLVED_LOCKED` & preemption rules)

**Architecture Risk Status: REVIEWED & COMPLIANT**
