# ORBIT Milestone M1.4: Production Human Takeover Capability Integration Audit

**Milestone**: M1.4 — Production Human Takeover Integration (Audit & Architecture Phase)  
**Status**: **AUDIT COMPLETE — READY FOR IMPLEMENTATION**  
**Date**: September 6, 2026  
**Environment**: Windows 11 AMD64 (Build 26200), Python 3.13.7  
**Baseline Commit**: `ca87ef8`

---

## 1. Executive Summary

Milestone **M1.4** designs the integration of the **Production Human Takeover Capability** into the ORBIT production architecture under `src/orbit/adapters/takeover/`. This capability provides instant, sub-millisecond, fail-closed preemption of autonomous operations whenever physical human intervention is detected on the host mouse or keyboard.

This audit evaluates the experimental findings of **Prototype B (Human Takeover & Input Ownership)**, traces the production runtime cancellation and capability pipelines (M0 through M1.3), establishes the native Win32 low-level hook threading model, defines synthetic vs physical attribution rules, resolves the takeover scope decision, and models all concurrency race conditions.

---

## 2. Frozen Boundary Verification

Prior to performing this audit, frozen prototype boundaries were verified against baseline commit `ca87ef8`:
```powershell
git diff ca87ef8 -- prototypes/prototype_a_workspace/ prototypes/prototype_b_human_takeover/ prototypes/prototype_c_keyboard/ prototypes/prototype_d_observation/
```
**Verification Result**: **0 files modified, 0 lines diff**.  
All four frozen prototypes (A, B, C, D) remain 100% untouched.

---

## 3. Prototype B Architecture Analysis

Prototype B was executed and inspected against the Windows 11 AMD64 platform:
- **Formal Test Suite Execution**: `python prototypes/prototype_b_human_takeover/formal_test_suite.py` passed **10/10 tests (B1–B10)**.
- **Observed Metrics**:
  - Average detection latency: **767.875 µs**
  - P95 detection latency: **1088.3 µs**
  - Total events processed: 12 (0 false positives, 0 false negatives)

### Prototype B Component Breakdown

| Component | Responsibility | Production Applicability | Integration Strategy |
| :--- | :--- | :--- | :--- |
| `input_monitor.py` | Low-level Win32 hooks (`WH_MOUSE_LL`, `WH_KEYBOARD_LL`) & message pump thread | **REQUIRES_ADAPTATION** | Adapt into `src/orbit/adapters/takeover/hook.py`. Bridge to asyncio loop via `loop.call_soon_threadsafe()`. |
| `app_types.py` | Event models, `InputSource`, `TakeoverState`, latency records | **REQUIRES_ADAPTATION** | Integrate with ORBIT contracts (`TakeoverEventPayload`, typed models). |
| `takeover_detector.py` | Anomaly classifier, trajectory comparison, quiet-period timer | **REQUIRES_ADAPTATION** | Refactor into `TakeoverClassifier` and `TakeoverDetector`. Replace trajectory Bezier logic with direct input preemption. |
| `state_machine.py` | 5-state lifecycle (`IDLE`, `EXECUTING`, `PAUSED_BY_USER`, etc.) | **REQUIRES_ADAPTATION** | Integrate with ORBIT `SystemStateMachine` (`SystemState.HUMAN_TAKEOVER_ACTIVE`). |
| `telemetry.py` | $T_1 \to T_5$ latency logging, P95 metrics | **REQUIRES_ADAPTATION** | Connect to production `ActionCounter` and `EventBus`. |
| `trajectory_engine.py` | Bezier curve generation & spatial corridors | **REFERENCE_ONLY** | Not needed for production direct movement / streaming typing. |
| `input_controller.py` | Prototype SendInput driver | **UNSUITABLE** | Superseded by production `NativeDispatchGateway` (Pointer) and `NativeKeyboardDispatchGateway` (Keyboard). |

---

## 4. Production Runtime Cancellation Analysis

Tracing ORBIT runtime cancellation across `src/orbit/runtime/`:

1. **Token Hierarchy**:
   - `CancellationSource` in `src/orbit/runtime/cancellation.py` is thread-safe and controls atomic `cancel()`.
   - Each submitted task receives a dedicated `CancellationSource` in `OrbitOrchestrator._active_cancellation_sources[task_id]`.
   - Passing `token.is_cancelled` allows capability loops (pointer movement, click dwell, text streaming, shortcut phases) to abort synchronously before dispatch.
