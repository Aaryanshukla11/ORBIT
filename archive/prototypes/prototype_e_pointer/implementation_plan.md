# ORBIT PROTOTYPE E — IMPLEMENTATION PLAN & ARCHITECTURE SPECIFICATION
## Safe Pointer Action & Click Execution Engine (Version 2.3.0)

**Document Version:** 2.3.0 (Phase 2B Movement Architecture Specification — Final Correction Pass)  
**Phase:** Phase 2B (Absolute Cursor Movement Only)  
**Target Environment:** Windows 11 Build 26200+ (AMD64 64-bit), Python 3.13.7  
**Isolated Path:** `prototypes/prototype_e_pointer/`  
**Frozen Baselines:**  
- Prototype A (Desktop Workspace & Docking) — FROZEN  
- Prototype B v1.1 (Human Takeover & Mouse Control Safety) — FROZEN  
- Prototype C v1.1 (Reliable Keyboard Interaction & Unicode Engine) — FROZEN  
- Prototype D v1.3.1 (Screen Observation & Evidence Fusion Engine) — FROZEN  
- Prototype E Phase 1 (Core Safety Contracts & Coordinate Engine) — VALIDATED & FROZEN  
- Prototype E Phase 2A (Win32 SendInput C ABI Validation) — VALIDATED & FROZEN  

---

## 1. Executive Architecture & Core Invariants

ORBIT Prototype E investigates and empirically validates whether ORBIT can perform **reliable, coordinate-aware, deterministic, and interruptible Windows pointer actions** against desktop UI elements discovered by observation, while strictly guaranteeing the paramount safety invariant:

$$\boxed{\mathbf{HUMAN\ CONTROL\ ALWAYS\ OVERRIDES\ ORBIT\ CONTROL}}$$

and the deterministic action loop:

$$\boxed{\mathbf{OBSERVE} \longrightarrow \mathbf{VALIDATE\ TARGET\ IDENTITY} \longrightarrow \mathbf{EXECUTE\ POINTER\ ACTION} \longrightarrow \mathbf{CONTINUOUSLY\ CHECK\ CANCELLATION}}$$

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           PROTOTYPE E ARCHITECTURAL CONTEXT & BOUNDARIES                        │
├───────────────────────────────┬─────────────────────────────────┬───────────────────────────────┤
│ FROZEN OBSERVATION (PROTO D)  │ PROTOTYPE E (POINTER ENGINE)    │ FROZEN SAFETY/HOOKS (PROTO B) │
├───────────────────────────────┼─────────────────────────────────┼───────────────────────────────┤
│ - Desktop ObservationSnapshot │ 1. Standalone Target Contract   │ - WH_MOUSE_LL Low-Level Hook  │
│ - Monotonic DesktopGeneration │ 2. Structural Topology Identity │ - Real-time Velocity Monitor  │
│ - Multi-Source Evidence Fusion│ 3. Runtime ABI Verification Gate│ - Instant Takeover Signal     │
│ - Spatial Bounds & Occlusion  │ 4. ORBIT Button Ownership Model │ - Emergency Stop Pipeline     │
│ - Snapshot TTL & Invalidation │ 5. Absolute Movement Engine     │ - Human Input Preemption      │
│                               │ 6. 3-Phase Target Verification  │                               │
│                               │ 7. 7-Layer Evidence Accounting  │                               │
└───────────────────────────────┴─────────────────────────────────┴───────────────────────────────┘
```

### Core Invariants Defined:
1. $\mathbf{POINTER\ API\ SUCCESS\ \ne\ TARGET\ TASK\ SUCCESS}$: A successful Win32 `SendInput` call only proves OS message queue ingestion (Layer 4); UI activation requires target-side observable verification (Layer 7).
2. $\mathbf{CURSOR\ ARRIVAL\ MUST\ BE\ EMPIRICALLY\ OBSERVED}$: `SendInput` return value $1$ (`DISPATCH_ACCEPTED`) does not prove cursor arrival; cursor position must be verified by `user32.GetCursorPos()` within $\pm 1\text{px}$ tolerance (`MOVEMENT_VERIFIED`).
3. $\mathbf{ZERO\ AUTOMATIC\ MOVEMENT\ RETRIES}$: If movement fails or readback differs, the controller reports the discrepancy and never automatically re-injects stale coordinates.
4. $\mathbf{STALE\ OR\ INVALID\ TARGET\ \implies\ NO\ POINTER\ ACTION}$: If desktop generation, window identity, foreground state, or coordinate bounds mutate between observation and dispatch, execution is rejected.
5. $\mathbf{FAIL-CLOSED\ RUNTIME\ ABI\ GATE}$: The controller validates ctypes structure memory sizes and offsets at runtime and aborts before dispatch if ABI expectations are not met.
6. $\mathbf{NO\ MAGIC\ NUMBERS\ (C1)}$: All Win32 flags are composed dynamically via named constants `MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK`.
7. $\mathbf{STRUCTURAL\ TOPOLOGY\ IDENTITY\ (C2)}$: Display comparison checks `VirtualDesktopTopologyIdentity` (origin, dimensions, monitor count) and ignores observation timestamp differences.
8. $\mathbf{EPISTEMIC\ INTEGRITY\ (C3)}$: Readback mismatches are classified factually as `CURSOR_READBACK_MISMATCH` with `EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE`, without claiming human takeover without independent hook verification.
9. $\mathbf{SINGLE-PACKET\ HONESTY\ (C4)}$: For $N=1$, dispatch outcomes are strictly $M=0$ (`DISPATCH_ZERO`) or $M=1$ (`DISPATCH_ACCEPTED`).
10. $\mathbf{NON-ATOMIC\ READBACK\ DISCLOSURE\ (C5)}$: The sequence $T_1 \to T_5$ is non-atomic; `MOVEMENT_VERIFIED` proves destination arrival at $T_5$, not exclusive continuous trajectory control.

---

## 2. Repository Baseline & Frozen Checkpoint

```text
Baseline Commit : ca87ef8 (docs(prototype-d): final independent closure audit)
Git Diff Status : 0 lines modified across Prototypes A, B, C, and D
Isolation Path  : prototypes/prototype_e_pointer/
```

- **Prototype A** (`prototypes/prototype_a_workspace/`): Frozen. 0 modifications.
- **Prototype B** (`prototypes/prototype_b_human_takeover/`): Frozen. 0 modifications.
- **Prototype C** (`prototypes/prototype_c_keyboard/`): Frozen. 0 modifications.
- **Prototype D** (`prototypes/prototype_d_observation/`): Frozen. 0 modifications.
- **Prototype E Phase 1 & 2A**: Implemented, tested, and validated (24/24 total tests passing).

---

## 3. Phase 2 Staged Implementation Sequence (Phase 2A → 2E)

```
┌────────────────────────────────────────────────────────────────────────┐
│             PHASE 2 STAGED IMPLEMENTATION & VALIDATION SEQUENCE        │
├────────────────────────────────────────────────────────────────────────┤
│ PHASE 2A: ABI Validation & SendInput Foundation [COMPLETE]             │
│   - ctypes sizeof(INPUT)==40, sizeof(MOUSEINPUT)==32, offset checks    │
│   - Fail-closed AbiGate singleton (10/10 tests passing)                │
├────────────────────────────────────────────────────────────────────────┤
│ PHASE 2B: Absolute Cursor Movement Only [CURRENT STAGE]                │
│   - Named flag composition (MOUSEEVENTF_MOVE|ABSOLUTE|VIRTUALDESK)     │
│   - Structural topology identity comparison                            │
│   - Post-dispatch GetCursorPos verification (±1px tolerance)           │
│   - Fact-based diagnostic classification without causality overclaim   │
│   - Zero button downs, zero button ups, zero clicks                    │
├────────────────────────────────────────────────────────────────────────┤
│ PHASE 2C: Single Button State Transactions & Lockout Machine           │
│   - Isolated synthetic DOWN, isolated synthetic UP                     │
│   - PointerStateManager ownership tracking                             │
│   - Emergency UP, UNRESOLVED_LOCKED lockout                            │
├────────────────────────────────────────────────────────────────────────┤
│ PHASE 2D: Controlled Click Transactions                                │
│   - Compound [MOVE -> Gate -> DOWN -> Dwell -> Gate -> UP]             │
│   - Controlled multi-widget Tkinter target callback verification       │
├────────────────────────────────────────────────────────────────────────┤
│ PHASE 2E: Full Integration & Multi-Tier Validation                     │
│   - Prototype D snapshot adapter + live target validator integration   │
│   - Topology identity verification + cancellation preemption gates     │
│   - Formal acceptance matrix execution                                 │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Phase 2B Data Contracts & Module Layout

