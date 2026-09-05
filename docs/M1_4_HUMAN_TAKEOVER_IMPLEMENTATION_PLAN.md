# ORBIT Milestone M1.4: Human Takeover Implementation Plan

**Milestone**: M1.4 — Production Human Takeover Integration  
**Status**: **PLAN CREATED — READY FOR EXECUTION**  
**Date**: September 6, 2026  

---

## 1. Overview of Proposed Changes

This implementation plan specifies the exact modules to be created or modified for ORBIT Milestone M1.4.

---

## 2. Proposed Implementation Files

### A. New Files

#### 1. `src/orbit/adapters/takeover/__init__.py` [NEW]
- **Responsibility**: Package exports for the production human takeover capability.
- **Exports**: `ProductionHumanTakeoverAdapter`, `NativeInputMonitor`, `TakeoverClassifier`, `TakeoverStateManager`, `TakeoverEvidence`, `TakeoverState`.

#### 2. `src/orbit/adapters/takeover/safety.py` [NEW]
- **Responsibility**: Low-level 64-bit AMD64 ctypes Win32 hook definitions and structure layouts.
- **Structures**: `MSLLHOOKSTRUCT`, `KBDLLHOOKSTRUCT`, `POINT`, `HOOKPROC`, `WH_MOUSE_LL`, `WH_KEYBOARD_LL`, `LLMHF_INJECTED`, `LLKHF_INJECTED`, `ORBIT_EXTRA_INFO_SIGNATURE`.
- **Concurrency Boundary**: Thread-safe definitions, used by hook thread.
- **Failure Behavior**: Verifies structure sizes and ctypes prototypes before hooking.

#### 3. `src/orbit/adapters/takeover/hook.py` [NEW]
- **Responsibility**: Dedicated message-pump background thread installing and managing native `WH_MOUSE_LL` and `WH_KEYBOARD_LL` hooks.
- **Inputs**: Registered event callback `Callable[[InputEvent], None]`.
- **Outputs**: High-speed queue and callback dispatches with $<50\,\mu\text{s}$ latency.
- **Concurrency Boundary**: Dedicated background OS thread with Win32 message loop (`GetMessageW`).
- **Cancellation / Shutdown Behavior**: Posts `WM_QUIT` via `PostThreadMessageW`, cleanly unhooks `UnhookWindowsHookEx`, and joins thread.
- **Failure Behavior**: If hook installation fails, surfaces explicit error to health tracker.

#### 4. `src/orbit/adapters/takeover/classifier.py` [NEW]
- **Responsibility**: Classifies low-level input events into `USER_PHYSICAL`, `ORBIT_EXPECTED`, and `INPUT_AMBIGUOUS`.
- **Inputs**: Raw `MSLLHOOKSTRUCT` / `KBDLLHOOKSTRUCT` flag and `dwExtraInfo` data.
- **Outputs**: `TakeoverEvidence` containing device, reason, latency, and timestamp.
- **Concurrency Boundary**: Pure stateless calculation, thread-safe.
- **Failure Behavior**: Ambiguous input is classified as high-priority takeover for safety.

#### 5. `src/orbit/adapters/takeover/state.py` [NEW]
- **Responsibility**: Thread-safe state machine managing the takeover lifecycle (`STOPPED`, `STARTING`, `MONITORING_IDLE`, `MONITORING_ACTIVE_TASK`, `TAKEOVER_TRIGGERED`, `TAKEOVER_ACTIVE`, `RELEASE_PENDING`, `ERROR`).
- **Inputs**: State transition requests, inactivity timer triggers.
- **Outputs**: Validated state, duration in state, state change notifications.
- **Concurrency Boundary**: Protected by `threading.RLock`.
- **Failure Behavior**: Rejects invalid transitions with `StateTransitionError`.

#### 6. `src/orbit/adapters/takeover/telemetry.py` [NEW]
- **Responsibility**: Records detection latency ($T_1 \to T_5$), false-positive/negative counts, and aggregated performance metrics.
- **Outputs**: Latency percentiles (Min, Mean, P95, Max).

#### 7. `src/orbit/adapters/takeover/adapter.py` [NEW]
- **Responsibility**: `ProductionHumanTakeoverAdapter` implementing `BaseCapabilityAdapter` and `HumanTakeoverCapability`.
- **Inputs**: `start_monitoring`, `stop_monitoring`, `reset_takeover_state`.
- **Outputs**: Asyncio event loop bridge, `EventType.TAKEOVER_EVENT` dispatch, health reporting.
- **Concurrency Boundary**: Bridges Win32 hook thread to `asyncio` event loop via `loop.call_soon_threadsafe`.

---

### B. Modified Files

#### 1. `src/orbit/adapters/production/production_takeover.py` [MODIFY]
- **Responsibility**: Update production takeover capability module to re-export `ProductionHumanTakeoverAdapter` from `src/orbit/adapters/takeover/`.

#### 2. `src/orbit/adapters/production/production_safety.py` [MODIFY]
- **Responsibility**: Connect `ProductionSafetyCoordinator.emergency_stop_all()` to `pointer.emergency_release_all()` and `keyboard.emergency_release_all()`.

#### 3. `src/orbit/runtime/orchestrator.py` [MODIFY]
- **Responsibility**: Ensure `handle_human_takeover()` seamlessly connects to `ProductionHumanTakeoverAdapter` callback and cancels all active execution tasks.

---

### C. Test Files

#### 1. `tests/unit/test_takeover_classifier.py` [NEW]
- Unit tests for physical vs synthetic input classification, signature verification, and ambiguous event handling.

#### 2. `tests/unit/test_takeover_state_machine.py` [NEW]
- Unit tests for takeover state transitions, quiet-period timer transitions, and invalid transition guards.

#### 3. `tests/unit/test_takeover_hook_safety.py` [NEW]
- Unit tests for Win32 hook ABI layouts, message pump start/stop lifecycle, and thread isolation.

#### 4. `tests/integration/test_takeover_orchestrator_flow.py` [NEW]
- Integration test verifying:
  - Takeover trigger $\to$ orchestrator cancels active task $\to$ pointer/keyboard sanitize held state $\to$ system state becomes `HUMAN_TAKEOVER_ACTIVE`.

#### 5. `tests/integration/test_takeover_live_validation.py` [NEW]
- Controlled live Windows test verifying low-level hook registration, synthetic signature bypass, and emergency preemption.

---

## 3. Execution Sequence & Dependencies

```
Phase 1: Win32 Safety & Hook Module (`safety.py`, `hook.py`, `classifier.py`)
    ↓
Phase 2: Takeover State Manager & Telemetry (`state.py`, `telemetry.py`)
    ↓
Phase 3: Production Adapter & Asyncio Bridge (`adapter.py`, `production_takeover.py`)
    ↓
Phase 4: Safety Coordinator & Orchestrator Wiring (`production_safety.py`, `orchestrator.py`)
    ↓
Phase 5: Unit & Integration Test Suites (`tests/unit/`, `tests/integration/`)
    ↓
Phase 6: Live Windows Validation & Frozen Boundary Check
```
