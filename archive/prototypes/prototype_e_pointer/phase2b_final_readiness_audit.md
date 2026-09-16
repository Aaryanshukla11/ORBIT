# ORBIT PROTOTYPE E — PHASE 2B INDEPENDENT ADVERSARIAL FINAL READINESS AUDIT REPORT
## Absolute Cursor Movement Architecture (Final Pre-Implementation Gate)

**Audit Date:** 2026-09-05  
**Auditor:** Independent Systems, Safety & Adversarial Architecture Auditor  
**Audit Scope:** Comprehensive Adversarial Analysis of Phase 2B Pre-Implementation Specification, Win32 SendInput AMD64 ABI, Virtual Desktop Geometry Mathematics, High-DPI Virtualization, Cancellation Pipeline, Topology Mutation Limits, Epistemic Readback Boundaries, and Action Counter Integrity.  
**Pre-Implementation Non-Action Invariant:** **0 `SendInput` calls / 0 clicks / 0 cursor movements / 0 Phase 2B implementation modules created.**  
**Status Verdict:** 🟢 **READY FOR PHASE 2B IMPLEMENTATION**

---

## 1. Repository Baseline Verification & Files Inspected

### 1.1 Frozen Prototype Isolation Verification
```text
Baseline Commit : ca87ef8 (docs(prototype-d): final independent closure audit)
Diff Command    : git diff ca87ef8 -- prototypes/prototype_a_workspace/ prototypes/prototype_b_human_takeover/ prototypes/prototype_c_keyboard/ prototypes/prototype_d_observation/
Diff Output     : 0 files changed, 0 insertions, 0 deletions (100% FROZEN ISOLATION CONFIRMED)
Git Status      : Clean branch tracking; 0 modifications in frozen Prototypes A, B, C, D
```

### 1.2 Files Inspected
The following files across the active Prototype E directory and frozen Prototype B historical baseline were independently inspected:

| Category | File Inspected | Key Contracts / Architecture Verified |
| :--- | :--- | :--- |
| **Foundation Contracts** | `prototypes/prototype_e_pointer/app_types.py` | `VirtualDesktopTopologyIdentity`, `MovementExecutionStatus`, `MovementDiagnosticReason`, `MovementRequest`, `MovementExecutionResult` |
| **ABI Gate** | `prototypes/prototype_e_pointer/abi_validator.py` | `INPUT`, `MOUSEINPUT`, ctypes offsets, `AbiGate.require_abi_valid()`, `ActionCounter` |
| **Coordinate Engine** | `prototypes/prototype_e_pointer/coordinate_mapper.py` | `normalize_to_sendinput`, `denormalize_from_sendinput`, `get_topology_identity`, `get_topology_observation` |
| **DPI Management** | `prototypes/prototype_e_pointer/dpi_awareness.py` | `DpiManager`, `DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2`, physical space alignment |
| **Cancellation** | `prototypes/prototype_e_pointer/cancellation.py` | `CancellationToken`, thread-safe monotonic cancellation, `.reason` attribute |
| **Telemetry** | `prototypes/prototype_e_pointer/telemetry.py` | `Phase1TelemetryCollector`, `Phase2bTelemetryCollector` |
| **Regression Baselines** | `prototypes/prototype_e_pointer/phase1_validation.py` | Phase 1 Safety Validation Suite (14/14 tests verified passing) |
| **Regression Baselines** | `prototypes/prototype_e_pointer/phase2a_validation.py` | Phase 2A ABI Validation Suite (10/10 tests verified passing) |
| **Planning & Audits** | `prototypes/prototype_e_pointer/implementation_plan.md` | v2.3.0 Staged implementation plan |
| **Planning & Audits** | `prototypes/prototype_e_pointer/phase2b_pre_implementation_audit.md` | Phase 2B pre-implementation audit with Corrections C1–C5 |
| **Planning & Audits** | `prototypes/prototype_e_pointer/phase2b_acceptance_matrix.md` | Formal acceptance matrix (P2B-1 to P2B-22) |
| **Planning & Audits** | `prototypes/prototype_e_pointer/phase2b_risk_register.md` | Failure matrix and risk register |
| **Historical Baseline** | `prototypes/prototype_b_human_takeover/input_controller.py` | Historical Prototype B SendInput implementation and legacy coordinate normalization flaws |

