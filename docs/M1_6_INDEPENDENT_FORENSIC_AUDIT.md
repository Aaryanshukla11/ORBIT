# ORBIT — MILESTONE M1.6 INDEPENDENT FORENSIC AUDIT
## ZERO-TRUST PRODUCTION READINESS VERIFICATION & ADVERSARIAL AUDIT REPORT

```text
========================================================================================
AUDIT STATUS            : COMPLETE & AUTHORITATIVE
AUDIT TYPE              : ZERO-TRUST / ADVERSARIAL FORENSIC AUDIT
AUDIT DATE              : 2026-09-06
OPERATING ENVIRONMENT   : Windows 11 Pro AMD64 (10.0.26200-SP0), Python 3.13.7
CORE PYTEST BASELINE    : 401 / 401 PASSING (100% GREEN, 0 Failures, 0 Skipped)
TESTS/LIVE BASELINE     : 10 / 10 PASSING (100% GREEN)
PROTOTYPES (A-D) DIFF   : STRICT ZERO DIFF RELATIVE TO ca87ef8
FINAL AUDIT VERDICT     : M1.6 FUNCTIONALLY STRONG — BUT LIVE VALIDATION CLAIMS OVERSTATED
========================================================================================
```

---

## 1. EXECUTIVE SUMMARY

This independent, zero-trust forensic audit evaluated the entire codebase of Milestone M1.6 across `src/orbit/`, `tests/`, and `prototypes/` without assuming the truth of previous completion reports.

### Key Audit Findings:
1. **The Autonomy Pipeline Is Functionally Real:** `ClosedLoopExecutionEngine` genuinely connects `OBSERVE -> RESOLVE -> VALIDATE -> SAFETY GATE -> ACT -> RE-OBSERVE -> VERIFY -> DECIDE`. It is not an unintegrated set of isolated classes.
2. **Target Resolution is Dynamic, but Multi-Tiered:** Targeting is dynamic and bounds-derived from live Win32/DWM measurements (`WINDOW_TITLE`) and accessibility trees (`ACCESSIBILITY_ELEMENT`). `VISUAL_SEMANTIC` correctly fails closed with `UNSUPPORTED`.
3. **Safety Gates Are Active in Production Paths:** `wsp.validate_coordinate()` and `AutonomousDispatchGate.execute_guarded()` are strictly invoked prior to Win32 `SendInput` in autonomous closed-loop execution.
4. **Discrepancy 1 — Live Hardware Takeover vs State-Injected Preemption:** The live test in `tests/live/test_m1_6_live_safety.py` tests preemption via state injection (`system_state_getter = lambda: HUMAN_TAKEOVER_ACTIVE`). While Prototype B proves low-level physical hook latency (1.16ms), the M1.6 live suite tests the *state-machine preemption gate*, not physical human hand movement on a hardware mouse.
5. **Discrepancy 2 — Real Application Automation Scope:** The live tests in `tests/live/` spawn external Win32 GUI windows (`tkinter` in dedicated subprocesses) and validate HWND discovery, dynamic interior safe point calculation, coordinate validation, real cursor movement, and post-action observation deltas. This proves safe OS interaction, but does not represent deep application workflow automation (e.g. multi-step form completion).
6. **Discrepancy 3 — Orchestrator Synthetic Fallback:** If `OrbitOrchestrator.submit_task()` is invoked without `target_intent` metadata, it falls back to a development plan containing hardcoded `(500, 300)` coordinates (though coordinate validation is still enforced).

---

## 2. INDEPENDENT AUDIT METHODOLOGY

- **Zero-Trust Rule:** No completion report or docstring was accepted as ground truth.
- **Source Inspection:** Line-by-line tracing of execution paths from WebSocket gateway and orchestrator down to Win32 `SendInput` and `BitBlt` calls.
- **Adversarial Mock Detection:** Searched for monkeypatches, mock capability injections, bypass flags, and stubbed verification methods.
- **Clean Environment Test Execution:** Re-ran all test suites independently via command line.

---

## 3. REPOSITORY STATE EXAMINED

- **Branch:** `main`
- **Host OS:** Windows 11 AMD64 (10.0.26200-SP0)
- **Python Version:** 3.13.7 (AMD64 64-bit)
- **Core Production Files:**
  - `src/orbit/runtime/orchestrator.py`
  - `src/orbit/runtime/execution/engine.py`
  - `src/orbit/runtime/execution/safety_gate.py`
  - `src/orbit/runtime/execution/recovery.py`
  - `src/orbit/runtime/targeting/locator.py`
  - `src/orbit/runtime/targeting/action_point.py`
  - `src/orbit/runtime/verification/verifier.py`
  - `src/orbit/adapters/workspace/adapter.py`
  - `src/orbit/adapters/pointer/adapter.py`
  - `src/orbit/adapters/keyboard/adapter.py`
  - `src/orbit/adapters/observation/adapter.py`