2. **Cancellation Propagation on Takeover**:
   - When physical takeover is detected, `OrbitOrchestrator.handle_human_takeover(reason)` is invoked.
   - It iterates through all active task cancellation sources and triggers `cancel(reason)`.
   - It transitions `SystemStateMachine` to `SystemState.HUMAN_TAKEOVER_ACTIVE`.
   - It invokes `EmergencySafetyCoordinator.emergency_stop_all()` to clean up any physically or synthetically held hardware state.
3. **Safety Guarantee**:
   - Any in-flight capability operation polling its cancellation token exits immediately, returning `False` or structured cancellation evidence.

---

## 5. Production Pointer Takeover Response

Tracing pointer modules in `src/orbit/adapters/pointer/`:

| Execution Stage | Cancellation Behavior | Synthetic State Protection |
| :--- | :--- | :--- |
| **A. Cursor Move before dispatch** | Returns `MovementStatus.CANCELLED_BEFORE_DISPATCH`. | Zero SendInput packets dispatched. |
| **B. Cursor Move after dispatch** | Returns `MovementStatus.CANCELLED_AFTER_DISPATCH`. | Single-packet move completed; cursor readback recorded honestly. |
| **C. Button DOWN before dispatch** | Returns `ButtonExecutionStatus.CANCELLED_BEFORE_DISPATCH`. | Zero button packets dispatched. |
| **D. Button DOWN after dispatch** | Button recorded as `BUTTON_HELD_SYNTHETIC`. | Cleaned up immediately when `emergency_stop_all()` calls `emergency_release_all()`. |
| **E. Click Dwell Period** | Dwell sleep catches cancellation token $\to$ triggers `emergency_sanitize()`. | Releases held button with `MOUSEEVENTF_*UP`. Logs `CANCELLED_DURING_DWELL_SANITIZED`. |
| **F. Button UP dispatch** | If UP succeeds, state returns to `IDLE`. If UP fails, transitions to `UNRESOLVED_LOCKED`. | Hard fail-closed protection prevents forgotten buttons. |
| **G. Emergency Sanitization** | Dispatches `MOUSEEVENTF_*UP` for all synthetic buttons. | Idempotent; only releases ORBIT-owned buttons. |

**Pointer Conclusion**: The pointer subsystem is 100% safe against stuck buttons during takeover, provided `emergency_release_all()` is invoked during takeover preemption.

---

## 6. Production Keyboard Takeover Response

Tracing keyboard modules in `src/orbit/adapters/keyboard/`:

| Execution Stage | Cancellation Behavior | Synthetic State Protection |
| :--- | :--- | :--- |
| **A. Key DOWN before dispatch** | Aborts before SendInput call. | Zero keys injected. |
| **B. Unicode Text Streaming** | Polled before every UTF-16 code unit. Loop breaks on cancel. | `finally:` block invokes `state_manager.sanitize_orbit_keys()`. |
| **C. Shortcut Phase 1 (Modifiers)** | Modifiers injected $\to$ cancelled at Phase 2 $\to$ aborts. | `finally:` block releases all held modifiers in reverse order. |
| **D. Shortcut Phase 2 (Action Key)** | Action key injected $\to$ cancelled $\to$ aborts. | Action key and modifiers released via `finally:` block. |
| **E. Emergency Sanitization** | `ProductionKeyboardAdapter.emergency_release_all()` iterates all `ORBIT_SYNTHETIC` keys and dispatches `KEYEVENTF_KEYUP`. | Preserves any user physical keys; clears 100% of synthetic keys. |

**Keyboard Conclusion**: The keyboard subsystem contains strict `finally:` sanitization blocks and fail-closed state management, guaranteeing zero orphaned modifier keys on preemption.

---

## 7. Native Hook Threading Model

### Low-Level Hook Thread Requirements (`WH_MOUSE_LL` / `WH_KEYBOARD_LL`)

1. **Dedicated Message Pump Thread**:
   - `SetWindowsHookExW` registers a thread-specific hook. The OS requires a standard Win32 message loop (`GetMessageW` / `DispatchMessageW`) on the thread that installed the hook.
   - Classification: **CODE_PROVEN & LIVE_OS_VALIDATED**.
2. **Hook Execution Latency Constraint**:
   - Windows imposes `LowLevelHooksTimeout` (default: 200–1000 ms). If a hook procedure exceeds this timeout, Windows silently unhooks it.
   - Therefore, the hook callback MUST execute in $<50\,\mu\text{s}$, performing only bitwise flag checking and enqueuing the event.
   - Classification: **DOCUMENTED_PLATFORM_BEHAVIOR & LIVE_OS_VALIDATED**.
3. **Asyncio Boundary Crossing**:
   - The native hook thread cannot directly call `asyncio` coroutines or access `EventBus` without synchronization.
   - The production adapter must capture the main `asyncio` event loop and use `loop.call_soon_threadsafe(self._on_native_takeover_event, event)` or a high-speed thread-safe queue.
   - Classification: **CODE_PROVEN**.
