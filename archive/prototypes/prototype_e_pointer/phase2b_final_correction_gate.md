# ORBIT PROTOTYPE E — PHASE 2B FINAL ARCHITECTURAL CORRECTION GATE REPORT
## Pre-Implementation Safety, Evidence & Gateway Contracts

**Audit Date:** 2026-09-05  
**Auditor:** Independent Systems & Safety Architecture Auditor  
**Scope:** Phase 2B Pre-Implementation Contract Corrections (Corrections 1–6): Evidence Semantics, Desktop Attachment Scope, Topology Identity Boundaries, Single Native Dispatch Gateway, GetLastError Discipline, and Implementation Invariants.  
**Pre-Implementation Non-Action Invariant:** **0 `SendInput` calls / 0 clicks / 0 cursor movements / 0 Phase 2B implementation modules created.**  
**Status Verdict:** 🟢 **READY FOR PHASE 2B IMPLEMENTATION**

---

## 1. Frozen Baseline Verification

```text
Baseline Commit : ca87ef8 (docs(prototype-d): final independent closure audit)
Diff Command    : git diff ca87ef8 -- prototypes/prototype_a_workspace/ prototypes/prototype_b_human_takeover/ prototypes/prototype_c_keyboard/ prototypes/prototype_d_observation/
Diff Output     : 0 files changed, 0 insertions, 0 deletions (100% FROZEN ISOLATION CONFIRMED)
Git Status      : Clean branch tracking; 0 modifications in frozen Prototypes A, B, C, D
Phase 1 Status  : 14/14 tests passing
Phase 2A Status : 10/10 tests passing (Fail-Closed ABI Gate Active)
```

---

## 2. Detailed Architectural Corrections (Corrections 1–6)

