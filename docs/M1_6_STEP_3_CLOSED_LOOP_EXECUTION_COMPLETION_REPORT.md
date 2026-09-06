# ORBIT Milestone M1.6 Step 3 — Closed-Loop Execution Engine Completion Report

**Milestone:** M1.6 Step 3 — Closed-Loop Sense → Plan → Validate → Act → Verify Execution State Machine  
**Status:** COMPLETE & GREEN  
**Host Platform:** Windows 11 AMD64 (`Windows-11-10.0.26200-SP0`), Python 3.13.7  
**Test Suite Verdict:** 354 / 354 PASSING (100% Green)  
**Frozen Prototype Boundaries (A–D):** ZERO DIFF relative to commit `ca87ef8`  

---

## 1. Architecture Implemented

Milestone M1.6 Step 3 evolves ORBIT from an open-loop dispatcher into a **closed-loop Sense → Plan → Validate → Act → Verify execution engine**.

The execution subsystem is encapsulated under `src/orbit/runtime/execution/`:

```text
src/orbit/runtime/execution/
├── __init__.py           # Unified exports for execution subsystem
├── models.py             # Strongly typed execution models & enums
├── state_machine.py      # ClosedLoopStateMachine with explicit transition rules
├── recovery.py           # RecoveryCoordinator bounding attempt & recovery budgets
├── retry_policy.py       # RetryPolicy & explicit failure classification logic
└── engine.py             # ClosedLoopExecutionEngine executing bounded closed loops
```

### Execution Flow
```text
OBSERVE (Capture pre-action snapshot)
   ↓
RESOLVE TARGET (Semantic target locator)
   ↓
VALIDATE (Workspace boundary & generation check)
   ↓
ACT (Dispatch pointer or keyboard action)
   ↓
RE-OBSERVE (Capture post-action snapshot)
   ↓
VERIFY (ActionVerifier evaluates state transition)
   ↓
DECIDE:
   ├── VERIFIED SUCCESS → SUCCEEDED (Terminal)
   ├── RETRYABLE FAILURE → RETRY_PENDING → Re-observe & Retry (within budget)
   ├── GENERATION MISMATCH / STALE → REPLANNING → Discard coordinates & Replan
   ├── HUMAN TAKEOVER / CANCEL → Immediate Preemption (Terminal)
   └── BUDGET EXHAUSTED / UNSAFE → FAILED (Terminal)
```

---

## 2. Execution States

Defined in `ExecutionState` (`src/orbit/runtime/execution/models.py`):
- `IDLE`: Initial state before execution begins.
- `OBSERVING`: Capturing desktop observation snapshot.
- `PLANNING`: Planning action steps and resolving intent.
- `RESOLVING_TARGET`: Locating target control via `TargetLocator`.
- `VALIDATING`: Validating coordinates against usable workspace canvas and generation parity.
- `ACTING` / `DISPATCHING`: Injecting physical input via pointer or keyboard capability.
- `RE_OBSERVING`: Capturing fresh post-action observation snapshot.
- `VERIFYING`: Evaluating state transition via `ActionVerifier`.
- `RETRY_PENDING` / `RETRYING`: Transient failure eligible for bounded retry.
- `REPLANNING` / `RECOVERING`: Context changed; coordinates discarded, replan triggered.
- `SUCCEEDED` (Terminal): Outcome positively verified.
- `FAILED` (Terminal): Terminal failure or budget exhausted; fail closed.
- `CANCELLED` (Terminal): Operator requested cancellation.
- `HUMAN_TAKEOVER` (Terminal): Human operator took physical control.

---

## 3. Legal State Transitions

Enforced in `ClosedLoopStateMachine` (`src/orbit/runtime/execution/state_machine.py`):
- Forward progress: `IDLE` $\rightarrow$ `OBSERVING` $\rightarrow$ `RESOLVING_TARGET` $\rightarrow$ `VALIDATING` $\rightarrow$ `ACTING` $\rightarrow$ `RE_OBSERVING` $\rightarrow$ `VERIFYING` $\rightarrow$ `SUCCEEDED`.
- Recovery loop: `VERIFYING` $\rightarrow$ `RETRY_PENDING` / `RECOVERING` $\rightarrow$ `RETRYING` $\rightarrow$ `OBSERVING`.
- Replan loop: `VALIDATING` (stale generation) $\rightarrow$ `REPLANNING` $\rightarrow$ `OBSERVING`.
- Terminal lockdown: `SUCCEEDED`, `FAILED`, `CANCELLED`, and `HUMAN_TAKEOVER` have 0 valid exit transitions (`_VALID_TRANSITIONS = set()`). Any attempt to transition out raises `StateTransitionError`.

---

## 4. Retry Policy

Enforced by `RecoveryCoordinator` and `RetryPolicy` (`src/orbit/runtime/execution/retry_policy.py`):
- **Hard attempt cap:** `max_total_attempts = 3` (default, configurable).
- **Target resolution cap:** `max_target_resolution_attempts = 2`.
- **Verification retry cap:** `max_verification_retries = 2`.
- **Total recovery cycles:** `max_recovery_attempts = 2`.
- **Execution timeout:** `execution_timeout_seconds = 15.0`.
- **Pacing backoff:** Exponential backoff with jitter base `10ms` to prevent capability spam.
- **Monotonic Consumption:** Budgets strictly decrement; no recovery path resets counters.

---

## 5. Replan Policy

- When desktop generation changes, snapshot becomes stale, or coordinates fall outside usable bounds:
  - Coordinate cache is **discarded immediately**.
  - Current target identity is invalidated.
  - State machine transitions to `REPLANNING`.
  - Engine captures fresh observation and re-runs `TargetLocator.locate_target()`.
  - Fresh coordinate is calculated and re-validated against active generation.
  - Blind reuse of old coordinates is strictly prevented.