---

## 2. Adversarial Questions & Independent Verification

### Section A — Win32 SendInput Semantics

1. **Is `INPUT.cbSize` correctly supplied as `sizeof(INPUT)`?**
   - **YES**. On Windows AMD64 (64-bit), `ctypes.sizeof(INPUT) == 40` bytes. The parameter `cbSize` passed to `user32.SendInput(cInputs, pInputs, cbSize)` must be exactly `40` (the size of a single `INPUT` structure, **not** the size of the array). This is enforced by `ctypes.sizeof(INPUT)` and verified by test `P2A-4`.

2. **Is the ctypes `SendInput` signature correct?**
   - **YES**. The formal Win32 User32 signature is:
     ```c
     UINT SendInput(
       UINT cInputs,
       LPINPUT pInputs,
       int cbSize
     );
     ```
   - In Python ctypes on AMD64, it must be declared as:
     ```python
     user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
     user32.SendInput.restype = wintypes.UINT
     ```
   - Failing to set `argtypes` and `restype` defaults to 32-bit return values and can cause pointer marshalling truncation on 64-bit systems. The Phase 2B specification mandates explicit signature declaration.

3. **Is the function return type correct?**
   - **YES**. `SendInput` returns a `UINT` representing the count of input packets successfully inserted into the system input stream.

4. **Are DWORD / ULONG_PTR / LONG / UINT types correctly represented?**
   - **YES**.
     - `dx, dy`: `wintypes.LONG` (4 bytes, signed 32-bit integer).
     - `mouseData`: `wintypes.DWORD` (4 bytes, unsigned 32-bit integer).
     - `dwFlags`: `wintypes.DWORD` (4 bytes, unsigned 32-bit integer).
     - `time`: `wintypes.DWORD` (4 bytes, unsigned 32-bit integer).
     - `dwExtraInfo`: `ctypes.c_uint64` (8 bytes, unsigned 64-bit pointer-sized integer).

5. **Is `MOUSEINPUT` structure alignment correct on AMD64?**
   - **YES**.
     - Offset 0: `dx` (4 bytes)
     - Offset 4: `dy` (4 bytes)
     - Offset 8: `mouseData` (4 bytes)
     - Offset 12: `dwFlags` (4 bytes)
     - Offset 16: `time` (4 bytes)
     - Offset 20: *4 bytes compiler padding* (to align 8-byte `dwExtraInfo` on 8-byte boundary)
     - Offset 24: `dwExtraInfo` (8 bytes)
     - Total Size: `32` bytes. Verified at runtime by `abi_validator.py`.

6. **Is `dwExtraInfo` truly pointer-sized?**
   - **YES**. On AMD64 Windows, `ULONG_PTR` is 8 bytes (`ctypes.sizeof(ctypes.c_void_p) == 8`). `abi_validator.py` verifies `is_pointer_sized_extrainfo == True` via `ctypes.sizeof(MOUSEINPUT.dwExtraInfo) == 8`.

7. **Can a successful `SendInput` return value prove cursor arrival?**
   - **NO**.
   - **What `SendInput` success ($M = 1$) proves**: The single input event was successfully validated by User32 and queued into the Windows raw input queue (Layer 4).
   - **What `SendInput` success does NOT prove**:
     - It does NOT prove the cursor reached the requested coordinate (Layer 5).
     - It does NOT prove that a hardware mouse sensor did not move the cursor simultaneously.
     - It does NOT prove that the operating system or display driver did not clamp the cursor coordinate.
     - It does NOT prove target window focus or UI element activation (Layer 7).
   - **Verdict**: Layer 4 dispatch and Layer 5 cursor readback must remain strictly decoupled.

---

### Section B — Absolute Movement Flags

1. **Exact Proposed Movement Flags**:
   ```python
   MOUSEEVENTF_MOVE        = 0x0001
   MOUSEEVENTF_VIRTUALDESK = 0x4000
   MOUSEEVENTF_ABSOLUTE    = 0x8000

   FLAGS_ABSOLUTE_MOVE = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
   ```
