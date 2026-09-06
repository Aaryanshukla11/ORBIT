# ORBIT Milestone M1.6 Step 3 — Closed-Loop Execution Architecture Audit

**Milestone:** M1.6 Step 3 — Closed-Loop Sense → Plan → Validate → Act → Verify Execution Engine  
**Status:** AUDIT COMPLETE — PRE-IMPLEMENTATION  
**Host Platform:** Windows 11 AMD64 (`Windows-11-10.0.26200-SP0`)  
**Python Runtime:** 3.13.7  
**Verified Pre-Implementation Baseline:** 302 / 302 PASSING (100% Green)  
**Frozen Prototype Boundaries (A–D):** ZERO DIFF relative to commit `ca87ef8`

---

## 1. Executive Summary & Audit Mission

This audit inspects ORBIT's runtime execution pipeline before implementing **Milestone M1.6 Step 3: Closed-Loop Sense → Plan → Validate → Act → Verify Execution Engine**.

In Step 1, ORBIT gained **Semantic Target Resolution & Safe Dynamic Coordinate Dispatch** (transforming open-loop coordinates into grounded element/window targets bounded by workspace generation checks).  
In Step 2, ORBIT gained the **Post-Action Verification Engine** (`ActionVerifier`), breaking the assumption that pointer event injection equates to action success.

However, the orchestrator's task lifecycle (`OrbitOrchestrator._execute_task_lifecycle`) remains a **single-shot linear execution model**:
1. Target is located against initial observation snapshot.
2. A single step/action is dispatched.
3. Post-action verification runs once.
4. If verification yields `VERIFIED_FAILURE` or `STALE_EVIDENCE`, the orchestrator immediately raises `RuntimeError` and terminates the task as `FAILED`.

There is currently:
- **No bounded retry policy**: Transient UI latency, focus animations, or target shifts immediately fail the task fail-closed.
- **No re-observation loop**: There is no safe mechanism to capture a fresh post-failure observation and re-evaluate the target.
- **No bounded recovery coordination**: Actions cannot refresh stale workspace context or re-resolve moving elements within conservative attempt limits.
- **Risk of uncoordinated loops**: Without a dedicated closed-loop state machine, ad-hoc while-loops could introduce dangerous unbounded retries, stale coordinate re-use, or unmonitored capability spam.

Step 3 must introduce a formal, bounded, fail-closed `ExecutionEngine` managing the complete sense-plan-validate-act-verify cycle with explicit state machine transitions and strict safety preemption.

---

## 2. Current Action Execution Lifecycle Analysis

### 2.1 Current Workflow in `OrbitOrchestrator`
Currently, task execution follows `src/orbit/runtime/orchestrator.py`:
1. `submit_task()` creates a `Task` in `TaskStatus.CREATED` and queues background execution via `asyncio.create_task(_execute_task_lifecycle())`.
2. `_execute_task_lifecycle()` transitions:
   `CREATED -> QUEUED -> VALIDATING -> READY -> RUNNING`.
3. An initial screen frame is captured via `obs.capture_screen(display_index=0)`.
4. If `task.metadata["target_intent"]` is present:
   - Captures `snapshot = await obs.capture_snapshot()`.
   - Calls `self._target_locator.locate_target(snapshot, intent)`.
   - If not resolved: fails task immediately (`TaskStatus.FAILED`).
   - Builds plan: `_build_target_resolved_plan()` attaching `ExpectedOutcome` to the click action.
5. Iterates through `plan.steps` and `step.actions`:
   - Calls `await self._execute_action(session_id, action, cancel_token)`.