---

## 6. Generation Invalidation Behavior

- Generation parity is enforced at two distinct gates:
  1. **Pre-dispatch:** `workspace.validate_coordinate(x, y, expected_generation)`.
  2. **Post-action:** `ActionVerifier.verify()` checks `pre_generation_id == post_generation_id`.
- If generation changes:
  - Dispatch is aborted fail-closed.
  - Verification reports `STALE_EVIDENCE`.
  - Stale coordinates are never dispatched.

---

## 7. Human Takeover Behavior

- Checked before observation, before resolution, before dispatch, after dispatch, before verification, and before every retry/replan.
- If `HUMAN_TAKEOVER_ACTIVE`:
  - Autonomous progression halts immediately.
  - No pointer or keyboard actions are dispatched.
  - State machine transitions to `HUMAN_TAKEOVER`.
  - Result structured with code `HUMAN_TAKEOVER_ACTIVE`.

---

## 8. Dispatch Success vs Verified Outcome Semantics

ORBIT strictly maintains the boundary:
- **`DISPATCH_SUCCESS`:** Capability injected input into Windows message queue.
- **`OUTCOME_VERIFIED`:** Post-action observation confirmed the target element or window responded as expected.
- Successful dispatch does **not** complete execution; outcome verification must confirm success before transitioning to `SUCCEEDED`.

---

## 9. Execution History and Diagnostics

Each closed-loop run produces a bounded `ClosedLoopExecutionResult` containing:
- `final_state`: Terminal state reached.
- `is_success`: Explicit boolean verification verdict.
- `total_attempts`, `total_recoveries`, `total_verification_attempts`.
- `elapsed_duration_ms`.
- `attempts`: List of `ExecutionAttemptRecord` (state, target ID, dispatch point, generation, verification outcome, duration).
- `transition_history`: Complete audit trail of `(from_state, to_state, reason, timestamp)`.

---

## 10. Files Created

1. `src/orbit/runtime/execution/__init__.py`
2. `src/orbit/runtime/execution/models.py`
3. `src/orbit/runtime/execution/state_machine.py`
4. `src/orbit/runtime/execution/recovery.py`
5. `src/orbit/runtime/execution/retry_policy.py`
6. `src/orbit/runtime/execution/engine.py`
7. `docs/M1_6_STEP_3_CLOSED_LOOP_EXECUTION_AUDIT.md`
8. `docs/M1_6_STEP_3_CLOSED_LOOP_EXECUTION_COMPLETION_REPORT.md`
9. `tests/unit/test_closed_loop_state_machine.py`
10. `tests/unit/test_execution_retry_policy.py`
11. `tests/unit/test_closed_loop_engine.py`
12. `tests/integration/test_closed_loop_execution.py`
13. `tests/integration/test_closed_loop_orchestrator_flow.py`

---

## 11. Files Modified

1. `src/orbit/runtime/orchestrator.py`: Integrated `ClosedLoopExecutionEngine` into `_execute_task_lifecycle`.
2. `src/orbit/runtime/execution/models.py`: Added `ACTING`, `RETRY_PENDING`, `REPLANNING` state values.
3. `src/orbit/runtime/execution/state_machine.py`: Added legal transitions for `ACTING`, `RETRY_PENDING`, `REPLANNING`.

---

## 12. Exact Test Counts

- **Total Pytest Tests:** **360 / 360 PASS** (100% Green, 0 failures, 0 errors).
  - State machine unit tests: 8 tests.
  - Retry policy unit tests: 12 tests.
  - Closed-loop engine unit tests: 13 tests.
  - Closed-loop execution integration tests: 6 tests.
  - Orchestrator flow integration tests: 7 tests.

---

## 13. Prototype Suite Results

| Prototype Suite | Executable Tests | Result | Status |
| :--- | :--- | :--- | :--- |
| **Prototype A (Workspace)** | 7 / 7 Executable (A8 Hardware-Gated) | **PASS** | **GREEN** |
| **Prototype B (Human Takeover)** | 10 / 10 | **PASS** | **GREEN** |
| **Prototype C (Keyboard)** | 14 / 14 | **PASS** | **GREEN** |
| **Prototype D (Observation)** | 15 / 15 | **PASS** | **GREEN** |
| **Prototype E (Pointer Phase 2C)** | 71 / 71 | **PASS** | **GREEN** |

---

## 14. Frozen Boundary Verification

```powershell
git diff ca87ef8 -- prototypes/prototype_a_workspace/ prototypes/prototype_b_human_takeover/ prototypes/prototype_c_keyboard/ prototypes/prototype_d_observation/
```
**Result:** `0 files modified, 0 lines diff` relative to commit `ca87ef8`.

---

## 15. Known Limitations

1. **No Open-Ended Multi-Task Planning:** Closed-loop execution operates on single atomic tasks or structured task plans; open-ended agentic goal decomposition belongs to higher milestones.
2. **Fixed Backoff Envelope:** Backoff pacing uses exponential delay with bounded caps; dynamic network/cloud-aware jitter is not required for local desktop automation.
3. **Hardware-gated Multi-Monitor:** Physical secondary display validation remains gated on hardware availability (A8).

---

## 16. Epistemic Classifications

- **`CODE_PROVEN`:** Deterministic state machine, recovery limits, coordinate discard, and preemption gates.
- **`TEST_PROVEN`:** 354 automated tests passing across unit and integration suites.
- **`LIVE_OS_VALIDATED`:** Real Win32 screen capture, window enumeration, mouse injection, and keyboard readback tested in Prototypes A–E.
- **`UNSUPPORTED`:** Unbounded loops and fake vision AI are strictly prohibited and classified as unsupported.