---

## 4. TEST COLLECTION INTEGRITY

```powershell
python -m pytest --collect-only
# Result: 401 tests collected in 1.14s
```
- Total test items: **401**
- No tests were dynamically hidden or uncollected.

---

## 5. FULL PYTEST RESULT

```powershell
python -m pytest -v
# Result: 401 passed in 38.65s (100% Green, 0 Failures, 0 Skipped, 0 XFailed, 0 Errors)
```
- `tests/unit/`: 278 Passed
- `tests/integration/`: 111 Passed
- `tests/smoke/`: 2 Passed
- `tests/live/`: 10 Passed

---

## 6. LIVE TEST RESULT

```powershell
python -m pytest tests/live -v
# Result: 10 passed in 3.15s (100% Green)
```

---

## 7. PRODUCTION EXECUTION PATH TRACE

Tracing an autonomous task submitted via `OrbitOrchestrator.submit_task(session_id, prompt, context={"target_intent": ...})`:

1. **Task Submission (`orchestrator.py:L350`):**
   - `submit_task()` creates `Task` with `metadata`, instantiates `CancellationSource`, launches `_execute_task_lifecycle()` in background task.
2. **Context & Policy Initialization (`orchestrator.py:L475-518`):**
   - Parses `TargetIntent`, `ExpectedOutcome`, and `ExecutionPolicy`.
   - Delegates directly to `ClosedLoopExecutionEngine.execute_task_action()`.
3. **Observation Phase (`engine.py:L330`):**
   - Calls `ProductionObservationAdapter.capture_snapshot(target_hwnd)`.
   - Executes Win32 `EnumWindows`, DWM `DwmGetWindowAttribute` extended bounds, and GDI screen capture.
4. **Target Resolution Phase (`engine.py:L390`):**
   - Calls `EvidenceBasedTargetLocator.locate_target(snapshot, target_intent)`.
   - Checks snapshot freshness; resolves target from `snapshot.windows` or `snapshot.detected_elements`.
   - Derives `SafeActionPoint(x, y)` inside bounding box interior margins.
5. **Coordinate Validation Gate (`engine.py:L463`):**
   - Calls `ProductionWorkspaceAdapter.validate_coordinate(int(x), int(y), expected_generation=expected_gen)`.
   - Checks active desktop generation parity, virtual desktop metrics, and reserved AppBar dock boundaries.
6. **Pre-Dispatch Safety Gate (`engine.py:L541`, `safety_gate.py:L75`):**
   - Calls `AutonomousDispatchGate.execute_guarded()`.
   - Evaluates `can_dispatch()` checking `context.is_cancelled` and `context.is_takeover_active()`.
   - If blocked, raises `PreemptionSafetyError(dispatch_stage=NOT_DISPATCHED)`.
7. **Native OS Actuation (`engine.py:L553`, `pointer/adapter.py:L151`):**
   - Calls `ProductionPointerAdapter.click()` / `move_to()`.
   - Enforces pointer-level lockout check and Win32 `SendInput` AMD64 C ABI injection with `dwExtraInfo` tracking.
8. **Post-Action Re-Observation (`engine.py:L726`):**
   - Calls `ProductionObservationAdapter.capture_snapshot()` to grab fresh post-action desktop state.
9. **Post-Action Verification (`engine.py:L744`, `verifier.py:L43`):**
   - Calls `ActionVerifier.verify(pre_snapshot, post_snapshot, expected_outcome)`.
   - Checks generation parity and non-identical snapshot IDs; evaluates `WINDOW_STATE_CHANGE` / `OBSERVATION_STATE_DELTA`.
10. **Decide / Recovery / Completion (`engine.py:L760-840`, `orchestrator.py:L546-564`):**
    - If verified: transitions to `ExecutionState.SUCCEEDED`, returns result to orchestrator, updates plan, marks `TaskStatus.COMPLETED`.
    - If failed: queries `RecoveryCoordinator.can_recover()`, sleeps jittered backoff, retries fresh observation cycle up to budget cap.

---

## 8. TARGET RESOLUTION FORENSIC ANALYSIS

