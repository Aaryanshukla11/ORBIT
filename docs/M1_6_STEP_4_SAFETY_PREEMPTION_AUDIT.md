# ORBIT Milestone M1.6 Step 4 — Safety Preemption & Takeover Audit

**Milestone:** M1.6 Step 4 — Cross-Capability Autonomy Safety & Human Takeover Preemption  
**Date:** 2026-09-06  
**Auditor:** ORBIT Core Runtime Systems Engineering  
**Baseline State:** 360 / 360 unit & integration tests passing (100% green)  
**Frozen Prototype Commit:** `ca87ef8` (Prototypes A–D 0 diff)

---

## Executive Summary

Milestone M1.6 Steps 1–3 established semantic target resolution, post-action verification, and bounded closed-loop execution. However, prior to this audit, autonomous actions across distinct capabilities (Pointer, Keyboard, Observation, Workspace) lacked a unified, atomic pre-dispatch safety gate and a single canonical cancellation authority.

This audit evaluates the existing codebase across 7 mandatory dimensions, exposes critical race windows between human takeover detection and hardware OS event dispatch, and specifies the minimal, robust architecture required to guarantee **zero new autonomous OS input events** when human takeover is active.

---

## Audit Item 1: Autonomous Capabilities That Can Produce Side Effects

We inspected every capability implementation and mock in the repository to identify all side-effecting operations:

1. **Pointer Capability (`src/orbit/adapters/pointer/adapter.py`, `buttons.py`, `movement.py`, `mock_pointer.py`):**
   - `click(x, y, button, count)`: Injects OS mouse down/up inputs (`SendInput`).
   - `move_to(x, y, smooth, duration)`: Moves cursor across display coordinates.
   - `drag(x1, y1, x2, y2)`: Holds mouse button while translating cursor.
   - `press_button()`, `release_button()`: Low-level button state mutations.
   - *Side-effect hazard:* Unintended clicks on desktop controls, window focus changes, or dragging desktop items.

2. **Keyboard Capability (`src/orbit/adapters/keyboard/adapter.py`, `dispatch.py`, `shortcuts.py`, `mock_keyboard.py`):**
   - `type_text(text, delay_ms)`: Injects character sequences via `SendInput`.
   - `press_shortcut(combination)`: Injects key combinations (e.g., `Ctrl+S`, `Alt+F4`, `Ctrl+W`).
   - `press_key()`, `release_key()`: Individual virtual key injections.
   - *Side-effect hazard:* Text insertion into user documents, triggering destructive OS hotkeys, or modifier keys remaining stuck down.

3. **Workspace Capability (`src/orbit/adapters/workspace/adapter.py`, `geometry.py`, `watchdog.py`):**
   - `register_appbar(edge, size)`: Win32 `SHAppBarMessage` registering desktop edge reservation, shifting desktop work area and moving third-party windows.
   - `unregister_appbar()`: Unregisters desktop edge, shifting all windows back.
   - `watchdog.py` recovery actions: Automatic repositioning of misaligned windows or re-docking.
   - *Side-effect hazard:* Disruptive desktop screen reorganization while a human is trying to use the display.

4. **Closed-Loop Execution Engine (`src/orbit/runtime/execution/engine.py`):**
   - Multi-attempt retry loop (`RETRYING`, `RECOVERING`, `REPLANNING`).
   - Re-observation loops and verification evaluation cycles.
   - *Side-effect hazard:* Resurrecting failed actions after operator intervention or continuing retry loops.

---

## Audit Item 2: Existing Cancellation Paths

The repository currently contains several distinct cancellation pathways:

1. **`CancellationToken` / `CancellationSource` (`src/orbit/runtime/cancellation.py`):**
   - Thread-safe cooperative cancellation token supporting `is_cancelled`, `reason`, `register_callback()`, and `wait_cancelled()`.
   - Used in `ClosedLoopExecutionEngine` and `OrbitOrchestrator` to signal task cancellation.
   - Limitation: Does not differentiate the root semantic cause (e.g. human takeover vs. operator cancel vs. timeout vs. shutdown).