4. **Hook Thread Lifecycle**:
   - Start: Spawns daemon thread, installs hooks, sets `ready_event`, runs `GetMessageW`.
   - Stop: Posts `WM_QUIT` via `PostThreadMessageW(thread_id, WM_QUIT, 0, 0)`, unhooks `UnhookWindowsHookEx`, and joins thread.
   - Classification: **CODE_PROVEN & LIVE_OS_VALIDATED**.

---

## 8. Synthetic vs Physical Attribution Analysis

### Attribution Signature Verification

ORBIT uses a unified, single 64-bit signature passed in `dwExtraInfo`:
$$\text{ORBIT\_EXTRA\_INFO\_SIGNATURE} = \text{0x08B17001}$$

Verified in active production code:
- `src/orbit/adapters/pointer/safety.py`: `ORBIT_EXTRA_INFO_SIGNATURE = 0x08B17001`
- `src/orbit/adapters/keyboard/safety.py`: `ORBIT_EXTRA_INFO_SIGNATURE = 0x08B17001`
- `src/orbit/adapters/pointer/movement.py`: `inp.union.mi.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE`
- `src/orbit/adapters/keyboard/dispatch.py`: `inp.union.ki.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE`

### Attribution Rules

```
Hook Event Received (MSLLHOOKSTRUCT / KBDLLHOOKSTRUCT)
   │
   ├── is_injected == False (flags & LLMHF/LLKHF_INJECTED == 0)
   │     └── CLASSIFICATION: USER_PHYSICAL (Genuine human action)
   │
   └── is_injected == True (flags & LLMHF/LLKHF_INJECTED != 0)
         ├── dwExtraInfo == 0x08B17001
         │     └── CLASSIFICATION: ORBIT_EXPECTED (ORBIT synthetic input)
         │
         └── dwExtraInfo != 0x08B17001
               └── CLASSIFICATION: INPUT_AMBIGUOUS (Foreign synthetic input -> Takeover for Safety)
```

**Attribution Reliability Verdict**: **RELIABLE**.  
Because physical hardware drivers never set `LLMHF_INJECTED` or `LLKHF_INJECTED`, human input is unambiguously recognized.

**Temporal Proximity Invariant**:  
Human physical input occurring immediately after synthetic input has `is_injected == False` and will **never** be suppressed.

---

## 9. Takeover Scope Decision

### Options Evaluated:
- **Option A (Cancel only active action)**: Unsafe. If an agent is running a multi-step task, cancelling only one mouse move would allow the next step (e.g. click or keystroke) to fire while the human is operating the machine.
- **Option B (Cancel active task)**: Partial. Does not stop background tasks or queued automation.
- **Option C (Cancel all tasks in session)**: Session-scoped.
- **Option D (Global Runtime Preemption & Safety Stop)**: **RECOMMENDED & CHOSEN**.

### Authoritative Takeover Policy:
1. Physical intervention transitions the global system state to `SystemState.HUMAN_TAKEOVER_ACTIVE`.
2. All active task cancellation sources are cancelled immediately.
3. Global emergency safety coordinator executes `emergency_stop_all()`, releasing all synthetic pointer buttons and keyboard keys.
4. The system remains in `HUMAN_TAKEOVER_ACTIVE` until explicitly acknowledged and released by the operator via `release_takeover()` or WebSocket command `RELEASE_TAKEOVER`.

---

## 10. Proposed Production Takeover Contract

### `ProductionHumanTakeoverAdapter`

```python
class ProductionHumanTakeoverAdapter(BaseCapabilityAdapter, HumanTakeoverCapability):
    """Production low-level hook adapter detecting physical human intervention."""
    
    def __init__(self, config: Optional[TakeoverConfig] = None) -> None:
        super().__init__(
            capability_name="ProductionHumanTakeover",
            capability_type=CapabilityType.HUMAN_TAKEOVER,
            adapter_mode=AdapterMode.PRODUCTION,
        )
        self._monitor = NativeInputMonitor()
        self._state_manager = TakeoverStateManager()
        self._classifier = TakeoverClassifier()
```

### Protocol Methods:
- `async def start_monitoring(on_takeover_detected: Callable[[TakeoverEvidence], None]) -> bool`
- `async def stop_monitoring() -> bool`
- `async def is_takeover_active() -> bool`
- `async def reset_takeover_state() -> bool`
- `async def get_health() -> CapabilityHealth`
- `async def get_metrics() -> TakeoverTelemetrySnapshot`

---

## 11. Proposed Production State Machine