6. Inside `_execute_action()`:
   - Pre-dispatch takeover check.
   - Pre-dispatch cancellation check.
   - Workspace coordinate validation (`validate_coordinate`).
   - Capability dispatch (e.g. `ptr.click(x, y)`).
   - Post-dispatch takeover & cancellation checks.
   - Transition to `ActionStage.VERIFYING`.
   - Fresh post-action snapshot capture (`await obs.capture_snapshot()`).
   - Evaluation via `self._action_verifier.verify(pre, post, expected_outcome)`.
   - Fail-closed check: if `VERIFIED_FAILURE`, `STALE_EVIDENCE`, or `UNSUPPORTED`, transitions to `ActionStage.FAILED` and raises `RuntimeError`.
   - If `VERIFIED_SUCCESS` or `INCONCLUSIVE`, transitions to `ActionStage.COMPLETED`.
7. Once all actions complete, task transitions to `TaskStatus.VERIFYING` then `TaskStatus.COMPLETED`.

### 2.2 Key Deficiencies in the Current Linear Lifecycle
- **Single Attempt Limitation:** A transient failure (e.g. click registered but dialog took 150ms to open, so initial verification observed zero delta) terminates the entire task with no structured recovery attempt.
- **No Re-Observation:** If a target moves or desktop geometry reconfigures, the plan cannot re-observe and re-resolve the new coordinates safely.
- **Scattered Responsibilities:** The orchestrator currently orchestrates capabilities, manages task states, constructs plans, validates coordinates, dispatches pointers, and performs verification all within monolithic methods.

---

## 3. Observation Evidence Baseline & Availability

| Observation Modality | Current Production Capability | Availability for Closed Loop |
| :--- | :--- | :--- |
| **GDI Screen Capture** | `ProductionObservationAdapter.capture_screen()` | **Available** (produces `FrameData` with JPEG raw bytes). |
| **Top-Level Windows** | `ProductionObservationAdapter.capture_snapshot()` -> `_window_tracker.enumerate_visible_windows()` | **Available** (provides HWND, title, PID, process name, extended frame bounds, foreground flag). |
| **MSAA / UIA Controls** | `ProductionObservationAdapter.capture_snapshot()` -> `_acc_coordinator.collect_accessibility_observations()` | **Available** (provides element ID, name, role, bounds, focus state, enabled state). |
| **Virtual Desktop Metrics** | `ProductionWorkspaceAdapter.get_virtual_desktop_bounds()` & `get_desktop_generation()` | **Available** (tracks topology, origin, bounds, and monotonic generation increments). |
| **Visual OCR / Neural Perception** | None (no production model integrated) | **UNSUPPORTED** (must return `UNSUPPORTED` fail-closed). |

---

## 4. Target Resolution & Safe Coordinate Dispatch Review

Implemented in `src/orbit/runtime/targeting/`:
- **`TargetLocator.locate_target(snapshot, intent)`**:
  - Resolves UI target against fresh snapshot evidence.
  - Generates immutable `ResolvedTarget` containing bounding box, semantic metadata, and evidence summary.
- **`SafeActionPointCalculator.calculate_action_point(bounds, generation_id)`**:
  - Computes interior centroid with 20% safe margin away from edge boundaries.
  - Stamps coordinate with desktop generation ID.
- **Pre-Dispatch Workspace Gate**:
  - Validates `(x, y)` against current usable work area (excluding docked AppBar).
  - Validates desktop generation parity (`expected_generation == active_generation`).
  - Blocks dispatch if coordinate falls in reserved area, out of bounds, or on stale generation.

---

## 5. Post-Action Verification Review

Implemented in `src/orbit/runtime/verification/`:
- **`ActionVerifier.verify(pre_snapshot, post_snapshot, expected_outcome)`**:
  - Enforces evidence hygiene: rejects missing snapshots (`INCONCLUSIVE`), identical snapshot reuse (`STALE_EVIDENCE`), stale snapshots (`STALE_EVIDENCE`), and desktop generation parity mismatch (`STALE_EVIDENCE`).
  - Evaluates concrete strategies:
    - `WINDOW_STATE_CHANGE`: `WINDOW_APPEARED`, `WINDOW_CLOSED`, `WINDOW_FOCUSED`.
    - `ACCESSIBILITY_STATE_CHANGE`: `TARGET_DISAPPEARED`, `TARGET_APPEARED`, `ELEMENT_STATE_CHANGED`.
    - `OBSERVATION_STATE_DELTA`: general desktop UI changes.
    - `VISUAL_SEMANTIC`: explicitly returns `UNSUPPORTED`.
  - Computes evidence-backed confidence (strictly $< 1.0$, never fabricated).