2. **`OrbitOrchestrator.handle_human_takeover()` (`src/orbit/runtime/orchestrator.py`):**
   - Invoked when native hook detects physical mouse/keyboard activity.
   - Transitions `SystemStateMachine` to `SystemState.HUMAN_TAKEOVER_ACTIVE`.
   - Iterates through `_active_cancellation_sources` and calls `.cancel("Preempted by human takeover: ...")`.
   - Calls `EmergencySafetyCoordinator.emergency_stop_all()`.
   - Emits `EventType.TAKEOVER_EVENT`.

3. **`ClosedLoopExecutionEngine.execute_task_action()` (`src/orbit/runtime/execution/engine.py`):**
   - Checks `cancel_token.is_cancelled` at loop start, after observe, before dispatch, and after dispatch.
   - Checks `await self.is_human_takeover_active()` at loop start, after observe, before dispatch, and after dispatch.
   - Transitions state machine to `ExecutionState.CANCELLED` or `ExecutionState.HUMAN_TAKEOVER`.

4. **Capability-Level Token Polling:**
   - `PointerAdapter` and `KeyboardAdapter` check `cancellation_token.is_cancelled` inside movement steps and multi-key sequences.
   - Limitation: `MockKeyboardAdapter` and several high-level orchestrator branches (`type_text`, `shortcut`) previously bypassed cancellation checks entirely!

---

## Audit Item 3: Cross-Capability Cancellation Propagation

Currently, cancellation propagation across capabilities has notable gaps:

1. **Orchestrator Level:**
   - When human takeover triggers, `OrbitOrchestrator.handle_human_takeover()` cancels `_active_cancellation_sources`.
   - If an action was already in `_execute_action()`:
     - Pointer actions check `SystemState.HUMAN_TAKEOVER_ACTIVE` before coordinate validation.
     - Keyboard actions (`type_text`, `shortcut`) did **not** check `HUMAN_TAKEOVER_ACTIVE` before dispatching!
     - Workspace actions (`workspace_dock`, `workspace_undock`) did **not** check `HUMAN_TAKEOVER_ACTIVE` before calling `register_appbar`!

2. **ClosedLoopExecutionEngine Level:**
   - If `ClosedLoopExecutionEngine` is run with a local cancellation token not registered in `_active_cancellation_sources`, it relies solely on polling `await self.is_human_takeover_active()`.
   - While it checks `is_human_takeover_active()` periodically, there was no centralized atomic pre-dispatch gate immediately wrapping `await ptr.click()`, `await ptr.move_to()`, or keyboard dispatch.

3. **Safety Coordinator Isolation:**
   - `EmergencySafetyCoordinator.emergency_stop_all()` releases mouse buttons and keys, but does not prevent a scheduled retry task from subsequently firing another input event if the state machine loop didn't cleanly exit.

---

## Audit Item 4: Race Conditions Between Takeover Activation and Action Dispatch

A critical race condition exists in the pre-dispatch phase:

```text
[Engine Thread / Task]                      [Native Hook / Operator]
Check takeover inactive (Returns False)
                                             -> Physical mouse movement detected!
                                             -> Takeover active = True
                                             -> handle_human_takeover() scheduled
Dispatch pointer click -> SendInput() [UNSAFE!]
```

Because `is_human_takeover_active()` and `ptr.click()` were executed as distinct async steps without an atomic pre-dispatch safety gate, an asynchronous task switch or OS delay between the check and the actual `SendInput` invocation could permit an autonomous mouse click to hit the screen *after* the human took control.

**Required Solution:**
An **Atomic Pre-Dispatch Safety Gate** (`AutonomousDispatchGate`) that:
1. Holds a thread/async-safe reentrant lock during final gate validation.
2. Re-verifies live takeover state and token cancellation synchronously immediately prior to capability dispatch.
3. If takeover is active, rejects dispatch fail-closed and guarantees **ZERO OS input events**.
4. Epistemically tracks dispatch state (`NOT_DISPATCHED`, `DISPATCH_IN_PROGRESS`, `DISPATCHED`, `OUTCOME_UNKNOWN`).

---

## Audit Item 5: Actions That Could Continue After Cancellation

We analyzed what operations could continue or resurrect after cancellation:

1. **Retries and Replans:**
   - In `ClosedLoopExecutionEngine`, if an action failed verification, `RecoveryCoordinator` schedules a retry backoff (`await asyncio.sleep(backoff)`).
   - If takeover occurred during that `asyncio.sleep()`, the loop previously woke up and did a top-of-loop check, which was safe, BUT if the sleep was not immediately interrupted by the cancellation event, execution would unnecessarily dwell before halting.
   - If `cancel_token` was not checked at every recovery boundary, a retry attempt could initiate.