```python
# 1. Named Win32 Flags (Correction C1)
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000
FLAGS_ABSOLUTE_MOVE = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK

# 2. Structural Topology Identity (Correction C2)
@dataclass(frozen=True)
class VirtualDesktopTopologyIdentity:
    origin_x: int
    origin_y: int
    width: int
    height: int
    monitor_count: int

    def matches(self, other: "VirtualDesktopTopologyIdentity") -> bool:
        return (
            self.origin_x == other.origin_x
            and self.origin_y == other.origin_y
            and self.width == other.width
            and self.height == other.height
            and self.monitor_count == other.monitor_count
        )

@dataclass(frozen=True)
class VirtualDesktopTopologyObservation:
    identity: VirtualDesktopTopologyIdentity
    observed_at_ns: int

# 3. Status & Diagnostic Reasons (Correction C3, C4)
class MovementExecutionStatus(str, Enum):
    NOT_DISPATCHED = "NOT_DISPATCHED"
    DISPATCH_ACCEPTED = "DISPATCH_ACCEPTED"
    MOVEMENT_VERIFIED = "MOVEMENT_VERIFIED"
    DISPATCHED_BUT_MOVEMENT_UNVERIFIED = "DISPATCHED_BUT_MOVEMENT_UNVERIFIED"
    CURSOR_READBACK_MISMATCH = "CURSOR_READBACK_MISMATCH"
    DISPATCH_ZERO = "DISPATCH_ZERO"
    DISPATCH_PARTIAL_NOT_APPLICABLE = "DISPATCH_PARTIAL_NOT_APPLICABLE"
    CANCELLED_BEFORE_DISPATCH = "CANCELLED_BEFORE_DISPATCH"
    CANCELLED_AFTER_DISPATCH = "CANCELLED_AFTER_DISPATCH"
    REJECTED_OUT_OF_BOUNDS = "REJECTED_OUT_OF_BOUNDS"
    REJECTED_TOPOLOGY_MUTATED = "REJECTED_TOPOLOGY_MUTATED"
    ABI_INVALID = "ABI_INVALID"
    REJECTED_PRECONDITION = "REJECTED_PRECONDITION"

class MovementDiagnosticReason(str, Enum):
    NONE = "NONE"
    EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE = "EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE"
    TOPOLOGY_CHANGE_POSSIBLE = "TOPOLOGY_CHANGE_POSSIBLE"
    EXTERNAL_INPUT_POSSIBLE = "EXTERNAL_INPUT_POSSIBLE"
    QUANTIZATION_VARIANCE = "QUANTIZATION_VARIANCE"
    SENDINPUT_FAILED = "SENDINPUT_FAILED"
    TOPOLOGY_MUTATED = "TOPOLOGY_MUTATED"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"
    ABI_MISMATCH = "ABI_MISMATCH"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"

# 4. Movement Request & Result Models
@dataclass(frozen=True)
class MovementRequest:
    target_x: int
    target_y: int
    tolerance_px: int = 1
    cancellation_token: Optional[Any] = None
    timeout_ms: float = 100.0

@dataclass(frozen=True)
class MovementExecutionResult:
    status: MovementExecutionStatus
    diagnostic_reason: MovementDiagnosticReason
    requested_pos: Tuple[int, int]
    observed_pos: Optional[Tuple[int, int]]
    delta_px: Optional[Tuple[int, int]]
    accepted_packets: int
    duration_us: float
    error_message: Optional[str] = None
```

---

## 5. Movement Verification Evidence Layers (L1–L6)

```text
L1: Movement Request Created    ──► MovementRequest instantiated in memory
L2: Preconditions Validated     ──► AbiGate valid, coordinates in bounds, topology identity matches
L3: Coordinates Normalized      ──► NormalizedCoordinate (0..65535) computed
L4: SendInput Accepted Packet   ──► user32.SendInput returns 1 (DISPATCH_ACCEPTED)
L5: Cursor Position Observed    ──► user32.GetCursorPos() reads back (x_obs, y_obs)
L6: Destination Verified        ──► |x_obs - x_req| <= 1px and |y_obs - y_req| <= 1px (MOVEMENT_VERIFIED)
```

---

## 6. Critical Pre-Implementation Stop Condition

$$\boxed{\mathbf{DO\ NOT\ IMPLEMENT\ PHASE\ 2B\ UNTIL\ AUTHORIZED}}$$

All architectural corrections C1–C5 are integrated. No Phase 2B pointer injection code has been written. Standing by for explicit authorization.
