# ORBIT PROTOTYPE E — PHASE 2 FINAL ARCHITECTURAL READINESS AUDIT REPORT
## Safe Pointer Action & Click Execution Engine (Corrections Pass C1–C6)

**Audit Date:** 2026-09-05  
**Auditor:** Independent Systems & Safety Architecture Auditor  
**Scope:** Final Pre-Implementation Corrections Pass (C1–C6), Runtime ABI Verification, TOCTOU Timing Normalization, UIPI Diagnostic Truthfulness, Unresolved State Lockout Policy, Topology Identity Fingerprints, and Phase 2A–2E Staged Implementation Sequence  
**Decision:** 🟢 **FINAL PHASE 2 ARCHITECTURE GATE PASSED — READY FOR PHASE 2A AUTHORIZATION**

---

## 1. Executive Summary & Baseline Verification

```text
Baseline Commit : ca87ef8 (docs(prototype-d): final independent closure audit)
Diff Command    : git diff ca87ef8 -- prototypes/prototype_a_workspace/ prototypes/prototype_b_human_takeover/ prototypes/prototype_c_keyboard/ prototypes/prototype_d_observation/
Diff Output     : 0 files changed, 0 insertions, 0 deletions (100% ISOLATION CONFIRMED)
Phase 1 Status  : Complete, Tested, and Frozen (14/14 tests passing, zero pointer injection)
```

This audit formalizes the 6 mandatory architectural corrections (C1–C6) required to eliminate all remaining unverified assumptions, speculative timing claims, overdiagnosed failure states, and premature scope expansions prior to authorizing any pointer interaction.

---

## 2. Formal Architectural Corrections Applied (C1–C6)

### Correction C1: Runtime ABI & Memory Layout Verification Gate
- **Weakness Discovered**: The previous specification assumed 64-bit AMD64 structure sizes ($40$ bytes for `INPUT`, $32$ bytes for `MOUSEINPUT`) purely in documentation without mandating runtime enforcement.
- **Correction Applied**:
  - Implementation Phase 2A will execute an explicit, standalone runtime ABI validator before any Win32 `SendInput` system call.
  - The validator programmatically verifies:
    1. `ctypes.sizeof(MOUSEINPUT) == 32`
    2. `ctypes.sizeof(INPUT) == 40`
    3. `MOUSEINPUT.dx` offset == 0, `MOUSEINPUT.dwFlags` offset == 12, `MOUSEINPUT.dwExtraInfo` offset == 24
    4. `INPUT.union` offset == 8
    5. `dwExtraInfo` uses a pointer-sized unsigned integer (`ctypes.c_uint64` / `ULONG_PTR`).
  - **Capability States Defined**: `ABI_VALID`, `ABI_MISMATCH`, `UNSUPPORTED_PROCESS_ARCHITECTURE`.
  - **Fail-Closed Invariant**: If ABI validation fails, pointer controller initialization throws an exception and refuses to load, completely disabling synthetic pointer injection.

---

### Correction C2: TOCTOU Timing Claim Normalization
- **Weakness Discovered**: The previous documentation cited an unmeasured "~5–20 µs context switch gap" as if it were a universal Windows guarantee.
- **Correction Applied**:
  - Speculative timing constants were eliminated from all architectural assertions.
  - **Normalized Invariant Statement**:
    $$\boxed{\text{"There is an unavoidable non-zero user-mode TOCTOU window between validation and input dispatch. Its duration is scheduler, workload, process, and hardware dependent."}}$$
  - **Empirical Measurement Discipline**: Future telemetry will measure and record empirical statistical distributions (Mean, Median, P95, P99, Min, Max) across recorded runs, while explicitly distinguishing *measured API execution latency* from the *unknowable external context-switch race window*.

---

### Correction C3: UIPI & Delivery Failure Diagnostic Truthfulness
- **Weakness Discovered**: The specification previously conflated Layer 7 zero-mutation outcomes with "UIPI silent message drops" without independent process elevation evidence.
- **Correction Applied**:
  - Prohibited diagnosing UIPI solely based on $M=N$ return with absent target state change.
  - Defined truthful, granular failure classifications:
    - `DISPATCH_ACCEPTED`: `SendInput` returned $M=N$ (Layer 4).
    - `TARGET_EFFECT_NOT_OBSERVED`: Target application callback or state did not mutate (Layer 7).
    - `PERMISSION_RESTRICTION_POSSIBLE`: Target PID is running at higher integrity level (e.g. Administrator) than ORBIT.
    - `TARGET_UNRESPONSIVE`: Target application message loop is hung (`IsHungAppWindow`).
    - `VERIFICATION_UNAVAILABLE`: Target application lacks accessible readback hooks.

---

### Correction C4: Unresolved Pointer Lockout Contract & Recovery Policy
- **Weakness Discovered**: The unresolved button down state lacked an explicit state boundary between ORBIT's internal tracking and Windows kernel logical button states, and needed an explicit unlock policy.
- **Correction Applied**:
  - **State Model Distinction**:
    - `ORBIT_INTERNAL_STATE_UNRESOLVED`: ORBIT knows it issued synthetic `BUTTON_DOWN` but emergency `BUTTON_UP` could not be confirmed.
    - `OS_BUTTON_STATE_CONFIRMED_DOWN`: Whether Windows logical button state is down (queried via `GetAsyncKeyState`, but ambiguous if user is also holding a button).
  - **Lockout Policy**:
    1. If emergency sanitization UP fails ($M=0$), the system immediately enters `UNRESOLVED_LOCKED`.
    2. `PointerStateManager.is_locked_unresolved` is set to `True`.
    3. **All subsequent pointer actions (movements, clicks, button-downs) are hard-rejected** with `UNRESOLVED_POINTER_STATE`.
    4. **Prohibited Unlocks**: The controller will NEVER automatically unlock merely because a new action starts, a cancellation token resets, or time passes.
    5. **Recovery Policy**: Exiting `UNRESOLVED_LOCKED` requires an explicit administrative/testbed recovery protocol that confirms `GetAsyncKeyState` is clear and issues a fresh verified hardware release packet.