2. **Stuck Keys / Mouse Buttons:**
   - If a drag or multi-key shortcut was in progress when cancellation occurred, mouse buttons or modifier keys could remain held down unless sanitized by `emergency_stop_all()`.

3. **Workspace Watchdog Recovery:**
   - `WorkspaceWatchdog` contains an automated recovery loop that detects AppBar misalignment or window boundary violations.
   - While `watchdog.py` already checks `self.is_takeover_active_fn()`, we must ensure that any autonomous execution cancellation also suppresses disruptive watchdog corrections.

4. **Multi-Step Tasks in Orchestrator:**
   - Multi-step execution plans in `OrbitOrchestrator` loop over steps. If step $N$ is cancelled or preempted, subsequent steps must never execute.

---

## Audit Item 6: Existing Locking and Concurrency Assumptions

1. **Orchestrator Concurrency:**
   - `OrbitOrchestrator` uses `self._lock = asyncio.Lock()` for lifecycle state transitions (`SystemStateMachine`).
   - `_on_physical_takeover_detected()` is a synchronous callback from the native hook thread, which schedules `asyncio.create_task(self.handle_human_takeover())`.
   - Cancellation source iteration happens under `self._lock`.

2. **Cancellation Token Concurrency:**
   - `CancellationSource` uses `threading.Lock()` to protect internal state (`_cancelled`, `_callbacks`).
   - It signals an `asyncio.Event` via `call_soon_threadsafe`.

3. **Takeover State Manager:**
   - `TakeoverStateManager` in `src/orbit/adapters/takeover/state.py` uses `threading.RLock()` for transition safety and cooldown tracking.

4. **Assumption & Gap:**
   - Concurrency is currently split between Python `threading.Lock` (in low-level hooks/tokens) and `asyncio.Lock` (in orchestrator).
   - The pre-dispatch gate must safely bridge thread-safe native takeover signals and async coroutine execution without blocking the event loop.

---

## Audit Item 7: Minimal Architecture Required for Coordinated Preemption

To guarantee cross-capability safety and prevent unnecessary complexity, the minimal required architecture consists of:

1. **`CancellationReason` Enum & `ExecutionContext`:**
   - Canonical `CancellationReason` (`HUMAN_TAKEOVER`, `RUNTIME_SHUTDOWN`, `OPERATOR_CANCEL`, `SAFETY_ABORT`, `TIMEOUT`, `INTERNAL_FAILURE`).
   - `ExecutionContext`: Canonical authority binding `execution_id`, `CancellationToken`, `CancellationReason`, live takeover detection, and preemption evidence.

2. **`AutonomousDispatchGate`:**
   - Single canonical gate for ALL autonomous side-effecting operations (Pointer, Keyboard, Workspace).
   - Atomically checks cancellation and live takeover status immediately before invoking the capability adapter.
   - Truthfully tracks in-flight dispatch semantics (`NOT_DISPATCHED`, `DISPATCH_IN_PROGRESS`, `DISPATCHED`, `OUTCOME_UNKNOWN`).
   - Ensures fail-closed rejection: ZERO OS events dispatched once takeover is active.

3. **Multi-Step Engine Hardening (`ClosedLoopExecutionEngine`):**
   - Immediate cancellation-aware sleeps (`await cancel_token.wait_cancelled()` with timeout) during recovery backoffs.
   - Comprehensive pre-dispatch gate integration for both Pointer and Keyboard dispatches.
   - Explicit terminal state lockdown ensuring no retry budget, replan, or background task can resurrect execution.

4. **Structured Preemption Evidence & Bounded History:**
   - Bounded ring buffer recording structured preemption records (`execution_id`, reason, state, attempt, generation, dispatch status, timestamp).

---

## Audit Conclusion

The current codebase provides a solid foundation (`CancellationToken`, `TakeoverStateManager`, `ClosedLoopStateMachine`), but lacks a single authoritative `ExecutionContext` and an atomic `AutonomousDispatchGate` across capabilities. 

Implementation of M1.6 Step 4 will introduce these two core constructs, wire them into the execution engine and orchestrator, and validate them with rigorous concurrency and race-condition tests.
