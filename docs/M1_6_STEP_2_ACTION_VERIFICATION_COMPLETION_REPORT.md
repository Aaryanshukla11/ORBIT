# ORBIT Milestone M1.6 Step 2 — Post-Action Verification Engine Completion Report

**Milestone:** M1.6 Step 2 — Post-Action Verification Engine  
**Status:** COMPLETE & GREEN  
**Host Platform:** Windows 11 AMD64 (`Windows-11-10.0.26200-SP0`)  
**Python Runtime:** 3.13.7  
**Test Suite Verdict:** 302 / 302 PASSING (100% Green)  
**Frozen Prototype Boundaries (A–D):** ZERO DIFF relative to commit `ca87ef8`

---

## 1. Executive Summary & Verification Engine Contract

Milestone M1.6 Step 2 completes the architectural transformation of ORBIT's execution loop from open-loop dispatch into an evidence-backed verification engine.

Before M1.6 Step 2, ORBIT suffered from the standard robotic process automation flaw: `dispatch succeeded == action succeeded`. In reality, pointer injection only confirms that the OS message queue accepted mouse input; it offers zero evidence that a UI target responded, focused, opened, or updated.

M1.6 Step 2 introduces a deterministic, fail-closed verification pipeline:
```
Observe (Pre-Action Snapshot)
    ↓
Target Resolution & Action Dispatch
    ↓
Post-Action State Check (Takeover & Cancellation Invariants)
    ↓
Observe (Post-Action Snapshot)
    ↓
ActionVerifier.verify(pre, post, expected_outcome)
    ↓
[VERIFIED_SUCCESS | VERIFIED_FAILURE | INCONCLUSIVE | STALE_EVIDENCE | UNSUPPORTED]
    ↓
[COMPLETED] or [FAIL-CLOSED: ActionStage.FAILED + ErrorDetail]
```

### Core Invariants Enforced
1. **Event Dispatch is Never Proof of Success:** Successful injection via Win32 `SendInput` or mock pointer is strictly classified as dispatch completion, never verification success.
2. **Fresh Evidence Mandatory:** Post-action verification requires fresh pre- and post-action observation evidence. If an identical snapshot is reused, or if evidence is marked stale, verification rejects the action fail-closed as `STALE_EVIDENCE`.
3. **Generation Parity Check:** If the desktop topology generation changes between pre- and post-action captures, verification rejects the comparison fail-closed as `STALE_EVIDENCE`.
4. **Honest Confidence:** No fabricated `1.0` confidence scores. Confidence scores strictly reflect evidence strength (e.g. `0.95` for multi-source confirmation, `0.90` for element matching, `0.80` for general delta, `0.0` for failures/unsupported).
5. **Fail-Closed Strategy:** Any action requiring verification that yields `VERIFIED_FAILURE`, `STALE_EVIDENCE`, or `UNSUPPORTED` immediately marks the action `ActionStage.FAILED`, records structured diagnostics, emits runtime events, and terminates execution.
6. **No Fake Perception:** Unsupported capabilities (such as OCR or ungrounded VLM heuristics) return `UNSUPPORTED` and fail closed.

---

## 2. Baseline & Prototype Audit Matrix

| Component / Test Suite | Prior Baseline | Step 2 Verified Baseline | Verdict |
| :--- | :--- | :--- | :--- |
| **Full Pytest Suite** | 278 / 278 PASS | **302 / 302 PASS** (+24 tests) | **GREEN** |
| **Prototype A Formal Suite** | 7 / 7 PASS (A8 Gated) | 7 / 7 PASS (A8 Hardware-Gated) | **GREEN** |
| **Prototype B Formal Suite** | 10 / 10 PASS | 10 / 10 PASS | **GREEN** |
| **Prototype C Formal Suite** | 14 / 14 PASS | 14 / 14 PASS | **GREEN** |
| **Prototype D Formal Suite** | 15 / 15 PASS | 15 / 15 PASS | **GREEN** |
| **Prototype E Phase 2C Suite**| 71 / 71 PASS | 71 / 71 PASS | **GREEN** |
| **Frozen Prototypes A–D Diff**| 0 lines diff | **0 lines diff (`ca87ef8`)** | **PRESERVED** |

---

## 3. Verification Subsystem Architecture

The post-action verification engine resides in `src/orbit/runtime/verification/` and is fully decoupled from capability adapters:

```
src/orbit/runtime/verification/
├── __init__.py           # Public exports (ActionVerifier, models, evaluators)
├── models.py             # Strongly typed domain contracts & enums
├── evidence.py           # Snapshot diagnostic summary & evidence extraction
├── strategies.py         # Concrete deterministic evaluators
└── verifier.py           # ActionVerifier coordinator & safety validation gates
```

### Key Models (`models.py`)
- **`VerificationOutcome` (Enum):** Discrete outcomes:
  - `VERIFIED_SUCCESS`: Strong evidence confirms expected state transition occurred.
  - `VERIFIED_FAILURE`: Strong evidence demonstrates expected state did not occur.
  - `INCONCLUSIVE`: Insufficient or ambiguous evidence to evaluate outcome.
  - `STALE_EVIDENCE`: Post-action snapshot stale, identical, or generation mismatch.
  - `UNSUPPORTED`: Requested strategy not backed by available capabilities.
- **`VerificationStrategy` (Enum):**
  - `ACCESSIBILITY_STATE_CHANGE`: Compare UI control / MSAA / UIA state.
  - `WINDOW_STATE_CHANGE`: Compare top-level window list or foreground focus.
  - `TARGET_PRESENCE_CHANGE`: Verify element appearance or dismissal.
  - `OBSERVATION_STATE_DELTA`: General observable desktop state delta.
  - `VISUAL_SEMANTIC`: Visual/OCR comparison (explicitly unsupported in current runtime).
- **`ExpectedOutcome` (Pydantic Model):** Declared intent of the expected outcome, including `outcome_type`, `strategy`, `target_id`, `window_title`, `target_hwnd`, `expected_property`, and `expected_value`.
- **`ActionVerificationResult` (Pydantic Model):** Authoritative verification result containing discrete outcome, strategy used, evidence-backed confidence, pre/post generation IDs, detected changes, and failure reasons.

---

## 4. Epistemic Confidence Model (Zero Fabricated Confidence)

ORBIT strictly rejects arbitrary `1.0` confidence scores for perception and verification:
- **`0.95` Confidence:** Deterministic multi-source confirmation (e.g. Win32 HWND closed and confirmed gone from window list; or UIA element property updated to expected boolean/string).
- **`0.90` Confidence:** Single-provider property delta or window presence check without secondary cross-check.
- **`0.80` Confidence:** General observable UI state delta (e.g. window count changed or element count delta detected without target identity assertion).
- **`0.50` Confidence:** Ambiguous or non-deterministic state delta.
- **`0.30` Confidence:** Zero observable changes detected when no specific outcome was declared (`INCONCLUSIVE`).
- **`0.0` Confidence:** Failed verification, stale evidence, or unsupported strategies.

---

## 5. Evidence Hygiene & Staleness Invariants

`ActionVerifier.verify()` enforces strict evidence hygiene before evaluating any strategy:
1. **Missing Snapshot Check:** If `pre_snapshot` or `post_snapshot` is missing, returns `INCONCLUSIVE` (`confidence=0.0`) with diagnostic error.
2. **Identical Snapshot Check:** If `post_snapshot.snapshot_id == pre_snapshot.snapshot_id`, returns `STALE_EVIDENCE` fail-closed.
3. **Stale Evidence Check:** If `post_snapshot.is_stale` is True, returns `STALE_EVIDENCE` fail-closed.
4. **Desktop Generation Parity:** If `post_snapshot.generation_id != pre_snapshot.generation_id`, returns `STALE_EVIDENCE` fail-closed (geometry shift prevents direct comparison).

---

## 6. Window State Transition Evaluator

Implemented in `src/orbit/runtime/verification/strategies.py:evaluate_window_state_change`:
- **`WINDOW_APPEARED`:** Evaluates if a new window matching `window_title` or `target_hwnd` appeared in `post_snapshot` that was not present in `pre_snapshot`.
- **`WINDOW_CLOSED`:** Evaluates if a target window present in `pre_snapshot` is confirmed closed in `post_snapshot`. If target remains open, returns `VERIFIED_FAILURE`.
- **`WINDOW_FOCUSED`:** Evaluates whether `post_snapshot.foreground_window` matches the declared `window_title` and `target_hwnd`.

---

## 7. Accessibility State Transition Evaluator

Implemented in `src/orbit/runtime/verification/strategies.py:evaluate_accessibility_state_change`:
- **`TARGET_DISAPPEARED`:** Confirms that a target UI element present in `pre_snapshot` (e.g. a dismissed modal dialog or clicked banner) is absent in `post_snapshot`.
- **`TARGET_APPEARED`:** Confirms that a newly triggered UI element (e.g. a dropdown menu or notification toast) appeared in `post_snapshot`.
- **`ELEMENT_STATE_CHANGED`:** Compares accessible properties (e.g. `is_focused`, `is_enabled`, `value`) against declared expected values.