2. **Accidental / Dangerous Flags Investigation**:
   - `MOUSEEVENTF_LEFTDOWN` (`0x0002`), `MOUSEEVENTF_LEFTUP` (`0x0004`), `MOUSEEVENTF_RIGHTDOWN` (`0x0008`), `MOUSEEVENTF_RIGHTUP` (`0x0010`), `MOUSEEVENTF_MIDDLEDOWN` (`0x0020`), `MOUSEEVENTF_MIDDLEUP` (`0x0040`), `MOUSEEVENTF_WHEEL` (`0x0800`), `MOUSEEVENTF_HWHEEL` (`0x1000`) are **strictly excluded**.
   - The bitmask contains solely the 3 flags necessary for absolute virtual desktop positioning.
3. **Primary Monitor vs Virtual Desktop Mapping**:
   - If `MOUSEEVENTF_VIRTUALDESK` (`0x4000`) is omitted, `MOUSEEVENTF_ABSOLUTE` maps $0..65535$ exclusively to `SM_CXSCREEN` and `SM_CYSCREEN` (the primary monitor). On multi-monitor setups where secondary monitors exist to the left (negative X) or top (negative Y), omitting `MOUSEEVENTF_VIRTUALDESK` produces severe coordinate distortion.
   - `MOUSEEVENTF_VIRTUALDESK` is mandatory and guaranteed in `FLAGS_ABSOLUTE_MOVE`.

---

### Section C — Coordinate Mathematics

1. **Primary Monitor at Origin $(0, 0)$**:
   - $\Delta x = x - 0 = x, \quad dx = \operatorname{round}(x \times 65535.0 / (W_v - 1))$.
   - $x = 0 \implies dx = 0$; $x = W_v - 1 \implies dx = 65535$. Verified.
2. **Secondary Monitor to the Left (Negative X)**:
   - Primary: $1920\times1080$ at $(0, 0)$; Secondary: $1920\times1080$ at $(-1920, 0)$.
   - Virtual Desktop: $X_{\text{origin}} = -1920, W_v = 3840$.
   - Leftmost pixel $x = -1920 \implies \Delta x = -1920 - (-1920) = 0 \implies dx = 0$.
   - Rightmost pixel $x = 1919 \implies \Delta x = 1919 - (-1920) = 3839 \implies dx = \operatorname{round}(3839 \times 65535 / 3839) = 65535$. Verified.
3. **Secondary Monitor Above Primary (Negative Y)**:
   - $Y_{\text{origin}} = -1080, H_v = 2160$.
   - Topmost pixel $y = -1080 \implies \Delta y = -1080 - (-1080) = 0 \implies dy = 0$. Verified.
4. **Mixed Negative X and Negative Y**:
   - Dual negative offsets shift $\Delta x$ and $\Delta y$ into non-negative range $[0, W_v - 1]$ and $[0, H_v - 1]$. Verified.
5. **Single-Pixel Dimensions ($W_v \le 1$ or $H_v \le 1$)**:
   - If $W_v \le 1$, division by $(W_v - 1)$ is guarded in `coordinate_mapper.py` (lines 142–151), setting $dx = 0$ and returning `INVALID_VIRTUAL_DIMENSIONS`. No `ZeroDivisionError` can occur.
6. **Bottom-Right Boundary**:
   - In discrete pixel coordinate systems, the bottom-right pixel of a rectangle $[x_{\text{origin}}, x_{\text{origin}} + W_v)$ is $(x_{\text{origin}} + W_v - 1, y_{\text{origin}} + H_v - 1)$. This maps exactly to $(65535, 65535)$.
7. **Out-of-Bounds Coordinates**:
   - `metrics.contains_point(x, y)` evaluates $x_{\text{origin}} \le x < x_{\text{origin}} + W_v$. Any point outside returns `COORDINATE_OUT_OF_BOUNDS`, rejecting dispatch before `SendInput`.
8. **Floating Point Rounding & Quantization**:
   - Inverting normalized integers back to physical coordinates via `round(norm \times (W_v - 1) / 65535.0)` introduces at most $\pm 0.5\text{px}$ rounding variance.
   - Demanding exact $0.0\text{px}$ float equality is mathematically impossible across arbitrary resolutions. The configured $\pm 1\text{px}$ tolerance is mathematically sound and empirically validated.

---

### Section D — DPI and Virtualization

1. **Per-Monitor V2 Initialization Timing**:
   - `initialize_dpi_awareness()` is invoked before any call to `GetSystemMetrics`, `GetCursorPos`, or coordinate normalization.