---

### Correction C5: Deterministic Topology Identity Fingerprint Contract
- **Weakness Discovered**: Display topology checks were described qualitatively without an immutable fingerprint representation.
- **Correction Applied**:
  - Defined immutable data contract:
    ```python
    @dataclass(frozen=True)
    class VirtualDesktopTopologyFingerprint:
        origin_x: int
        origin_y: int
        width: int
        height: int
        monitor_count: int
        timestamp_ns: int
    ```
  - `coordinate_mapper.py` attaches this fingerprint to every coordinate normalization.
  - Immediately before `SendInput` dispatch, the controller queries current display metrics and computes the live fingerprint. If any dimension, origin, or monitor count differs:
    - Dispatch is rejected with `ValidationFailureReason.TOPOLOGY_MUTATED`.
    - Coordinates are never injected against stale display topology.
  - **Limitation Disclosed**: This pre-dispatch check dramatically reduces the stale coordinate window, but does not eliminate topology changes occurring after the check during kernel dispatch.

---

### Correction C6: Staged Implementation Sequence (Phase 2A → 2E)
- **Weakness Discovered**: Attempting full movement, clicks, and drags simultaneously increases cross-layer debugging complexity and safety risk.
- **Correction Applied**:
  - Frozen Phase 2 implementation into 5 isolated sub-phases (Phase 2A to Phase 2E).
  - **Drag operations are explicitly excluded** from the initial Phase 2 sequence.

```
┌────────────────────────────────────────────────────────────────────────┐
│             PHASE 2 STAGED IMPLEMENTATION & VALIDATION SEQUENCE        │
├────────────────────────────────────────────────────────────────────────┤
│ PHASE 2A: ABI Validation & SendInput Foundation                        │
│   - ctypes sizeof(INPUT)==40, sizeof(MOUSEINPUT)==32, offset checks    │
│   - INPUT packet constructor with dwExtraInfo ORBIT signature          │
│   - Zero-action dry validation; fail-closed on ABI mismatch            │
├────────────────────────────────────────────────────────────────────────┤
│ PHASE 2B: Absolute Cursor Movement Only                                │
│   - Virtual desktop SendInput coordinates (0xC001 flags)               │
│   - Post-dispatch GetCursorPos verification (±1px tolerance)           │
│   - No clicks, no button depressions                                   │
├────────────────────────────────────────────────────────────────────────┤
│ PHASE 2C: Single Button State Transactions & Lockout Machine           │
│   - Isolated synthetic DOWN, isolated synthetic UP                     │
│   - PointerStateManager ownership tracking                             │
│   - Partial dispatch detection, emergency UP, UNRESOLVED_LOCKED lockout│
├────────────────────────────────────────────────────────────────────────┤
│ PHASE 2D: Controlled Click Transactions                                │
│   - Compound [MOVE -> Gate -> DOWN -> Dwell -> Gate -> UP]             │
│   - Controlled multi-widget Tkinter target callback verification       │
├────────────────────────────────────────────────────────────────────────┤
│ PHASE 2E: Full Integration & Multi-Tier Validation                     │
│   - Prototype D snapshot adapter + live target validator integration   │
│   - Topology fingerprint verification + cancellation preemption gates  │
│   - Formal acceptance matrix E25–E41 execution                         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Remaining Unavoidable Windows OS Limitations

1. **Windows Shared Logical Button State**: Windows User32 maintains only a single global logical button state (`GetAsyncKeyState`). Synthetic UP resets the shared logical state to UP even if a user is physically holding a hardware mouse switch. Software cannot isolate hardware switch contacts from the Windows input queue.
2. **User-Mode Non-Zero TOCTOU Window**: The scheduling gap between user-mode pre-dispatch validation and kernel `SendInput` processing cannot be eliminated in Windows user space.
3. **UIPI Asymmetric Injection Visibility**: Non-elevated processes cannot query integrity levels or observe message queues of elevated processes directly. Layer 7 observable state readback is the only reliable indicator of real-world task success.

---

## 4. Invariant & Safety Confirmations

- **Zero Pointer Injection Occurred**: 0 calls to Win32 `SendInput`, 0 mouse clicks, 0 cursor displacements.
- **Frozen Prototypes Untouched**: Prototypes A, B, C, and D remain 100% frozen (0 diff lines against `ca87ef8`).
- **Phase 1 Foundation Intact**: 14/14 tests in `phase1_validation.py` remain fully functional and passing.

---

## 5. Final Readiness Verdict

$$\boxed{\mathbf{\text{\Large 🟢 FINAL PHASE 2 ARCHITECTURE GATE PASSED}}}$$

The specification has been hardened with runtime ABI validation, TOCTOU timing normalization, truthful diagnostic states, unresolved state hard-lockouts, topology identity fingerprints, and staged Phase 2A–2E sequencing.

**Phase 2A (ABI Validation & Foundation) is approved for implementation upon user command.**