---

## 8. General Observation Delta Evaluator

Implemented in `src/orbit/runtime/verification/strategies.py:evaluate_observation_state_delta`:
- Detects foreground window handle changes.
- Detects new windows opened or existing windows closed.
- Detects new accessible elements created or destroyed.
- If changes occur: returns `VERIFIED_SUCCESS` (`confidence=0.80`).
- If no changes occur and `ANY_OBSERVABLE_CHANGE` was expected: returns `VERIFIED_FAILURE`.
- If no changes occur and no specific outcome was declared: returns `INCONCLUSIVE` (`confidence=0.30`).

---

## 9. Unsupported Strategies (No Fake OCR/Vision)

ORBIT's verification engine maintains strict epistemic honesty:
- Requesting `VerificationStrategy.VISUAL_SEMANTIC` immediately returns `VerificationOutcome.UNSUPPORTED` (`confidence=0.0`).
- The runtime refuses to fabricate mock OCR matches or hallucinate computer vision bounding boxes.
- `UNSUPPORTED` outcomes fail closed, preventing silent open-loop execution under false safety claims.

---

## 10. Orchestrator Integration & Fail-Closed Lifecycle

`OrbitOrchestrator._execute_action()` in `src/orbit/runtime/orchestrator.py` integrates verification cleanly:
1. **Pre-Action Snapshot:** Automatically captures fresh pre-action observation if the action requires verification.
2. **Capability Dispatch:** Dispatches pointer or keyboard action to target capability.
3. **Post-Dispatch Checks:** Verifies cancellation token and human takeover state.
4. **Transition to VERIFYING:** Transitions `action.stage` to `ActionStage.VERIFYING` and emits `ACTION_STAGE_CHANGED`.
5. **Post-Action Snapshot:** Captures fresh post-action observation.
6. **ActionVerifier Execution:** Calls `self._action_verifier.verify(pre, post, expected_outcome)`.
7. **Verification Mapping:** Populates `action.verification` with `VerificationResult`.
8. **Fail-Closed Gate:** If outcome is `VERIFIED_FAILURE`, `STALE_EVIDENCE`, or `UNSUPPORTED`:
   - Sets `action.stage = ActionStage.FAILED`
   - Populates `action.error = ErrorDetail(code=outcome, message=...)`
   - Emits `ACTION_STAGE_CHANGED` with `FAILED`
   - Raises `RuntimeError` halting the task.
9. **Success Progression:** If `VERIFIED_SUCCESS` or `INCONCLUSIVE`, transitions `action.stage` to `ActionStage.COMPLETED`.

---

## 11. Pre-Action & Post-Action Observation Evidence Pipeline

- For target-resolved plans generated via `_build_target_resolved_plan()`, the target interaction click action automatically carries an `ExpectedOutcome` derived from the resolved target intent.
- Benign and positioning actions (such as `pointer_move` without declared expectations, or synthetic development plans) complete with `VerificationStatus.PASSED` or `SKIPPED` via readback validation, preventing redundant full-system accessibility tree traversals.
- Interactive actions (`pointer_click`, `type_text`, `shortcut`) execute full pre- and post-action evidence capture.

---

## 12. Safety Preemption & Takeover Invariants during Verification

- If human takeover triggers before, during, or immediately after action dispatch or during verification, the orchestrator immediately halts:
  - Blocks further capability dispatches.
  - Aborts verification.
  - Transitions action to `ActionStage.FAILED` with error code `HUMAN_TAKEOVER_ACTIVE`.
  - Emits takeover preemption events.

---

## 13. Cancellation Token Safety

- If cancellation is requested before dispatch, during execution, or during verification:
  - Transition immediately to `ActionStage.CANCELLED`.
  - Never emit or claim `VERIFIED_SUCCESS`.
  - Safety coordinator issues emergency stop.

---

## 14. Prototype Boundary & Non-Regression Invariant Verification

- Verification against `ca87ef8` confirms that frozen prototypes A through D were untouched:
  `git diff ca87ef8 -- prototypes/prototype_a_workspace/ prototypes/prototype_b_human_takeover/ prototypes/prototype_c_keyboard/ prototypes/prototype_d_observation/` = 0 lines diff.
- Formal prototype test suites executed and verified:
  - Prototype A: 7/7 PASS (A8 Hardware-Gated)
  - Prototype B: 10/10 PASS
  - Prototype C: 14/14 PASS
  - Prototype D: 15/15 PASS
  - Prototype E: 71/71 PASS