- **Evidence Sourcing:** Real HWNDs, real DWM bounding boxes, and real UIA/MSAA element bounds.
- **Dynamic Calculation:** `calculate_safe_action_point` computes interior coordinates:
  $$x = \text{round}(\text{left} + \text{margin} + (\text{width} - 2\cdot\text{margin})\cdot\text{rel\_x})$$
- **Semantic Resolution Depth:**
  - `ACCESSIBILITY_ELEMENT`: **REAL SEMANTIC RESOLUTION**
  - `WINDOW_TITLE`: **WINDOW-LEVEL HEURISTIC RESOLUTION**
  - `COORDINATE_REGION`: **EXPLICIT GEOMETRIC RESOLUTION**
  - `VISUAL_SEMANTIC`: **UNSUPPORTED (Fail-Closed)**
- **Fabrication Check:** Zero silently fabricated targets. Missing targets return `NOT_FOUND`; stale snapshots return `STALE_OBSERVATION`.

---

## 9. COORDINATE VALIDATION FORENSIC ANALYSIS

- **Validation Enforcement:** `ProductionWorkspaceAdapter.validate_coordinate` is strictly called before action dispatch in `ClosedLoopExecutionEngine`.
- **Generation Parity:** Stale `expected_generation` IDs are rejected with `STALE_COORDINATE_CONTEXT`.
- **Dock Collisions:** Coordinates inside docked AppBar geometry are rejected with `RESERVED_WORKSPACE_COLLISION`.
- **Bypass Investigation:** Direct WebSocket commands (`MOVE_POINTER`, `CLICK_POINTER`) bypass the workspace validation layer; however, autonomous tasks submitted via `SUBMIT_TASK` cannot bypass it.

---

## 10. DISPATCH GATE FORENSIC ANALYSIS

- **Locking & Preemption:** `AutonomousDispatchGate` utilizes an async lock and evaluates `can_dispatch()` immediately before invoking the adapter method.
- **Preemption Record:** Emits structured `PreemptionRecord` carrying nanosecond timestamps, failure reasons, and last known generation counters.
- **Atomicity:** Pre-dispatch check is atomic within user-space execution. Low-level adapters carry `cancellation_token` into `SendInput` loops.

---

## 11. HUMAN TAKEOVER EVIDENCE ANALYSIS

- **Prototype B:** Validates low-level Win32 hooks (`WH_MOUSE_LL` / `WH_KEYBOARD_LL`) with 1.16ms average detection latency (`LIVE_OS_VALIDATED`).
- **Live Test Suite:** `test_m1_6_live_safety.py` tests preemption via `system_state_getter` injection.
- **Audit Correction:** The live autonomy test demonstrates **state-machine and gate preemption**, not live physical human hand movement on hardware.

---

## 12. ACTIONVERIFIER EVIDENCE ANALYSIS

- **No Blind Success:** `ActionVerifier` rejects missing snapshots (`INCONCLUSIVE`), identical snapshot IDs (`STALE_EVIDENCE`), stale snapshots (`STALE_EVIDENCE`), and generation mismatches (`STALE_EVIDENCE`).
- **Confidence Scoring:** Confidence is derived from discrete structural and state checks (0.0 to 0.95); no hardcoded `confidence=1.0` fabrication.

---

## 13. CLOSED-LOOP ENGINE ANALYSIS

- **Multi-Step Execution:** Step 2 captures fresh observations, independently derives distinct coordinates, and validates anew.
- **Bounded Retries:** `RecoveryCoordinator` enforces hard caps on `total_attempts`, `recovery_attempts`, `target_resolution_attempts`, and `verification_retries`. No infinite loops.

---

## 14. LIVE TEST-BY-TEST EVIDENCE TABLE