### Correction 1 — SendInput Evidence Semantics & Observable Boundary
- **Prior Flaw**: Architectural documentation previously claimed *"SendInput proves insertion into the User32 raw input queue"*, asserting an assumption about undocumented kernel/subsystem queue internals.
- **Correction Applied**:
  - Removed all unverified claims regarding internal Windows queue internals.
  - Replaced with observable evidence boundaries:
    $$\boxed{\text{SendInput accepted packet count}\ \ne\ \text{cursor destination observed}\ \ne\ \text{continuous cursor control}\ \ne\ \text{target-level success}}$$
  - Formalized observable evidence states in [app_types.py](file:///c:/Users/Aaryan%20shukla/OneDrive/Desktop/ORBIT/prototypes/prototype_e_pointer/app_types.py):
    - `DISPATCH_ACCEPTED`: Win32 `SendInput` returned $M = 1$ for $N = 1$ packet.
    - `DISPATCH_ZERO`: Win32 `SendInput` returned $M = 0$.
    - `DISPATCH_PARTIAL_NOT_APPLICABLE`: Explicitly labeled for $N = 1$.
    - `MOVEMENT_VERIFIED` / `CURSOR_DESTINATION_OBSERVED`: Post-dispatch `GetCursorPos()` observed destination within configured $\pm 1\text{px}$ tolerance.
    - `CURSOR_READBACK_MISMATCH`: Post-dispatch `GetCursorPos()` observed coordinates outside tolerance.
    - `DISPATCHED_BUT_MOVEMENT_UNVERIFIED`: Post-dispatch readback failed or was interrupted before verification.

---

### Correction 2 — Desktop Attachment Scope & Minimal API Surface
- **Prior Flaw**: Preliminary notes referenced `OpenInputDesktop` and `SetThreadDesktop`, introducing unnecessary desktop switching complexity into the core architecture.
- **Correction Applied**:
  - `OpenInputDesktop` and `SetThreadDesktop` are **strictly excluded** from the Phase 2B pointer movement architecture.
  - Phase 2B relies exclusively on the minimal, standard Windows User32 API surface:
    1. `user32.GetSystemMetrics` (virtual desktop dimensions and origin).
    2. `user32.SendInput` (input packet injection via single gateway).
    3. `user32.GetCursorPos` (physical cursor position readback).
    4. `kernel32.GetLastError` (diagnostic error capture on dispatch zero).
    5. `user32.SetProcessDpiAwarenessContext` / `GetProcessDpiAwarenessContext` (Per-Monitor V2 DPI awareness).
  - No desktop-switching APIs are permitted in Phase 2B unless separately authorized.

---

### Correction 3 — Topology Identity Boundary & Distinction
- **Prior Flaw**: Previous audits risked implying that `VirtualDesktopTopologyIdentity(origin_x, origin_y, width, height, monitor_count)` detected all theoretical multi-monitor configuration shifts.
- **Correction Applied**:
  - The architecture explicitly distinguishes:
    1. **`GLOBAL_COORDINATE_SPACE_MUTATION_DETECTED`**: Guaranteed detection of virtual desktop origin shifts, resolution changes, monitor count additions/removals, or bounding box resizing.
    2. **`INTERNAL_MONITOR_ARRANGEMENT_MUTATION_POSSIBLY_UNDETECTED`**: An internal monitor swap (e.g. swapping positions of two identical $1920\times1080$ displays) where the aggregate bounding box $(X, Y, W, H, C)$ remains mathematically identical.
  - **Why Global Identity is Sufficient for Phase 2B**:
    In Phase 2B, SendInput absolute normalized coordinates ($0..65535$) map across the *global* virtual desktop bounding box. Even if internal monitor display indices swap, the continuous global physical pixel coordinates $(x_{\text{phys}}, y_{\text{phys}})$ map identically relative to $(x_{\text{orig}}, y_{\text{orig}})$. Therefore, full per-monitor GUID enumeration (`EnumDisplayMonitors`) is not required for Phase 2B global coordinate safety.

---

### Correction 4 — Single Native Dispatch Gateway
- **Prior Flaw**: Potential for ad-hoc or uninstrumented `user32.SendInput` calls in future helper modules.
- **Correction Applied**:
  - Enforced a mandatory architectural invariant: **NO code may invoke `user32.SendInput` directly except through one designated `NativeDispatchGateway`.**
  - Architectural Pipeline:
    ```text
    MovementRequest
          ↓
    Coordinate Validation (Bounds Check)
          ↓
    Coordinate Normalization (0..65535)
          ↓
    Fail-Closed ABI Gate Check (AbiGate.require_abi_valid)
          ↓
    Immediate Pre-Dispatch Topology Identity Check
          ↓
    Immediate Pre-Dispatch Cancellation Check (CP4)
          ↓
    NativeDispatchGateway
          ↓
    ActionCounter.sendinput_calls incremented
          ↓
    user32.SendInput(1, byref(INPUT), sizeof(INPUT))
          ↓
    Immediate NativeDispatchResult capture (N, M, LastError, timestamp)
    ```
  - **Invariants**:
    1. Every `SendInput` call increments `ActionCounter.sendinput_calls`.
    2. Failed dispatches ($M = 0$) are instrumented and counted.
    3. Successful dispatches ($M = 1$) are instrumented and counted.
    4. Zero alternate dispatch paths exist.

---

### Correction 5 — GetLastError Discipline & Epistemic Limits
- **Prior Flaw**: Potential ambiguity regarding how `GetLastError()` is interpreted on SendInput failures.
- **Correction Applied**:
  - If `SendInput` returns 0: capture `kernel32.GetLastError()` immediately into `NativeDispatchResult.win32_last_error`.
  - **Epistemic Invariant**:
    1. `GetLastError` is diagnostic telemetry only; it does **not** provide mathematical proof of root cause.
    2. `last_error == 0` when `SendInput` returns 0 must **never** be interpreted as successful dispatch.
    3. When `SendInput` returns 0, the dispatch is classified as `DISPATCH_ZERO` / `SENDINPUT_FAILED` regardless of `last_error`.

---

### Correction 6 — Final Implementation Contract

The future Phase 2B implementation must strictly adhere to the following 12 rules:

1. **Exact Allowed Windows APIs**: `GetSystemMetrics`, `SendInput`, `GetCursorPos`, `GetLastError`, `SetProcessDpiAwarenessContext`, `GetProcessDpiAwarenessContext`.
2. **Forbidden Pointer APIs**: `SetCursorPos`, `mouse_event`, window message posting (`WM_MOUSEMOVE`, `WM_LBUTTONDOWN`), `OpenInputDesktop`, `SetThreadDesktop`.
3. **Single Dispatch Gateway**: All SendInput calls routed through `NativeDispatchGateway`.
4. **Mandatory ActionCounter Instrumentation**: Every dispatch attempt increments `ActionCounter.sendinput_calls`.
5. **No Automatic Movement Retries**: Zero retry loops on dispatch zero or readback mismatch.
6. **Immediate Post-Dispatch Result Capture**: Capture $M$ and `GetLastError()` immediately.
7. **Cancellation Classification Rules**: `CANCELLED_BEFORE_DISPATCH` (0 packets sent) vs `CANCELLED_AFTER_DISPATCH` (packet accepted; no claim of movement prevention).
8. **Readback Evidence Boundaries**: `GetCursorPos()` at $T_5$ proves only the coordinate observed at $T_5$.
9. **$\pm 1$ Physical Pixel Destination Tolerance**: Asserted on post-dispatch readback.
10. **Topology Identity Limitations**: Global bounding box comparison; internal identical-box monitor swaps disclosed.
11. **No False UIPI Diagnosis**: Mismatches classified factually as `EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE` or `SENDINPUT_FAILED`.
12. **No Desktop Switching APIs**: Zero unauthorized desktop context switching.

---

## 3. Remaining Unavoidable OS & Hardware Limitations

1. **Asynchronous Kernel Ingestion**: `SendInput` queues packets into User32; `GetCursorPos` reads the resulting cursor position after kernel processing.
2. **Hardware Sensor Jitter**: Physical optical gaming mouse sensors may emit sub-millisecond displacement packets during automated cursor dispatch.
3. **Mid-Dispatch GPU Mode Changes**: Hardware resolution shifts during the sub-microsecond pre-dispatch window cannot be intercepted in user-mode.
4. **UIPI Integrity Boundaries**: Elevated windows (e.g. Administrator console) may restrict post-dispatch window messaging if ORBIT is un-elevated.

---

## 4. Final Verdict

$$\boxed{\mathbf{\text{\Large 🟢 READY FOR PHASE 2B IMPLEMENTATION}}}$$

All 6 architectural corrections are formally incorporated into the specification. The repository contains ZERO Phase 2B implementation source code, ZERO pointer actions have been performed, and Prototypes A–D remain 100% frozen. Standing by for explicit user authorization to implement Phase 2B.