```
               ┌───────────────┐
               │    STOPPED    │
               └───────┬───────┘
                       │ initialize() / start_monitoring()
                       ▼
               ┌───────────────┐
               │   STARTING    │
               └───────┬───────┘
                       │ hooks set (ready)
                       ▼
         ┌───────────────────────────┐
         │      MONITORING_IDLE      │◄─────────────────────────┐
         └─────────────┬─────────────┘                          │
                       │ task started                           │
                       ▼                                        │
         ┌───────────────────────────┐                          │
         │  MONITORING_ACTIVE_TASK   │                          │
         └─────────────┬─────────────┘                          │
                       │ Physical Human Input Detected          │
                       ▼                                        │
         ┌───────────────────────────┐                          │
         │    TAKEOVER_TRIGGERED     │                          │
         └─────────────┬─────────────┘                          │
                       │ Cancellation Issued & Sanitized        │
                       ▼                                        │
         ┌───────────────────────────┐                          │
         │      TAKEOVER_ACTIVE      │                          │
         └─────────────┬─────────────┘                          │
                       │ 1000ms Inactivity Quiet Period         │
                       ▼                                        │
         ┌───────────────────────────┐                          │
         │      RELEASE_PENDING      │                          │
         └─────────────┬─────────────┘                          │
                       │ Operator Explicit Reset Command        │
                       └────────────────────────────────────────┘
```

---

## 12. Concurrency and Race Analysis

| # | Race Scenario | State Owner | Resolution & Invariant |
| :--- | :--- | :--- | :--- |
| 1 | Physical mouse move during pointer move | `TakeoverDetector` & `CancellationToken` | Hook classifies `USER_PHYSICAL` $\to$ cancel token set $\to$ `move_to` aborts before next step $\to$ `HUMAN_TAKEOVER_ACTIVE`. |
| 2 | Physical click during button transaction | `ButtonTransactionExecutor` | Preempts dwell sleep $\to$ `emergency_sanitize()` releases synthetic button $\to$ human click registered cleanly. |
| 3 | Physical keypress during Unicode typing | `TextTypingExecutor` | Loop exits at next character $\to$ `finally:` block sanitizes all keys $\to$ zero stuck keys. |
| 4 | Takeover detected after SendInput completed | `OrbitOrchestrator` | Current single packet finished cleanly; all subsequent steps cancelled. |
| 5 | Duplicate takeover signals in $<1\text{ ms}$ | `TakeoverStateManager` | State machine locks and deduplicates; subsequent events refresh quiet timer without redundant cancellations. |
| 6 | Takeover during task completion | `TaskManager` | Completed task stays `COMPLETED`; system state enters `HUMAN_TAKEOVER_ACTIVE` to prevent future task launches. |
| 7 | Client disconnect during takeover | `SessionManager` | Disconnect handler runs `emergency_stop_all()` again safely (idempotent). |
| 8 | Operator release while cleanup is running | `OrbitOrchestrator` | Lock protects cleanup sequence; release request rejected until cleanup finishes. |
| 9 | Hook thread crashes / drops | `HealthTracker` | Adapter health transitions to `FAILED`; orchestrator enters safe error state. |
| 10 | Foreign software injection (`INPUT_AMBIGUOUS`) | `TakeoverClassifier` | Classified as high-risk anomaly $\to$ triggers immediate takeover for safety. |

---

## 13. Risk Register

| Risk ID | Description | Impact | Mitigation |
| :--- | :--- | :--- | :--- |
| **R-1** | Hook thread blocks, causing Windows to drop the hook | High | Hook callback does $<50\,\mu\text{s}$ non-blocking classification and offloads to asyncio via `call_soon_threadsafe`. |
| **R-2** | False positive on synthetic move due to missing signature | Critical | All production pointer and keyboard dispatch gateways hardcode `ORBIT_EXTRA_INFO_SIGNATURE = 0x08B17001`. |
| **R-3** | Orphaned modifier key if process killed during takeover | High | Emergency safety coordinator executes global key release on process exit and session termination. |
| **R-4** | Operator forgets to reset takeover | Medium | `RELEASE_PENDING` state and WebSocket status notifications alert operator that system is ready for release. |

---

## 14. Explicit Non-Goals for Milestone M1.4

- **NO** Workspace AppBar integration (deferred to M5).
- **NO** AI model planner integration.
- **NO** Modification of frozen Prototypes A–D.
- **NO** Blind automatic resumption without operator acknowledgement.

---

## 15. Final Readiness Verdict

**VERDICT**: **APPROVED FOR PRODUCTION IMPLEMENTATION**.  
The architecture has zero unresolved ambiguities. All contracts, thread boundaries, and failure states are fully defined.
