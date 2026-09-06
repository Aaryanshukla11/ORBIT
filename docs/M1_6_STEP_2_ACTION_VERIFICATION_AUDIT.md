# M1.6 STEP 2: POST-ACTION VERIFICATION ENGINE AUDIT

**Milestone:** M1.6 Step 2 (Audit Phase)  
**Date:** September 6, 2026  
**Auditor:** Antigravity AI (Pair Programming with Engineering Operator)  
**Host Environment:** Windows 11 AMD64 (Build 10.0.26200), Python 3.13.7  
**Baseline Status:** 278 / 278 Pytest PASS | Frozen Prototype Diff = 0 lines (`ca87ef8`)  
**Document Status:** COMPLETE & AUTHORITATIVE

---

## 1. Executive Summary & Core Finding

Milestone M1.6 Step 1 established semantic target resolution and pre-dispatch workspace validation. However, the runtime still equates:
> *"Pointer event was successfully dispatched to Win32 SendInput"* $\iff$ *"The action actually achieved its intended outcome."*

In `src/orbit/runtime/orchestrator.py:688-693`, post-action verification is completely bypassed:
```python
action.verification = VerificationResult(
    status=VerificationStatus.PASSED,
    confidence=1.0,
    details={"verification_mode": "mock_immediate"},
)
```
Every action passes unconditionally with artificial `1.0` confidence regardless of whether the clicked button responded, a window appeared, focus shifted, or the application crashed.

M1.6 Step 2 replaces this hardcoded mock with an evidence-driven **ActionVerifier** engine that captures fresh post-action observation, compares it against a pre-action baseline, evaluates state transitions, and enforces explicit verification outcomes (`VERIFIED_SUCCESS`, `VERIFIED_FAILURE`, `INCONCLUSIVE`, `STALE_EVIDENCE`, `UNSUPPORTED`).

---

## 2. Forensic Audit Questions & Repository Evidence

### Question 1: How an Action is Currently Considered Successful
- **Current Reality:** In `OrbitOrchestrator._execute_action()` (`src/orbit/runtime/orchestrator.py:688-697`), as soon as the capability method (e.g. `ptr.click()` or `kbd.type_text()`) returns without raising an unhandled exception, the orchestrator immediately sets:
  - `action.stage = ActionStage.VERIFYING`
  - `action.verification = VerificationResult(status=VerificationStatus.PASSED, confidence=1.0, details={"verification_mode": "mock_immediate"})`
  - `action.stage = ActionStage.COMPLETED`
- **Safety Defect:** A click that misses its control or lands on an unresponsive UI element is falsely recorded as 100% verified success.
- **Classification:** `CODE_PROVEN`.

---

### Question 2: What Observation Evidence is Available Before an Action
- **Available Data:**
  - `ObservationSnapshot` captured during target resolution in `_execute_task_lifecycle`:
    - `snapshot.foreground_window`: Win32 HWND, title, process name, bounds, focus state.
    - `snapshot.windows`: Complete list of enumerated visible top-level windows.
    - `snapshot.detected_elements`: UI Automation, MSAA, and Win32 controls with bounds, names, roles, control types, automation IDs, and enabled/focus states.
    - `snapshot.desktop_geometry`: Virtual desktop bounds.
    - `snapshot.generation_id`: Desktop topology and AppBar reservation generation.
    - `snapshot.timestamp_ns`: Monotonic capture timestamp.
    - `snapshot.freshness_state`: Evaluated freshness (`FRESH`, `AGING`, `STALE`).
  - Target provenance: `ResolvedTarget` carrying `target_id`, `bounding_box`, `evidence` (source, identifier, name, role), and `desktop_generation_id`.
- **Classification:** `CODE_PROVEN` & `LIVE_OS_VALIDATED`.

---

### Question 3: How a Fresh Observation Can Be Obtained After an Action
- **Available Mechanism:**
  - `ProductionObservationAdapter.capture_snapshot()` executes a fresh capture in a worker thread (`src/orbit/adapters/observation/adapter.py:176-254`):
    1. Queries Win32 GDI virtual desktop bounds.
    2. Queries live foreground window (`GetForegroundWindow` + DWM extended bounds).
    3. Enumerates live visible windows.
    4. Gathers live MSAA / UI Automation accessibility elements.
    5. Evaluates snapshot freshness and stamps monotonic timestamp and `generation_id`.
  - `MockObservationAdapter.capture_snapshot()` produces deterministic fresh snapshots for tests.
- **Classification:** `CODE_PROVEN` & `LIVE_OS_VALIDATED`.

---

### Question 4: Which Verification Mechanisms are Genuinely Available Today
- **1. Window State Transitions (`WINDOW_STATE_CHANGE`):** **GENUINELY AVAILABLE.**
  - Pre- and post-action `snapshot.windows` and `snapshot.foreground_window` provide ground-truth evidence of:
    - New window opened (e.g. clicking an app icon or menu item spawned an expected HWND/title).
    - Window closed (e.g. clicking a close button destroyed the target HWND).
    - Foreground focus changed (e.g. target window became active foreground window).
