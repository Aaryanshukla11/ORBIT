# ORBIT Milestone M1.2A — Pointer Capability Integration Audit
## Production Absolute Cursor Movement Integration

**Document Identifier:** `docs/M1_2A_POINTER_INTEGRATION_AUDIT.md`  
**Date:** September 6, 2026  
**Status:** APPROVED ARCHITECTURAL PRE-INTEGRATION AUDIT  
**Target:** Milestone M1.2A (Production Pointer Capability Integration — Absolute Cursor Movement Only)  
**Baseline Test Status:** 84/84 Pytest Passing | 15/15 Prototype D Passing | 71/71 Prototype E Passing  
**Frozen Prototype Status:** Exactly 0 Lines Modified relative to `ca87ef8`

---

## 1. Executive Summary

Milestone M1.2A transitions the validated cursor movement capability from **Prototype E (Safe Pointer Action Engine — Phase 2B)** into the actual production ORBIT runtime under `src/orbit/adapters/pointer/`.

### Strict Scope Boundary:
- **IN SCOPE (M1.2A)**:
  1. Win32 SendInput C ABI fail-closed runtime verification.
  2. Virtual desktop coordinate validation and 0..65535 absolute normalization.
  3. Structural display topology identity capture and pre-dispatch re-validation (T1 $\to$ T6).
  4. Cooperative pre-dispatch and post-dispatch cancellation integration with ORBIT's `CancellationToken`.
  5. Authoritative single-path native dispatch via `NativeDispatchGateway`.
  6. Post-dispatch `GetCursorPos` physical pixel readback and destination verification ($\pm 1\text{px}$ tolerance).
  7. Discrete SendInput evidence classification and diagnostic error capture.
  8. Observable action counter and health telemetry.
  9. Orchestrator and WebSocket command/event pipeline integration for typed cursor movement.
  10. Runtime backend selection (`POINTER_BACKEND=mock` vs `POINTER_BACKEND=prototype_e`) with fail-closed, no-silent-fallback semantics.

- **STRICT NON-GOALS (OUT OF SCOPE)**:
  - ❌ No clicks (left, right, middle, double).
  - ❌ No button DOWN or UP transitions.
  - ❌ No drag transactions.
  - ❌ No scrolling (wheel/hwheel).
  - ❌ No pointer state lockout transitions.
  - ❌ No modifications to frozen prototypes A–D.
  - ❌ No raw SendInput exposure to WebSocket clients or gateway.

---

## 2. Prototype E Dependency Classification Matrix

Every component within `prototypes/prototype_e_pointer/` is audited and classified according to the 5-tier rubric:
- **A. Safe to Reuse Directly** — Pure utility/logic safe to invoke inside the adapter boundary.
- **B. Requires Production Adapter Wrapper** — Core capability needing boundary translation, lifecycle management, or type adaptation.
- **C. Reimplemented Behind Production Boundary** — Functionality adapted to native ORBIT production conventions.
- **D. Out of Scope for M1.2A** — Button, click, drag, or prototype test scripts.
- **E. Unsafe for Production Integration** — Unverified or dangerous patterns.

| Component | Classification | Role in M1.2A | Architectural Handling & Rationale |
| :--- | :---: | :--- | :--- |
| `abi_validator.py` | **B** | Win32 AMD64 C ABI validation | `MOUSEINPUT`, `INPUT` structures, `validate_runtime_abi`, and `AbiGate` verified at adapter initialization. Fails closed if ABI mismatch occurs. |
| `dpi_awareness.py` | **A** | Per-Monitor v2 DPI context | `initialize_dpi_awareness()` ensures physical coordinate mapping across high-DPI displays. Safe inside adapter lifecycle. |
| `coordinate_mapper.py` | **B** | Topology & normalization math | Queries virtual desktop bounds, computes structural `VirtualDesktopTopologyIdentity`, and normalizes coordinates to 0..65535. |
| `native_gateway.py` | **B** | Single authoritative dispatch gateway | Enforces `AbiGate.require_abi_valid()`, increments `ActionCounter`, executes `user32.SendInput`, and captures `ctypes.get_last_error()`. |
| `pointer_controller.py` | **B** | 12-step movement pipeline | Implements safe sequence: T1 (topology) $\to$ T2 (bounds) $\to$ T3 (normalize) $\to$ T4 (cancel check) $\to$ T5 (ABI gate) $\to$ T6 (topology match) $\to$ T7 (pre-dispatch cancel) $\to$ T8 (dispatch) $\to$ T9 (record M) $\to$ T10 (post-dispatch cancel) $\to$ T11 (readback) $\to$ T12 (classify). |
| `telemetry.py` / `ActionCounter` | **B** | Observable action telemetry | Tracks total SendInput attempts, accepted packets, failed dispatches, topology rejections, and readback mismatches. |
| `cancellation.py` | **C** | Cooperative cancellation | Replaced with native production `orbit.runtime.cancellation.CancellationToken` to avoid duplicate token hierarchies. |
| `app_types.py` | **B / C** | Movement dataclasses & enums | Movement-specific result models (`MovementExecutionResult`, `MovementEvidence`, `TopologyFingerprint`) wrapped and mapped cleanly in `mapper.py`. Zero prototype dataclasses leak to ORBIT core. |
| `pointer_state_manager.py` | **D** | Button state machine & lockout | Out of scope for M1.2A. Belongs to Milestone M1.2B (Click & Button Transactions). |
| `button_controller.py` | **D** | Button DOWN/UP & Clicks | Out of scope for M1.2A. Clicks are strictly unauthorized in this milestone. |
| `target_validator.py` | **D** | Accessibility target verification | Advanced HWND/PID/element target validation is integrated with observation in Milestone M2. In M1.2A, coordinate bounds and display topology validation govern movement. |
| `phase1_validation.py` | **D** | Phase 1 test suite | Research acceptance artifact (frozen). |
| `phase2a_validation.py` | **D** | Phase 2A ABI test suite | Research acceptance artifact (frozen). |
| `phase2b_validation.py` | **D** | Phase 2B movement suite | Research acceptance artifact (frozen). |
| `phase2c_validation.py` | **D** | Phase 2C button suite | Research acceptance artifact (frozen). |