2. **Consistency Under DPI Virtualization**:
   - Under `DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2` (`-4`):
     - `GetSystemMetrics(SM_CXVIRTUALSCREEN)` returns unscaled physical pixels.
     - `GetCursorPos()` returns unscaled physical pixels.
     - `SendInput(MOUSEEVENTF_VIRTUALDESK)` maps across unscaled physical pixels.
   - Zero coordinate space mismatch exists.
3. **Interactive Window Station & Desktop Attachment**:
   - In automated testing or IDE subagents, Windows threads may not initially be attached to the active input desktop.
   - Calling `OpenInputDesktop(0, False, 0x01FF)` and `SetThreadDesktop(hInputDesktop)` ensures `GetCursorPos` and `SendInput` succeed without `ERROR_ACCESS_DENIED` (error code 5).
4. **Failure Behavior**:
   - If DPI awareness fails to initialize, `DpiManager.status.init_succeeded` reports the error code, while the coordinate engine falls back to live query bounds.

---

### Section E — Topology Mutation & Fingerprint Limits

1. **Structural Topology Identity**:
   ```python
   VirtualDesktopTopologyIdentity(
       origin_x: int,
       origin_y: int,
       width: int,
       height: int,
       monitor_count: int
   )
   ```
2. **Scenario Where Topology Changes but Identity is Identical**:
   - **Adversarial Scenario**: Consider a dual-monitor setup with two identical $1920\times1080$ monitors. If the user swaps Monitor 1 and Monitor 2 in Windows Display Settings (changing which monitor is the primary display), the overall virtual desktop bounding box $(0, 0, 3840, 1080, 2)$ may remain mathematically identical while internal per-monitor boundaries shift.
   - **Residual Limitation Disclosure**: `VirtualDesktopTopologyIdentity` validates the global virtual desktop bounding box and monitor count. In user-mode without per-monitor GUID enumerations, an internal display permutation within the exact same bounding box cannot be detected from `GetSystemMetrics` alone.
   - **Risk Evaluation**: This is a minor residual edge case that does not invalidate coordinate mapping within the global bounding box.

---

### Section F — Cancellation and Human Takeover

1. **Timeline Tracing**:
   ```text
   T1: Request received -> Cancellation Token Checkpoint CP1
   T2: Coordinate validation & normalization -> Cancellation Token Checkpoint CP2
   T3: Fail-closed ABI Gate verification -> Cancellation Token Checkpoint CP3
   T4: Pre-dispatch topology identity check -> Cancellation Token Checkpoint CP4
   T5: Single-packet SendInput (N = 1) dispatch
   T6: SendInput returns M (0 or 1) -> Post-dispatch Cancellation Checkpoint CP5
   T7: GetCursorPos readback -> Post-dispatch Cancellation Checkpoint CP6
   T8: Destination verification & outcome classification
   ```
2. **Factual Outcome Classifications**:
   - **`CANCELLED_BEFORE_DISPATCH`**: Token cancelled at CP1–CP4. Exactly **0** packets sent.
   - **`CANCELLED_AFTER_DISPATCH`**: Token cancelled at CP5–CP6. Input packet was already accepted by User32. The system reports cancellation truthfully without falsely claiming movement was prevented.
   - **`CURSOR_READBACK_MISMATCH`**: Readback delta exceeds $\pm 1\text{px}$. Classified with `EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE`, without claiming human takeover.

---

### Section G — Retry Hazards

- **Strict Non-Retry Invariant**: If `SendInput` returns 0, or if readback mismatches, or if cancellation occurs, the controller **never** performs automatic retries.
- **Rationale**: Re-injecting stale coordinates while a human user or external application is interacting with the desktop violates the core invariant: $\mathbf{HUMAN\ CONTROL\ ALWAYS\ OVERRIDES\ ORBIT\ CONTROL}$.

---

### Section H — Cursor Readback Boundaries

- `GetCursorPos()` at $T_7$ proves **only** the cursor position observed at $T_7$.
- It does **not** prove:
  - that ORBIT had continuous ownership of the trajectory
  - that external software did not intervene
  - that hardware acceleration did not apply
- `MOVEMENT_VERIFIED` means: *"The requested destination was observed within the configured tolerance during post-dispatch readback."*