---

## 6. Human Takeover & Cancellation Preemption Baseline

- **Human Takeover (`HumanTakeoverCapability` / `SystemState.HUMAN_TAKEOVER_ACTIVE`):**
  - Checked before pointer move, before pointer click, after action execution, and during verification.
  - If active, autonomous dispatches are blocked immediately; action transitions to `FAILED` with `HUMAN_TAKEOVER_ACTIVE`.
- **Cancellation (`CancellationToken`):**
  - Token checked at each phase transition.
  - If cancelled, execution immediately transitions to `CANCELLED` without claiming `VERIFIED_SUCCESS` or executing further dispatches.
  - Triggers emergency stop on safety coordinator.

---

## 7. Architecture Design for M1.6 Step 3: Closed-Loop Execution Engine

### 7.1 Dedicated Subsystem: `src/orbit/runtime/execution/`
```
src/orbit/runtime/execution/
├── __init__.py           # Package exports
├── models.py             # ExecutionPolicy, ExecutionContext, ClosedLoopExecutionResult, ExecutionState
├── state_machine.py      # ClosedLoopStateMachine with explicit legal transitions and history
├── recovery.py           # Bounded recovery coordinator (re-observation, context refresh, budget accounting)
└── engine.py             # ClosedLoopExecutionEngine implementing the Sense->Plan->Validate->Act->Verify cycle
```

### 7.2 Explicit State Machine Model (`ExecutionState`)
```
IDLE
  ↓
OBSERVING
  ↓
RESOLVING_TARGET
  ↓
VALIDATING
  ↓
DISPATCHING
  ↓
RE_OBSERVING
  ↓
VERIFYING
  ↓ 
[SUCCESS: SUCCEEDED]
  OR
[NOT VERIFIED: RECOVERING]
  ↓
RETRYING ───→ (loops back to OBSERVING if budget allows)
  OR
[FAIL-CLOSED: FAILED]

Preemption anytime:
  → CANCELLED
  → HUMAN_TAKEOVER
```

### 7.3 Bounded Execution Policy (`ExecutionPolicy`)
- `max_total_attempts: int = 3` (hard upper bound across entire task)
- `max_target_resolution_attempts: int = 2`
- `max_verification_retries: int = 2`
- `max_recovery_attempts: int = 2`
- `execution_timeout_seconds: float = 15.0`
- `retry_backoff_base_ms: float = 50.0` (bounded delay between cycles)
- **Zero Counter Resets**: Budgets are monotonically decremented; no recovery path can reset attempts.

### 7.4 Re-Observation & Re-Planning Safety
When verification fails or target is lost, recovery does NOT repeat the old coordinate:
1. Re-observes the environment via fresh `capture_snapshot()`.
2. Validates freshness and desktop generation.
3. Re-resolves target via `TargetLocator`.
4. Re-computes dynamic safe action point.
5. Re-validates coordinate with `WorkspaceCapability`.
6. Only then dispatches.

---

## 8. Audit Verification Checkpoints

1. **Test Baseline:** Verified at **302 / 302 PASS** in pytest.
2. **Frozen Prototypes:** Zero diff verified against `ca87ef8` across Prototypes A, B, C, and D.
3. **Epistemic Classifications:** Maintained throughout (`CODE_PROVEN`, `TEST_PROVEN`, `LIVE_OS_VALIDATED`).
4. **Implementation Authorization:** Ready to proceed to code implementation following the approved plan.