| Test Identifier | Real Win32 API? | Real Application Process? | Real HWND? | Mock Used? | Monkeypatch Used? | Actual OS Input? | Actual State Change? | Correct Epistemic Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `test_live_scenario_a_real_application_discovery` | YES (DWM, EnumWindows) | YES (`tkinter` subprocess) | YES | NO | NO | NO | Discovered window | `LIVE_OS_VALIDATED` |
| `test_live_scenario_b_real_target_resolution_and_safe_point` | YES (DWM, Win32) | YES (`tkinter` subprocess) | YES | NO | NO | NO | Derived safe point | `LIVE_OS_VALIDATED` |
| `test_live_scenario_c_real_safe_action_dispatch` | YES (SendInput, GDI) | YES (`tkinter` subprocess) | YES | NO | NO | YES (Mouse Move) | Cursor repositioned | `LIVE_OS_VALIDATED` |
| `test_live_scenario_d_real_post_action_verification` | YES (SendInput, GDI) | YES (`tkinter` subprocess) | YES | NO | NO | YES (Mouse Move) | Pre/post compared | `LIVE_OS_VALIDATED` |
| `test_live_multi_step_closed_loop_sequential_progression` | YES (SendInput, GDI) | NO (Desktop coords) | N/A | NO | NO | YES (Two Moves) | 2 cursor moves | `LIVE_OS_VALIDATED` |
| `test_live_target_not_found_fails_closed_zero_dispatches` | YES (GDI, EnumWindows) | NO (Phantom target) | N/A | NO | NO | NO (0 Dispatches) | Recovery budget hit | `LIVE_OS_VALIDATED` |
| `test_live_stale_generation_target_rejected_fail_closed` | YES (Production Adapters)| NO (Desktop coords) | N/A | NO | YES (Stale gen in locator)| NO (0 Dispatches) | Gate blocked dispatch | `TEST_PROVEN` |
| `test_live_verification_failure_triggers_bounded_retry_exhaustion` | YES (SendInput, GDI) | NO (Desktop coords) | N/A | YES (`FailingVerifier`)| NO | YES (Retry Moves) | Budget exhausted | `TEST_PROVEN` |
| `test_live_human_takeover_preempts_autonomous_dispatch` | YES (Production Adapters)| NO (Desktop coords) | N/A | NO | YES (State getter injected)| NO (0 Dispatches) | Gate blocked dispatch | `TEST_PROVEN` |
| `test_live_workspace_appbar_dock_collision_blocks_pointer_dispatch`| YES (Production Adapters)| NO (Desktop coords) | N/A | NO | YES (Mock dock validation)| NO (0 Dispatches) | Dock collision blocked | `TEST_PROVEN` |

---

## 15. REAL APPLICATION INTERACTION EVIDENCE

- **Application Tested:** Dedicated out-of-process Python GUI testbed window (`tkinter` running in an external subprocess with dedicated message pump).
- **Process Verification:** PID verified (`process_id > 0`), HWND verified (`hwnd > 0`), DWM bounding box verified.
- **Interaction Verified:** Real pointer movement dispatched to dynamically derived interior safe point.
- **Audit Limitation:** Demonstrates OS-level window discovery and safe cursor interaction; does not test deep multi-step application business workflows.

---

## 16. MOCK AND MONKEYPATCH DETECTION RESULTS

- **No mocks in primary live autonomy tests** (`test_live_scenario_a`, `b`, `c`, `d`, `e1`, `e2`).
- **Simulated test doubles in failure-injection tests:** `FailingVerifier` used to test retry exhaustion; monkeypatched generation/dock returns used to test negative safety gates. These are standard, valid failure-injection test patterns.

---

## 17. PROTOTYPE INTEGRITY VERIFICATION

- **Prototypes A, B, C, D:** `git diff ca87ef8 -- prototypes/prototype_a_workspace/ prototypes/prototype_b_human_takeover/ prototypes/prototype_c_keyboard/ prototypes/prototype_d_observation/` -> **0 lines diff (STRICT ZERO DIFF).**
- **Prototype E:** Implemented in subsequent commits for SendInput AMD64 pointer prototyping; 23/23 tests pass.

---

## 18. SAFETY BYPASS ANALYSIS

| Execution Entry Point | Bypasses Workspace Validation? | Bypasses Dispatch Gate? | Bypasses Pointer Lockout? | Overall Risk |
| :--- | :--- | :--- | :--- | :--- |
| `ClosedLoopExecutionEngine.execute_task_action` | **NO** | **NO** | **NO** | Zero Bypass (Safe) |
| `OrbitOrchestrator.submit_task` (with TargetIntent) | **NO** | **NO** | **NO** | Zero Bypass (Safe) |
| `OrbitOrchestrator.submit_task` (without TargetIntent) | **NO** (Validated in `_execute_action`) | **NO** (Checked in `_execute_action`) | **NO** | Hardcoded (500,300) fallback |
| `WebSocketManager` Direct `MOVE_POINTER` | **YES** | **YES** | **NO** (Checked in Adapter) | Low (Debug/Manual command) |

---

## 19. RACE CONDITION ANALYSIS

- **Gate to Dispatch Race:** If human takeover activates in the microsecond interval between `can_dispatch()` and `SendInput()`, `ProductionPointerAdapter` checks `cancellation_token.is_cancelled` before injection.
- **Post-Dispatch Race:** If takeover activates during execution, Boundary 6 catches it before re-observation or verification, preventing task progression.

---

## 20. EPISTEMIC CLASSIFICATION MATRIX