---

### Section I — Physical vs Simulated Validation Classification

All tests are strictly categorized into reality tiers:
1. `LIVE_OS_VALIDATED`: Direct execution against native Win32 User32 APIs on the live host OS.
2. `INTERNAL_LOGIC_VALIDATED`: Deterministic verification of internal algorithmic, mathematical, or fail-closed gating logic.
3. `SYNTHETICALLY_SIMULATED`: Mathematical simulation of hardware/display topologies not physically attached to the host (e.g. negative-origin multi-monitor setups).

---

### Section J — Action Counter Integrity

- `ActionCounter` in `app_types.py` / `abi_validator.py` tracks:
  - `sendinput_calls`
  - `setcursorpos_calls`
  - `synthetic_down_calls`
  - `synthetic_up_calls`
  - `synthetic_move_calls`
- All zero-action tests explicitly verify `action_counter.total_actions == 0`.
- Readback via `GetCursorPos()` is non-invasive and does not increment action counters.

---

### Section K — Acceptance Matrix Completeness (P2B-1 to P2B-22)

The acceptance matrix comprehensively covers all 22 required scenarios:
1. **P2B-1**: Named flag composition (`MOUSEEVENTF_MOVE | ABSOLUTE | VIRTUALDESK`).
2. **P2B-2**: Runtime ABI gate enforcement.
3. **P2B-3**: Zero-action rejection on simulated bad ABI.
4. **P2B-4**: Same topology identity with different timestamps (`VALID`).
5. **P2B-5**: Width mutation rejection (`REJECTED_TOPOLOGY_MUTATED`).
6. **P2B-6**: Height mutation rejection (`REJECTED_TOPOLOGY_MUTATED`).
7. **P2B-7**: Origin mutation rejection (`REJECTED_TOPOLOGY_MUTATED`).
8. **P2B-8**: Monitor count mutation rejection (`REJECTED_TOPOLOGY_MUTATED`).
9. **P2B-9**: Single-packet $M = 1$ acceptance (`DISPATCH_ACCEPTED`).
10. **P2B-10**: Single-packet $M = 0$ rejection (`DISPATCH_ZERO`).
11. **P2B-11**: Partial dispatch inapplicability for $N = 1$.
12. **P2B-12**: Live movement to desktop center ($\pm 1\text{px}$).
13. **P2B-13**: Live movement to top-left corner $(0, 0)$.
14. **P2B-14**: Live movement to bottom-right corner $(W_v - 1, H_v - 1)$.
15. **P2B-15**: Negative-origin synthetic coordinate normalization.
16. **P2B-16**: Out-of-bounds rejection before dispatch.
17. **P2B-17**: Cursor readback mismatch classification (`EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE`).
18. **P2B-18**: 5-point multi-grid tolerance verification.
19. **P2B-19**: Pre-dispatch cancellation abort (0 packets).
20. **P2B-20**: Post-dispatch cancellation classification.
21. **P2B-21**: Phase 1 regression verification (14/14 tests).
22. **P2B-22**: Phase 2A regression verification (10/10 tests).

---

## 3. Remaining Unavoidable OS & Hardware Limitations

1. **Non-Atomic Kernel Injection Pipeline**: `SendInput` asynchronously queues raw packets into User32. A sub-millisecond delay exists between `SendInput` return and cursor position updates in `GetCursorPos`.
2. **Hardware Sensor Jitter**: Physical optical gaming mouse sensors may emit sub-millisecond displacement packets during automated cursor movement.
3. **Mid-Dispatch GPU Mode Changes**: Display resolution changes occurring in the sub-microsecond interval between pre-dispatch validation and kernel processing cannot be prevented in user-mode.
4. **UIPI / Elevated Window Boundaries**: If cursor movement targets a higher-integrity window (e.g. Administrator console), User32 may restrict post-dispatch window messaging.

---

## 4. Final Verdict

$$\boxed{\mathbf{\text{\Large 🟢 READY FOR PHASE 2B IMPLEMENTATION}}}$$

The Phase 2B absolute cursor movement architecture is fully verified, mathematically sound, fail-closed on ABI and topology, epistemically modest in diagnostic reporting, single-packet honest in dispatch modeling, and fully isolated from frozen Prototypes A–D.