- **2. Accessibility Control State Transitions (`ACCESSIBILITY_STATE_CHANGE`):** **GENUINELY AVAILABLE.**
  - Pre- and post-action `snapshot.detected_elements` provide ground-truth evidence of:
    - Element state change (e.g. checkbox checked, toggle changed, focused state updated).
    - Element appearance (e.g. dropdown menu or dialog controls appeared).
    - Element disappearance (e.g. clicked modal or button dismissed).
- **3. Target Presence Transitions (`TARGET_PRESENCE_CHANGE`):** **GENUINELY AVAILABLE.**
  - Checking whether the specific target control still exists or was consumed by the action.
- **4. Image/Screenshot Comparison (Pixel/OCR Diffing):** **NOT IMPLEMENTED IN PRODUCTION.**
  - `capture_screen()` returns raw JPEG frames, but no neural visual models or production image-diff engines are wired to the runtime. Claiming OCR or VLM verification is explicitly `UNSUPPORTED`.
- **Classification:** `CODE_PROVEN` (No fake perception claims).

---

### Question 5: Existing Generation and Freshness Guarantees
- **Guarantees:**
  - `desktop_generation_id`: Authoritative counter in `WorkspaceStateManager`.
  - Stamped on pre-action `ObservationSnapshot`, `ResolvedTarget`, `SafeActionPoint`, and passed into `workspace.validate_coordinate()`.
  - If a display topology change or AppBar resize occurs during/after action execution, `post_snapshot.generation_id` will not match `pre_action.generation_id`.
  - In such cases, the verifier must report `STALE_EVIDENCE` or `INCONCLUSIVE` instead of claiming success.
- **Classification:** `CODE_PROVEN` & `TEST_PROVEN`.

---

### Question 6: Where the ActionVerifier Should Integrate
- **Integration Boundary:**
  - Location: `src/orbit/runtime/verification/`
  - Integration Point: `OrbitOrchestrator._execute_action()`
  - Sequence:
    1. Preserve `pre_action_snapshot` and `expected_outcome` before action dispatch.
    2. Dispatch action to capability (`ptr.click`, `ptr.move_to`, `kbd.type_text`, etc.).
    3. Check `cancel_token` and `HUMAN_TAKEOVER_ACTIVE`.
    4. Capture fresh `post_action_snapshot = await obs.capture_snapshot()`.
    5. Invoke `verifier.verify(pre_evidence, post_evidence, expectation)`.
    6. Populate `action.verification` with typed `VerificationResult`.
    7. If `VERIFIED_FAILURE`: fail closed! Transition `action.stage = ActionStage.FAILED`, record structured error, raise `RuntimeError`.
    8. If `VERIFIED_SUCCESS`: transition `action.stage = ActionStage.COMPLETED`.
- **Classification:** `CODE_PROVEN`.

---

## 3. Step 2 Subsystem Architecture

### Module Layout
```
src/orbit/runtime/verification/
├── __init__.py           # Public exports
├── models.py             # VerificationOutcome, VerificationStrategy, VerificationEvidence, VerificationResult
├── strategies.py         # Concrete verification strategy evaluators
├── evidence.py           # Pre/post observation evidence extraction
└── verifier.py           # Core ActionVerifier engine and policy evaluator
```

### Verification Outcome State Model
```python
class VerificationOutcome(str, Enum):
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"   # Strong evidence confirms expected state transition
    VERIFIED_FAILURE = "VERIFIED_FAILURE"   # Strong evidence confirms failure or contradictory state
    INCONCLUSIVE = "INCONCLUSIVE"           # Insufficient or ambiguous evidence
    STALE_EVIDENCE = "STALE_EVIDENCE"       # Post-action snapshot stale or desktop generation changed
    UNSUPPORTED = "UNSUPPORTED"             # Requested verification type unavailable
```

### Fail-Closed Decision Flow
```
Action Executed
       ↓
Pre/Post Generation Parity Check
       ↓ Mismatch? → STALE_EVIDENCE (Fail closed)
Freshness Check
       ↓ Stale? → STALE_EVIDENCE (Fail closed)
Select Strategy:
  - WINDOW_STATE_CHANGE: Compare HWNDs, foreground focus, titles
  - ACCESSIBILITY_STATE_CHANGE: Compare UIA/MSAA element states
  - TARGET_PRESENCE_CHANGE: Verify target appearance/dismissal
  - VISUAL_SEMANTIC: Return UNSUPPORTED (No fake AI)
       ↓
Evaluate State Transition
       ↓
VERIFIED_SUCCESS  → Complete Action
VERIFIED_FAILURE  → Fail Action (Fail closed)
INCONCLUSIVE      → Policy Decision (Flagged diagnostically)
```

---

## 4. Audit Sign-Off
Forensic audit complete. Baseline verified green (278/278). Frozen prototype boundary diff = 0.
Ready to proceed with M1.6 Step 2 implementation.