---

## 3. Production Pointer Boundary Architecture

Target structure under `src/orbit/adapters/pointer/`:

```
src/orbit/adapters/pointer/
├── __init__.py           # Package exports (ProductionPointerAdapter, MovementResult, etc.)
├── adapter.py            # ProductionPointerAdapter implementing PointerCapability & BaseCapabilityAdapter
├── movement.py           # Core 12-step MovementExecutor, NativeGateway, and CoordinateNormalizer
├── mapper.py             # Translates internal movement execution results into production contracts
├── safety.py             # Win32 AMD64 C ABI validation gate, topology fingerprinting, and invariants
└── health.py             # PointerHealthTracker and ActionCounter diagnostics
```

### Dependency Inversion & Isolation Diagram:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        ORBIT Production Core                           │
│        (OrbitOrchestrator, Gateway WebSocket, EventBus, Runtime)       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Depends strictly on Contracts
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             PointerCapability Protocol & ScreenPoint Contract          │
│                (src/orbit/contracts/capabilities.py)                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Implemented by
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       ProductionPointerAdapter                         │
│                    (src/orbit/adapters/pointer/)                       │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ movement.py         safety.py         mapper.py       health.py  │  │
│  │ (12-Step Pipeline) (ABI Gate & Topo) (Translation)   (Telemetry) │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Internal call to single gateway
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         NativeDispatchGateway                          │
│                      (user32.SendInput AMD64)                          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Epistemic Evidence & Non-Atomic Realism

The production pointer adapter enforces strict epistemic honesty across all 6 evidence levels:

1. `REQUEST_ACCEPTED_BY_ORBIT`: Command parameters parsed, session validated, and coordinate bounds verified.
2. `ABI_VALIDATED`: Win32 ctypes structure alignment (`MOUSEINPUT` 32 bytes, `INPUT` 40 bytes) confirmed.
3. `PRE_DISPATCH_VALIDATED`: Display topology fingerprint verified unchanged between T1 and T6.
4. `DISPATCH_ACCEPTED`: `user32.SendInput` accepted $M=1$ packet ($M=0$ classified as `DISPATCH_FAILED`).
5. `CURSOR_READBACK_OBSERVED`: Physical cursor position sampled via `user32.GetCursorPos` at T11.
6. `DESTINATION_VERIFIED`: Cursor position confirmed within $\pm 1\text{px}$ of requested target.

### Epistemic Invariants:
- `SendInput` returning 1 does **NOT** prove cursor movement occurred (e.g. UIPI or secure desktop block).
- Observing cursor at destination at T11 does **NOT** prove exclusive trajectory control (cooperative OS multitasking).
- Destination verification does **NOT** imply application-level task completion.
- Mismatch during readback is classified as `CURSOR_READBACK_MISMATCH` with diagnostic reason `EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE`.

---

## 5. Zero-Retry & Fail-Closed Invariants

- If `SendInput` returns 0: Return `DISPATCH_ZERO`. **Zero automatic retries.**
- If topology changes before dispatch: Return `REJECTED_TOPOLOGY_MUTATED`. **Zero automatic retries.**
- If cancellation is signalled before dispatch: Return `CANCELLED_BEFORE_DISPATCH`. **Zero SendInput dispatches.**
- If cancellation is signalled after dispatch: Return `CANCELLED_AFTER_DISPATCH` with truthful readback evidence.
- If ABI validation fails: Adapter enters `CapabilityLifecycleState.FAILED`. All subsequent actions rejected with `CapabilityUnavailableError`.

---

## 6. Audit Verdict

**VERDICT: APPROVED FOR M1.2A IMPLEMENTATION**  
All components, safety boundaries, coordinate contracts, and isolation layers are fully specified.