---

## 15. Complete Automated Test Results

The test suite expanded from 278 tests to **302 tests** with 100% passing:

### Unit Tests Added (`tests/unit/test_action_verification.py` - 18 Tests)
- `test_missing_pre_action_snapshot_returns_inconclusive`: PASS
- `test_missing_post_action_snapshot_returns_inconclusive`: PASS
- `test_identical_snapshot_reuse_rejected_fail_closed`: PASS
- `test_stale_post_action_snapshot_rejected`: PASS
- `test_desktop_generation_mismatch_rejected`: PASS
- `test_unsupported_visual_semantic_strategy_rejected`: PASS
- `test_window_appeared_success`: PASS
- `test_window_appeared_failure_when_missing`: PASS
- `test_window_closed_success`: PASS
- `test_window_closed_failure_when_still_open`: PASS
- `test_window_focused_success`: PASS
- `test_target_disappeared_success`: PASS
- `test_target_disappeared_failure_when_still_present`: PASS
- `test_target_appeared_success`: PASS
- `test_element_state_property_change_success`: PASS
- `test_observable_delta_detected_success`: PASS
- `test_zero_delta_without_expectation_returns_inconclusive`: PASS
- `test_zero_delta_with_expected_change_returns_failure`: PASS

### Integration Tests Added (`tests/integration/test_action_verification_flow.py` - 6 Tests)
- `test_action_verification_success_flow`: PASS
- `test_action_verification_failure_fails_closed`: PASS
- `test_action_verification_stale_evidence_fails_closed`: PASS
- `test_action_verification_unsupported_strategy_fails_closed`: PASS
- `test_human_takeover_blocks_verification`: PASS
- `test_cancellation_preempts_action_verification`: PASS

---

## 16. Code Proven and Test Proven Matrix

| Requirement / Invariant | Status | Evidence Classification |
| :--- | :--- | :--- |
| `ActionVerifier` Subsystem Implementation | COMPLETE | `CODE_PROVEN` & `TEST_PROVEN` |
| Evidence Hygiene (Staleness / Identity / Gen Mismatch) | COMPLETE | `CODE_PROVEN` & `TEST_PROVEN` |
| Window State Transitions (`APPEARED`, `CLOSED`, `FOCUSED`) | COMPLETE | `CODE_PROVEN` & `TEST_PROVEN` |
| Accessibility State Transitions (`APPEARED`, `DISAPPEARED`, `CHANGED`) | COMPLETE | `CODE_PROVEN` & `TEST_PROVEN` |
| General Observation Delta Evaluator | COMPLETE | `CODE_PROVEN` & `TEST_PROVEN` |
| Unsupported Strategy Rejection (`VISUAL_SEMANTIC`) | COMPLETE | `CODE_PROVEN` & `TEST_PROVEN` |
| Orchestrator `VERIFYING` Lifecycle Integration | COMPLETE | `CODE_PROVEN` & `TEST_PROVEN` |
| Fail-Closed Action Termination on Verification Failure | COMPLETE | `CODE_PROVEN` & `TEST_PROVEN` |
| Human Takeover Preemption During Verification | COMPLETE | `CODE_PROVEN` & `TEST_PROVEN` |
| Cancellation Preemption During Verification | COMPLETE | `CODE_PROVEN` & `TEST_PROVEN` |
| Zero Diff on Frozen Prototypes A–D | COMPLETE | `CODE_PROVEN` |

---

## 17. Epistemic Verification Taxonomy Audit

All verifications in Milestone M1.6 Step 2 conform to ORBIT's truth criteria:
- **`LIVE_OS_VALIDATED`:** Real Win32 GDI screen capture, live window enumeration, and real hardware mouse readbacks executed in prototype acceptance suites A, B, C, D, and E.
- **`CONTROLLED_LIVE_ENVIRONMENT`:** Orchestrator execution, cancellation propagation, and takeover preemption validated under live asynchronous event loops.
- **`INTERNAL_LOGIC_VALIDATED`:** Verification strategy algorithms, confidence calculation, staleness guards, and state machine transitions tested deterministically across 302 automated tests.

---

## 18. Next Milestone Gate Transition

**Milestone M1.6 Step 2 is COMPLETE and GREEN.**
- Closed-loop recovery loops, dynamic retry mechanisms, and multi-step replanning belong to **Milestone M1.6 Step 3** and remain untouched in accordance with strict scoping instructions.
- ORBIT is ready for Milestone M1.6 Step 3.
