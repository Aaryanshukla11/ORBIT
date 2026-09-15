# ORBIT PROTOTYPE E — PHASE 2 FORMAL ACCEPTANCE MATRIX (E25–E41)
## Pointer Interaction, Click Execution & State Sanitization (Updated C1–C6)

**Document Version:** 2.1.0  
**Target Phase:** Phase 2 (Safe Pointer Action & Click Execution Engine)  
**Host Platform:** Windows 11 Build 26200 AMD64 | Python 3.13.7  
**Frozen Baselines:** Prototypes A, B, C, D (Permanently Frozen)  

---

## 1. Acceptance Matrix Overview & Sub-Phase Mapping

The Phase 2 acceptance matrix defines **17 formal empirical verification tests (E25–E41)** staged across Sub-Phases 2A through 2E.

```
PHASE 2A: ABI & SendInput Foundation   ──► E25_ABI (Embedded in E25)
PHASE 2B: Absolute Cursor Movement     ──► E25, E26, E27
PHASE 2C: Single Button Transactions   ──► E28, E29, E31, E32, E33, E34
PHASE 2D: Controlled Click Execution   ──► E30, E35, E40
PHASE 2E: Integration & Matrix Closure ──► E36, E37, E38, E39, E41
```
*Note: Multi-stage Drag Operations (Level 4) are explicitly excluded from the initial Phase 2 sequence.*

---

## 2. Formal Acceptance Tests (E25–E41)

| Test ID | Capability Tested | Preconditions & Target | Exact Action Executed | Observable Ground Truth | Expected Verdict | Reality Classification |
| :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| **E25** | Safe Absolute Cursor Movement & ABI Gate | Live desktop window; cursor at $(x_1, y_1)$ | Runtime ABI check $\to$ Dispatch `MOVE` to $(x_2, y_2)$ | ABI verified valid; `GetCursorPos()` reads $(x_2, y_2) \pm 1\text{px}$ | **PASS** | `LIVE_OS_VALIDATED` |
| **E26** | Cursor Position Post-Dispatch Readback | Live desktop target | Move to 5 distinct grid coordinates | All 5 readbacks match target $\pm 1\text{px}$; status `MOVE_VERIFIED` | **PASS** | `LIVE_OS_VALIDATED` |
| **E27** | Coordinate Boundary Movement | Virtual desktop bounds | Move to $(x_{\text{orig}}, y_{\text{orig}})$ and $(W_v-1, H_v-1)$ | Coordinates reach exact virtual desktop corners $\pm 1\text{px}$ | **PASS** | `LIVE_OS_VALIDATED` |
| **E28** | Single Synthetic Button Down | Target window ready | Dispatch `MOUSEEVENTF_LEFTDOWN` | `PointerStateManager` records `_orbit_left_down = True` | **PASS** | `LIVE_OS_VALIDATED` |
| **E29** | Single Synthetic Button Release | Button currently held down | Dispatch `MOUSEEVENTF_LEFTUP` | `PointerStateManager` records `_orbit_left_down = False` | **PASS** | `LIVE_OS_VALIDATED` |
| **E30** | Controlled Click Callback Verification | Controlled Tkinter button ($0$ clicks) | Dispatch Left Click transaction | Widget callback fires; atomic counter: $0 \to 1$ | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |
| **E31** | Partial Transaction Recovery | Injected $N=3$ click packets | Simulate User32 partial return $M=2$ | Partial return detected; emergency UP dispatched immediately | **PASS** | `INTERNAL_LOGIC_VALIDATED` |
| **E32** | Synthetic Button Sanitization | ORBIT button-down active | Invoke `sanitize_orbit_buttons()` | `MOUSEEVENTF_LEFTUP` emitted; ORBIT bitmask cleared | **PASS** | `LIVE_OS_VALIDATED` |
| **E33** | Failed Sanitization Hard Lockout | Sanitization UP fails ($M=0$) | Simulate driver failure on sanitize | Enters `UNRESOLVED_LOCKED`; blocks future actions | **PASS** | `INTERNAL_LOGIC_VALIDATED` |
| **E34** | Cancellation Before Dispatch | Target validated; token cancelled | Attempt click dispatch | 0 SendInput packets emitted; status `CANCELLED_BEFORE_DISPATCH` | **PASS** | `LIVE_OS_VALIDATED` |
| **E35** | Cancellation During Multi-Stage Click | Button down; hold in progress | Token cancelled during click sleep | Trajectory halts; synthetic UP emitted; `CANCELLED_DURING_HOLD` | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |
| **E36** | Human Takeover Preemption | Long trajectory in progress | Human moves mouse during trajectory | Hook detects physical delta; motion halts in $< 1\text{ms}$ | **PASS** | `PHYSICALLY_VALIDATED` |
| **E37** | Foreground TOCTOU Rejection | Target window unfocused before gate | Dispatch click requiring foreground | Rejected at pre-dispatch gate with `FOREGROUND_LOST` | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |
| **E38** | Stale Snapshot Rejection | Snapshot age exceeds TTL (500ms) | Request click after delay | Rejected before dispatch with `SNAPSHOT_TTL_EXPIRED` | **PASS** | `LIVE_OS_VALIDATED` |
| **E39** | Display Topology Invalidation | Screen bounds mutate during session | Request click against old geometry | Topology fingerprint mismatch; `TOPOLOGY_MUTATED` | **PASS** | `SYNTHETICALLY_SIMULATED` |
| **E40** | Target Effect Absent Classification | Dispatch click to disabled widget | SendInput accepted (L4); no callback | Status classified as `TARGET_EFFECT_NOT_OBSERVED` | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |
| **E41** | Full Observe-Validate-Click Loop | Controlled Multi-Widget Target | Observe $\to$ Adapt $\to$ Validate $\to$ Click | Target state mutated and verified empirically via callback | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |

---

## 3. Test Invariants & Pass/Fail Criteria

### Invariant 1: Layer 4 vs Layer 7 Separation
A test passes **only** if:
1. `ExecutionResult.status == DISPATCH_SUCCESS` (Layer 4)
2. `TargetObservedState == EXPECTED_MUTATION` (Layer 7)
If Layer 4 succeeds but Layer 7 does not mutate, the result MUST be recorded as `TARGET_EFFECT_NOT_OBSERVED` or `DISPATCHED_BUT_UNVERIFIED`.

### Invariant 2: Zero Post-Cancellation Injection
Once a `CancellationToken` is observed as cancelled, exactly **0** subsequent `SendInput` pointer movement or button-down packets may be dispatched.