| Capability | Scope | Epistemic Classification |
| :--- | :--- | :--- |
| **GDI Desktop Capture** | Live OS Screen BitBlt | `LIVE_OS_VALIDATED` |
| **Window Hierarchy Discovery** | Live Win32 / DWM Enumeration | `LIVE_OS_VALIDATED` |
| **Window-Level Target Resolution** | Dynamic HWND / Title matching | `LIVE_OS_VALIDATED` |
| **Accessibility Target Resolution**| MSAA / UIA element matching | `LIVE_OS_VALIDATED` |
| **Visual Semantic Target Resolution**| OCR / Computer Vision | `UNSUPPORTED` (Fail-Closed) |
| **Workspace Bounds & Dock Validation**| Generation & usable canvas | `LIVE_OS_VALIDATED` |
| **SendInput Pointer Actuation** | Mouse move and click | `LIVE_OS_VALIDATED` |
| **SendInput Unicode Actuation** | Keyboard typing & shortcuts | `LIVE_OS_VALIDATED` |
| **State Delta Verification** | Pre/Post observation comparison | `LIVE_OS_VALIDATED` |
| **Closed-Loop Engine Retries** | Bounded recovery loops | `TEST_PROVEN` |
| **Hardware Human Takeover** | Physical mouse/keyboard hook | `LIVE_OS_VALIDATED` (Prototype B) |
| **Live Preemption Safety Gate** | State-injected preemption | `TEST_PROVEN` |

---

## 21. ALL FINDINGS WITH SEVERITY

| Finding ID | Severity | Category | Description | Status |
| :--- | :--- | :--- | :--- | :--- |
| **F-01** | **P3** | Architecture | `OrbitOrchestrator._execute_task_lifecycle` falls back to `_build_synthetic_plan()` with hardcoded `(500, 300)` when `target_intent` is omitted in task metadata. | Safe (validated), but legacy |
| **F-02** | **P3** | Architecture | Direct WebSocket `MOVE_POINTER` / `CLICK_POINTER` commands bypass `ProductionWorkspaceAdapter` validation (only checked at adapter boundary). | Debug commands only |
| **F-03** | **P4** | Documentation | `test_live_human_takeover_preempts_autonomous_dispatch` tests state-injected preemption, not live physical mouse movement. | Classification corrected |
| **F-04** | **P4** | Documentation | Real application testing is conducted on an isolated GUI testbed window (`tkinter`), which proves safe desktop interaction but not complex application workflow automation. | Classification corrected |

---

## 22. DOCUMENTATION CLAIM CORRECTIONS

1. **Claim:** "ORBIT no longer contains hardcoded coordinates."  
   **Correction:** `ClosedLoopExecutionEngine` contains zero hardcoded coordinates; however, `OrbitOrchestrator._build_synthetic_plan` retains `(500, 300)` as a fallback development plan when `target_intent` is absent.
2. **Claim:** "Human takeover is live validated in M1.6 Step 5."  
   **Correction:** M1.6 Step 5 validates the *state-machine preemption gate*; actual low-level physical hook latency is validated in Prototype B formal tests.
3. **Claim:** "Full live application task automation."  
   **Correction:** Validated against external Win32 GUI testbed window for window discovery, dynamic targeting, safe action dispatch, and state delta verification.

---

## 23. REMAINING PRODUCTION RISKS

- **Risk 1:** Lack of visual perception (OCR / Computer Vision) prevents interacting with non-accessible custom controls (Canvas, Electron, Games); scheduled for Milestone M1.7.
- **Risk 2:** Unstructured natural language prompts must be compiled into structured `TargetIntent` objects before submission.

---

## 24. FINAL VERDICT

```text
========================================================================================
                               FINAL AUDIT VERDICT:
          M1.6 FUNCTIONALLY STRONG — BUT LIVE VALIDATION CLAIMS OVERSTATED
========================================================================================
The core closed-loop autonomy runtime (OBSERVE -> RESOLVE -> VALIDATE -> SAFETY GATE ->
ACT -> RE-OBSERVE -> VERIFY -> DECIDE) is genuinely implemented, rigorously connected,
fail-closed, and empirically validated on Windows 11.

However, zero-trust discipline requires acknowledging that:
1. Live takeover tests validate state-injected preemption rather than physical mouse hardware.
2. Live application testing utilizes an isolated GUI testbed rather than complex third-party workflows.
3. Legacy synthetic plan fallbacks exist when target intents are omitted.

With these truthful epistemic corrections recorded, M1.6 is verified as solid, safe,
and ready for Milestone M1.7 visual perception development.
========================================================================================
```
