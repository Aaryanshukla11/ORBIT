# ORBIT PROTOTYPE E — ADVERSARIAL PRE-IMPLEMENTATION ARCHITECTURE AUDIT REPORT
## Safe Pointer Action & Click Execution Engine

**Audit Date:** 2026-09-05  
**Auditor:** Independent Systems & Safety Architecture Auditor  
**Target Specification:** `prototypes/prototype_e_pointer/implementation_plan.md` (v1.0.0)  
**Audit Scope:** Pre-Implementation Architecture, Invariants, Mathematical Correctness, Win32 Subsystems, Failure Modes, and Test Matrix  
**Status:** 🟡 **READY ONLY AFTER ARCHITECTURAL CORRECTIONS** (Corrections Specified & Applied to v1.1.0)

---

## 1. Executive Summary

This independent adversarial engineering audit was conducted on the proposed architecture for **ORBIT Prototype E (Safe Pointer Action & Click Execution Engine)** before authorizing any implementation code.

The objective was to actively challenge and stress-test every architectural assertion, Win32 coordinate transformation, button ownership assumption, cancellation propagation guarantee, and empirical verification claim.

### Key Discoveries & Audit Findings:
1. **Repository Baseline Integrity Verified**: Baseline commit is `ca87ef8`. `git diff ca87ef8` across `prototype_a_workspace`, `prototype_b_human_takeover`, `prototype_c_keyboard`, and `prototype_d_observation` confirmed **0 lines modified**; all prior prototypes remain 100% frozen and untouched.
2. **Prototype B Coordinate Limitation Confirmed**: Inspection of `prototypes/prototype_b_human_takeover/input_controller.py` confirmed that `_normalize_coords` assumes virtual screen origin $(0, 0)$ and does not query `SM_XVIRTUALSCREEN` (76) or `SM_YVIRTUALSCREEN` (77). On multi-monitor layouts with secondary monitors to the left ($x < 0$), Prototype B suffers from negative coordinate underflow and incorrect mapping. Prototype E's independent coordinate model is necessary and justified.
3. **Button Ownership Boundaries Clarified**: Windows User32 maintains only a single shared logical button state per button. While ORBIT can strictly track its own internal synthetic injection history (`_orbit_left_down`), emitting synthetic `MOUSEEVENTF_LEFTUP` on takeover will transition the Windows logical button state to UP even if the human is physically holding their hardware mouse button. The architecture must state this Windows-level physical hardware boundary honestly.
4. **SendInput Evidence Layering Enforced**: Win32 `SendInput` success ($N > 0$) strictly demonstrates Layer 4 (User32 packet acceptance into the OS input stream). It does NOT prove Layer 5 (cursor position update), Layer 6 (window message delivery), or Layer 7 (target task execution).
5. **TOCTOU Gap Formalized**: Validation at $T_2$ cannot mathematically eliminate the microsecond race before `SendInput` at $T_4$. Prototype E must implement a 3-phase defense: Pre-Action Validation, Immediate Pre-Dispatch Gate, and Post-Action Verification.
6. **Acceptance Matrix Expanded to E1–E24**: Added explicit tests for Partial SendInput Dispatch Recovery (E21), Target PID Recycling Rejection (E22), Target Mutation During Microsecond Gap (E23), and Display Topology Invalidation (E24).

---

## 2. Repository Baseline & Frozen Prototype Audit

```text
Baseline Commit : ca87ef8 (docs(prototype-d): final independent closure audit)
Git Diff Status : 0 lines modified across Prototypes A, B, C, and D
Working Tree    : Clean (except untracked prototype_e_pointer/ planning artifacts)
```

| Frozen Directory | Verified Frozen | Modifications Detected | Notes |
| :--- | :---: | :---: | :--- |
| `prototypes/prototype_a_workspace/` | **YES** | 0 | Windows workspace docking baseline |
| `prototypes/prototype_b_human_takeover/` | **YES** | 0 | Human takeover & WH_MOUSE_LL safety |
| `prototypes/prototype_c_keyboard/` | **YES** | 0 | Reliable keyboard & unicode engine |
| `prototypes/prototype_d_observation/` | **YES** | 0 | Screen observation & evidence fusion |

---

## 3. Prototype B Coordinate Limitation Verification

Direct source code inspection of `prototypes/prototype_b_human_takeover/input_controller.py` lines 94–127 revealed:

```python
# Prototype B input_controller.py (FROZEN)
self._vscreen_w = user32.GetSystemMetrics(78) or self._screen_w
self._vscreen_h = user32.GetSystemMetrics(79) or self._screen_h

def _normalize_coords(self, x: int, y: int) -> tuple[int, int]:
    norm_x = int((x * 65535) / (self._vscreen_w - 1))
    norm_y = int((y * 65535) / (self._vscreen_h - 1))
    return norm_x, norm_y

def move_to(self, x: int, y: int):
    norm_x, norm_y = self._normalize_coords(x, y)
    inp.union.mi.dx = norm_x
    inp.union.mi.dy = norm_y
    inp.union.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
```

### Technical Audit Findings:
1. **Missing Origin Query**: Prototype B queries `SM_CXVIRTUALSCREEN` (78) and `SM_CYVIRTUALSCREEN` (79), but **never queries** `SM_XVIRTUALSCREEN` (76) or `SM_YVIRTUALSCREEN` (77).
2. **Failure on Left/Top Secondary Monitors**: In a multi-monitor topology where a secondary 1080p monitor is placed to the left of the primary monitor, `SM_XVIRTUALSCREEN = -1920`. For pixel $x = -500$, Prototype B computes `norm_x = int((-500 * 65535) / (W - 1)) < 0`. For pixel $x = 0$ (left edge of primary monitor), Prototype B passes `norm_x = 0`, which Win32 `MOUSEEVENTF_VIRTUALDESK` maps to $SM\_XVIRTUALSCREEN = -1920$ (the left edge of the secondary monitor)!
3. **Audit Conclusion**: The claim in the Prototype E plan is **100% verified and factually accurate**. Prototype B functioned correctly in its isolated single-monitor testbed because $SM\_XVIRTUALSCREEN = 0$, but cannot handle multi-monitor coordinate spaces. Prototype E must solve this independently in its own `coordinate_validator.py`.

---

## 4. Windows Absolute Pointer Coordinate Audit

### 4.1 Win32 Coordinate Space Mathematics
When `MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK` is passed to `user32.SendInput`, the normalized coordinates $(dx, dy)$ are mapped across the entire virtual desktop rectangle defined by:
- Origin: $(x_{v\_origin}, y_{v\_origin}) = (\text{GetSystemMetrics}(76), \text{GetSystemMetrics}(77))$
- Dimensions: $(W_v, H_v) = (\text{GetSystemMetrics}(78), \text{GetSystemMetrics}(79))$
- Coordinate Domain: $[0, 65535] \subset \mathbb{Z}$

### 4.2 Formal Normalization Formula
To prevent integer truncation bias, off-by-one errors, and division-by-zero crashes, Prototype E defines the following coordinate contract:

$$\Delta x = x - x_{v\_origin}, \quad \Delta y = y - y_{v\_origin}$$

$$dx = \begin{cases} 
0 & \text{if } W_v \le 1 \\
\max\left(0, \min\left(65535, \operatorname{round}\left(\frac{\Delta x \times 65535.0}{W_v - 1}\right)\right)\right) & \text{if } W_v > 1 
\end{cases}$$

$$dy = \begin{cases} 
0 & \text{if } H_v \le 1 \\
\max\left(0, \min\left(65535, \operatorname{round}\left(\frac{\Delta y \times 65535.0}{H_v - 1}\right)\right)\right) & \text{if } H_v > 1 
\end{cases}$$

### 4.3 Coordinate Boundary Analysis
| Boundary Point | Virtual Screen Pixel $(x, y)$ | Relative Offset $(\Delta x, \Delta y)$ | Output $(dx, dy)$ | Win32 Destination Mapping |
| :--- | :--- | :--- | :--- | :--- |
| **Top-Left Corner** | $(x_{v\_origin}, y_{v\_origin})$ | $(0, 0)$ | $(0, 0)$ | Exact virtual desktop top-left pixel |
| **Bottom-Right Corner** | $(x_{v\_origin} + W_v - 1, y_{v\_origin} + H_v - 1)$ | $(W_v - 1, H_v - 1)$ | $(65535, 65535)$ | Exact virtual desktop bottom-right pixel |
| **Primary Origin** | $(0, 0)$ | $(-x_{v\_origin}, -y_{v\_origin})$ | $\operatorname{round}\left(\frac{-x_{v\_origin} \times 65535}{W_v - 1}\right)$ | Exact primary monitor top-left pixel |
| **Negative Coordinate** | $(x_{v\_origin} + 100, y_{v\_origin} + 100)$ | $(100, 100) \ge 0$ | $\operatorname{round}\left(\frac{100 \times 65535}{W_v - 1}\right)$ | Correctly positioned in secondary monitor |

### 4.4 Process DPI Awareness Invariant
To guarantee that `GetSystemMetrics`, `GetCursorPos`, and `SendInput` operate strictly in unscaled physical device pixels:
- The Prototype E process must call `user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)` (constant value `-4`) at module initialization before querying any metrics.

---

## 5. SendInput Semantics Reality Audit

### 5.1 The 7 Evidence Layers
To eliminate ambiguous "injection success" claims, Prototype E strictly separates:

```text
LAYER 1: Intent Creation       ──► PointerActionIntent constructed in memory
LAYER 2: Packet Construction   ──► INPUT array populated with ORBIT_EXTRA_INFO_SIGNATURE
LAYER 3: API Invocation        ──► user32.SendInput(nInputs, pInputs, sizeof(INPUT)) called
LAYER 4: Driver Acceptance     ──► Return value M == nInputs reported by User32
LAYER 5: OS Pointer Movement   ──► user32.GetCursorPos() reads back target coordinates ±1px
LAYER 6: Target Message Queue  ──► WM_LBUTTONDOWN / WM_LBUTTONUP queued in target thread
LAYER 7: Target Task Success   ──► Observable UI state mutation (callback fired, counter changed)
```

### 5.2 What SendInput Return Value ACTUALLY Proves
- **If $M == nInputs$**: Proves ONLY **Layer 4**. Windows User32 accepted the packets into the system input stream.
- **What it does NOT prove**:
  1. Does NOT prove the target window was not occluded by a topmost window.
  2. Does NOT prove the target window was not elevated (UIPI silently drops messages to higher-integrity windows without failing `SendInput`).
  3. Does NOT prove the target window message loop processed the event (the target could be hung / `IsHungAppWindow`).
  4. Does NOT prove task success.
- **If $M == 0$**: Injection blocked. Check `kernel32.GetLastError()`. Common causes: UIPI elevation block (`ERROR_ACCESS_DENIED`), invalid flags, or desktop locked.
- **If $0 < M < nInputs$ (Partial Dispatch)**: Critical failure state. If a 2-packet click (`[DOWN, UP]`) returns $M = 1$, the mouse button is left held down in User32! Prototype E must detect $M < nInputs$, log `PARTIAL_DISPATCH`, and trigger immediate `PointerStateManager.sanitize_orbit_buttons()`.

---

## 6. Human Physical Mouse Ownership Audit

### 6.1 What Is Knowable vs Unknowable
| State Domain | Source of Truth | Knowable by ORBIT? | Description |
| :--- | :--- | :---: | :--- |
| **ORBIT Injection History** | `PointerStateManager` in memory | **YES** | Exact set of synthetic DOWN packets dispatched with ORBIT signature and not yet matched with UP. |
| **Windows Logical Button State** | `GetAsyncKeyState(VK_LBUTTON)` | **YES** | Combined OS logical button state. Does NOT distinguish whether human or synthetic pressed it. |
| **Physical Human Button State** | `WH_MOUSE_LL` hook (untagged events) | **PROBABLY** | Hardware mouse clicks intercepted. However, if hook had not started or event timed out, hardware state is ambiguous. |
| **Hardware Physical Switch State** | Microswitch inside physical mouse | **NO** | Physical switch position cannot be queried via Win32 software APIs. |

### 6.2 The Shared Logical State Dilemma & Invariant
- **OS Reality**: Windows User32 maintains only **one** logical button state per mouse button.
- **Sanitization Invariant**:
  1. ORBIT tracks only buttons it explicitly depressed: `_orbit_left_down`, `_orbit_right_down`.
  2. On cancellation or takeover, ORBIT sanitizes ONLY buttons where `_orbit_button_down == True`.
  3. **Honest Limitation Disclosure**: If a human user is physically holding their left mouse button down at the exact moment ORBIT sanitizes an active synthetic drag by emitting `MOUSEEVENTF_LEFTUP`, Windows User32 will transition the shared logical button state to UP. ORBIT cannot prevent Windows from resetting the logical state when synthetic UP is processed.

---

## 7. Human Takeover Race Analysis

### 7.1 Timeline & Latency Breakdown
```text
T1: ORBIT begins pointer trajectory / click preparation
T2: Human physically moves mouse or clicks physical button
T3: Windows kernel delivers event to WH_MOUSE_LL hook           (Δt = 5–50 μs)
T4: Hook verifies untagged event, raises CancellationToken      (Δt = 1–5 μs)
T5: ORBIT trajectory loop checks CancellationToken.is_cancelled (Δt = 10–500 μs)
T6: ORBIT worker stops injection, invokes sanitize_orbit_buttons() (Δt = 5–20 μs)
```

### 7.2 Total Takeover Reaction Time (TTRT)
$$\text{TTRT} = T_6 - T_2 \approx 20\mu s \text{ to } 1.0\text{ms}$$

### 7.3 Adversarial Race Invariants:
1. **No "Instantaneous" Claims**: Takeover latency is governed by thread scheduling and hook message pumping. It is sub-millisecond, but strictly non-zero.
2. **Zero Post-Observation Injection**: Once $T_5$ occurs, the count of subsequent synthetic `SendInput` packets dispatched must be **strictly 0**.
3. **Pre-Observation Dispatches**: Any packet already dispatched to User32 before $T_4$ cannot be recalled. If `MOUSEEVENTF_LEFTDOWN` was dispatched before $T_4$, $T_6$ immediately emits `MOUSEEVENTF_LEFTUP` to release ownership.

---

## 8. Observation → Validation → Action TOCTOU Audit

### 8.1 The Time-of-Check to Time-of-Use (TOCTOU) Problem
```text
T0: ObservationSnapshot captured (Gen G0, HWND H0, Foreground H0)
T1: Target selected & validated in plan
T2: Pre-Dispatch Validation executes (Checks Gen == G0, IsWindow(H0), FG == H0) -> PASSED
T3: CPU Context switch / Win32 dispatch gap (Δt ≈ 5–20 μs)
T4: SendInput(MOUSEEVENTF_LEFTDOWN) executes
```

Between $T_2$ and $T_4$:
- The target window $H_0$ could be closed by the user or an external process.
- Another window could steal foreground focus.
- The desktop could shift or resize.

### 8.2 The 3-Phase Defense Architecture
Because eliminating the microsecond CPU context switch gap is physically impossible in user-mode Windows, Prototype E implements a **3-Phase Defense**:

1. **Phase 1: Pre-Action Validation** (Plan level):
   - Evaluates snapshot age vs TTL ($\le 500\text{ms}$).
   - Validates `DesktopGeneration` parity.
   - Validates `native_hwnd` exists and PID matches.
2. **Phase 2: Immediate Pre-Dispatch Gate** (Microsecond level, right before `SendInput`):
   - `user32.IsWindow(native_hwnd) == True`
   - `user32.GetForegroundWindow() == native_hwnd` (or ancestor)
   - `user32.IsIconic(native_hwnd) == False` (window is not minimized)
   - `cancellation_token.is_cancelled == False`
3. **Phase 3: Post-Action Target Verification** (Target-side verification):
   - Verifies target window remained alive and foreground throughout dispatch.
   - Queries target-side observable state (callback, event counter, caret position).
   - If target state did not mutate, logs `DISPATCHED_BUT_UNVERIFIED` rather than falsely claiming task success.

---

## 9. Drag Transaction Failure Audit

### 9.1 Multi-Stage State Machine
```
┌────────────────────────────────────────────────────────────────────────┐
│                      DRAG TRANSACTION STATE MACHINE                    │
├────────────────────────────────────────────────────────────────────────┤
│  [IDLE]                                                                │
│     │ (Intent received)                                                │
│     ▼                                                                  │
│  [STAGE 1: MOVING_TO_START] ────────► Takeover? ──► [CANCELLED_IDLE]   │
│     │ (Arrived at start)                             (No buttons held) │
│     ▼                                                                  │
│  [STAGE 2: BUTTON_DOWN]     ────────► Takeover? ──► [SANITIZING_UP]    │
│     │ (Recorded in PointerState)                     (Emits UP)        │
│     ▼                                                                  │
│  [STAGE 3: DRAGGING]        ────────► Takeover? ──► [SANITIZING_UP]    │
│     │ (Interpolated steps)                           (Emits UP)        │
│     ▼                                                                  │
│  [STAGE 4: BUTTON_UP]       ──────────────────────► [COMPLETED]        │
│     │ (Recorded in PointerState)                                       │
│     ▼                                                                  │
│  [IDLE]                                                                │
└────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Audit of Failure Scenarios
1. **Takeover during Stage 1**: Trajectory halts; button was never pressed; state returns cleanly to IDLE.
2. **Takeover during Stage 2/3**: Trajectory halts; `PointerStateManager.sanitize_orbit_buttons()` emits immediate `MOUSEEVENTF_LEFTUP`; status returned is `CANCELLED_DURING_HOLD` / `ABORTED_SANITIZED`.
3. **Target Application OLE Drag-Drop Boundary**: When ORBIT aborts a drag midway, ORBIT guarantees it releases its synthetic mouse button. However, whether the target application's internal OLE/COM `IDropTarget` cancels the drag or drops at the intermediate coordinate depends entirely on the target application. Prototype E guarantees **input ownership sanitization**, not target application state rollback.

---

## 10. Immutable Target Contract Audit

Prototype E must consume an immutable, standalone target contract without depending on volatile internal classes of Prototype D:

```python
@dataclass(frozen=True)
class ValidatedPointerTarget:
    target_id: str                      # Unique target identifier for telemetry
    native_hwnd: int                    # Target Win32 HWND
    process_id: int                     # Target process PID (guard against HWND recycling)
    class_name: Optional[str]           # Win32 window class name (e.g. "Button", "Edit")
    expected_bounds: Rect               # Bounding box in virtual desktop coordinates
    click_point: Tuple[int, int]        # Target click coordinate (x, y)
    source_generation_id: int           # DesktopGeneration at time of observation
    source_snapshot_timestamp_ns: int   # Nanosecond timestamp of observation snapshot
    confidence: str                     # Observation confidence ("HIGH", "MEDIUM", "LOW")
    require_foreground: bool = True     # Whether target must be foreground
    validity_ttl_ms: float = 500.0      # Maximum allowed age before snapshot expiry
```

### Target Rejection Rules:
- **Rule 1 (TTL Expired)**: `now_ns - source_snapshot_timestamp_ns > ttl_ns` $\implies$ `REJECTED_TTL_EXPIRED`
- **Rule 2 (Generation Mismatch)**: `current_generation != source_generation_id` $\implies$ `REJECTED_STALE_GENERATION`
- **Rule 3 (HWND Dead)**: `not IsWindow(native_hwnd)` $\implies$ `REJECTED_HWND_DESTROYED`
- **Rule 4 (PID Mismatch)**: `GetWindowThreadProcessId(native_hwnd) != process_id` $\implies$ `REJECTED_PID_MISMATCH`
- **Rule 5 (Foreground Lost)**: `require_foreground and GetForegroundWindow() != native_hwnd` $\implies$ `REJECTED_FOREGROUND_LOST`
- **Rule 6 (Out of Bounds)**: `not expected_bounds.contains_point(click_point)` $\implies$ `REJECTED_OUT_OF_BOUNDS`
- **Rule 7 (Low Confidence)**: `confidence in ("UNRELIABLE", "CONFLICTED")` $\implies$ `REJECTED_LOW_CONFIDENCE`

---

## 11. Multi-Monitor and High-DPI Reality Audit

### 11.1 Host Environment Reality
- **Host System**: Windows 11 Build 26200, AMD64 64-bit, Python 3.13.7.
- **Physical Display**: Single 2.8K Monitor (2880x1800 at 2.0x DPI scaling).
- **Virtual Screen Metrics on Host**: $SM\_XVIRTUALSCREEN = 0, SM\_YVIRTUALSCREEN = 0, SM\_CXVIRTUALSCREEN = 2880, SM\_CYVIRTUALSCREEN = 1800$.

### 11.2 Evidence Classification Discipline
- **Negative Coordinate Mapping ($x < 0$)**: Because the host system has only 1 physical monitor, negative coordinates cannot be physically exercised on live hardware without a secondary display. These tests MUST be classified as `SYNTHETICALLY_SIMULATED` (mathematical simulation against mock virtual desktop topologies).
- **High-DPI Coordinate Mapping (200% DPI)**: Because the host monitor is natively running at 200% DPI, high-DPI coordinate validation CAN be classified as `LIVE_OS_VALIDATED` and `CONTROLLED_LIVE_ENVIRONMENT`.

---

## 12. Formal Acceptance Matrix Audit (Expanded E1–E24)

The acceptance matrix has been expanded from 20 to 24 tests to close all adversarial failure gaps:

| Test ID | Capability | Setup & Target | Action Executed | Observable Verification | Expected Verdict | Evidence Classification |
| :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| **E1** | Absolute Pointer Movement | Live Tkinter target window | Move from $(x_1, y_1)$ to $(x_2, y_2)$ | `GetCursorPos()` matches $(x_2, y_2) \pm 1\text{px}$ | **PASS** | `LIVE_OS_VALIDATED` |
| **E2** | Multi-Monitor / Negative Coords | Secondary monitor origin $(-1920, 0)$ | Normalize & transform negative coord | Coords in $0..65535$; no integer underflow | **PASS** | `SYNTHETICALLY_SIMULATED` |
| **E3** | Coordinate Rounding Precision | Virtual desktop grid points | Compare forward/inverse mapping | Discrepancy $\le 1.0$ physical pixel | **PASS** | `LIVE_OS_VALIDATED` |
| **E4** | Out-of-Bounds Rejection | Coords $(99999, 99999)$ | Attempt move action | CoordinateValidator rejects with error | **PASS** | `LIVE_OS_VALIDATED` |
| **E5** | Single Left Click Execution | Controlled Tkinter button | Dispatch Left Click | Button callback fires; click counter $0 \to 1$ | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |
| **E6** | Right Click Context Menu | Controlled Tkinter text box | Dispatch Right Click | Context menu / right-click event recorded | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |
| **E7** | Double Click Execution | Controlled Tkinter target | Dispatch Double Click (20ms gap) | Double-click callback event triggered | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |
| **E8** | Controlled Drag Execution | Canvas item $(x_1, y_1) \to (x_2, y_2)$ | Multi-stage drag trajectory | Canvas object coordinates updated to $(x_2, y_2)$ | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |
| **E9** | Drag Cancellation Sanitization | Active drag in progress | Inject cancellation token midway | Trajectory halts; ORBIT mouse-up emitted cleanly | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |
| **E10**| Synthetic Button Ownership Isolation | ORBIT mouse-down active | Trigger takeover abort | ORBIT releases synthetic button; physical untouched | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |
| **E11**| Pre-Dispatch Human Takeover | Target ready for click | Human moves mouse before SendInput | Dispatch dropped; click count remains 0 | **PASS** | `PHYSICALLY_VALIDATED` |
| **E12**| Mid-Trajectory Human Takeover | Long trajectory in progress | Human moves mouse during trajectory | Motion halts in $< 1\text{ms}$; control ceded | **PASS** | `PHYSICALLY_VALIDATED` |
| **E13**| Mid-Hold Human Takeover | Button down; hold in progress | Human clicks mouse during hold | Synthetic button released immediately | **PASS** | `PHYSICALLY_VALIDATED` |
| **E14**| Stale Generation Rejection | Snapshot at Gen $G$; advance to $G+1$ | Request click against Gen $G$ | Rejected: `REJECTED_STALE_GENERATION` | **PASS** | `LIVE_OS_VALIDATED` |
| **E15**| Target Destruction Rejection | Target window destroyed | Request click against dead HWND | Rejected: `REJECTED_HWND_DESTROYED` | **PASS** | `LIVE_OS_VALIDATED` |
| **E16**| Foreground Focus Loss Rejection | Target window unfocused | Request click requiring foreground | Rejected: `REJECTED_FOREGROUND_LOST` | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |
| **E17**| Snapshot TTL Expiration | Snapshot age exceeds 500ms | Request click after delay | Rejected: `REJECTED_TTL_EXPIRED` | **PASS** | `LIVE_OS_VALIDATED` |
| **E18**| DPI Scaling Coordinate Contract | High-DPI target (200% scale) | Convert client rect to physical coords | Click lands accurately in target bounding box | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |
| **E19**| Post-Cancellation Zero Leak | Cancelled pointer session | Await subsequent tick | Zero delayed/queued SendInput packets emitted | **PASS** | `LIVE_OS_VALIDATED` |
| **E20**| Full Observe-Validate-Click Loop | Controlled Multi-Widget Target | Full Observe $\to$ Validate $\to$ Click | Target state mutated and verified empirically | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |
| **E21**| Partial SendInput Recovery | Injected $N=2$ click packets | Simulate User32 partial return $M=1$ | Partial return detected; immediate UP emitted | **PASS** | `INTERNAL_LOGIC_VALIDATED` |
| **E22**| Target PID Recycling Rejection | Recycled HWND with new PID | Request click against old target | Rejected: `REJECTED_PID_MISMATCH` | **PASS** | `LIVE_OS_VALIDATED` |
| **E23**| Microsecond TOCTOU Detection | Window closed immediately before SendInput | Dispatch click; post-action check | Discrepancy caught; logged `TARGET_MUTATED` | **PASS** | `CONTROLLED_LIVE_ENVIRONMENT` |
| **E24**| Display Topology Invalidation | Screen bounds mutate during session | Request click against old geometry | Rejected: `REJECTED_TOPOLOGY_CHANGED` | **PASS** | `SYNTHETICALLY_SIMULATED` |

---

## 13. Adversarial Risk Register (R1–R15)

| Risk ID | Risk Description | Cause | Detection | Architectural Mitigation | Unavoidable Boundary | Validation Type |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **R1** | Coordinate conversion off-by-one | Truncation vs rounding in 65535 math | `GetCursorPos` delta check | `round()` + clamp to $[0, 65535]$ | Discrete integer quantization ($\pm 0.5\text{px}$) | `LIVE_OS_VALIDATED` |
| **R2** | Negative coordinate underflow | Secondary monitor left of primary | Origin offset check in validator | Explicit $(x - x_{v\_origin})$ subtraction | Single-monitor host requires synthetic simulation | `SYNTHETICALLY_SIMULATED` |
| **R3** | DPI awareness virtualization mismatch | Default DPI unawareness in Python | `GetDpiForWindow` check | Declare `Per-Monitor V2` awareness at startup | Mixed-DPI monitor transitions | `CONTROLLED_LIVE_ENVIRONMENT` |
| **R4** | Display topology change mid-action | Monitor unplugged / resolution shift | Monitor topology comparison | Re-check `GetSystemMetrics` on each action | Topology shift during microsecond dispatch | `SYNTHETICALLY_SIMULATED` |
| **R5** | Stale observation dispatch | Target moved after snapshot capture | Snapshot timestamp vs now | 500ms hard TTL threshold | Target moving within TTL window | `LIVE_OS_VALIDATED` |
| **R6** | Microsecond TOCTOU race | Context switch between check and SendInput | Post-action target verification | Pre-dispatch gate + Post-action verify | Sub-10$\mu$s Win32 kernel context switch | `CONTROLLED_LIVE_ENVIRONMENT` |
| **R7** | Target HWND reuse | Windows recycled destroyed HWND | PID check via `GetWindowThreadProcessId` | Match HWND + PID + ClassName | None (triple-check eliminates recycling) | `LIVE_OS_VALIDATED` |
| **R8** | Foreground window shift | User or popup steals focus | `GetForegroundWindow` check | Require foreground equality before dispatch | Focus stolen in microsecond dispatch gap | `CONTROLLED_LIVE_ENVIRONMENT` |
| **R9** | Human mouse physical interference | User grabs mouse during ORBIT trajectory | `WH_MOUSE_LL` hook velocity delta | Immediate trajectory abort ($< 1\text{ms}$) | Packets dispatched before hook enters pipeline | `PHYSICALLY_VALIDATED` |
| **R10**| Button ownership ambiguity | Human & ORBIT both hold left button | `PointerStateManager` bitmask | Sanitize ONLY buttons ORBIT depressed | Windows shared logical button state | `CONTROLLED_LIVE_ENVIRONMENT` |
| **R11**| Drag transaction orphaning | Script aborts while button is down | `try...finally` cleanup handler | Auto-invoke `sanitize_orbit_buttons()` | Target app internal OLE drop handling | `CONTROLLED_LIVE_ENVIRONMENT` |
| **R12**| Partial SendInput dispatch | User32 accepts $M < N$ packets | Check `SendInput` return value | Treat $M < N$ as failure; sanitize buttons | Unfinished multi-packet hardware bursts | `INTERNAL_LOGIC_VALIDATED` |
| **R13**| Cancellation propagation latency | Thread scheduling delay in token check | Nanosecond timestamp delta logging | Check token at every trajectory microstep | Non-zero thread wake latency ($\approx 10\mu\text{s}$) | `PHYSICALLY_VALIDATED` |
| **R14**| False target success claim | Treating SendInput success as task success | Target-side callback verification | Separate Layer 4 from Layer 7 strictly | Third-party apps without UIA/callback hooks | `CONTROLLED_LIVE_ENVIRONMENT` |
| **R15**| UIPI privilege elevation block | Target window running as Administrator | `SendInput` returns 0 / GetLastError 5 | Detect return 0 and log UIPI restriction | Non-elevated ORBIT controlling elevated app | `LIVE_OS_VALIDATED` |

---

## 14. Required Architectural Corrections Applied to Implementation Plan

The following 6 corrections have been applied to update `implementation_plan.md` to **v1.1.0**:

1. **Explicit 3-Phase Target Verification Pipeline**: Formalized Pre-Action Validation, Immediate Pre-Dispatch Gate, and Post-Action Target Verification in the data models and execution loop.
2. **Shared OS Logical Button State Disclosure**: Formally documented that while ORBIT isolates its own synthetic depression tracking, Windows User32 maintains a single shared logical button state.
3. **The 7 Evidence Layers Formalized**: Explicitly specified Layers 1–7 in `telemetry.py` and `app_types.py` with zero conflation of injection vs task success.
4. **Coordinate Math Hardening**: Incorporated `round(...)`, division-by-zero guards for $W_v \le 1$, and `SetProcessDpiAwarenessContext(-4)` initialization.
5. **Partial SendInput Dispatch Handling**: Added explicit checks for $M < N$ return values with immediate button state sanitization.
6. **Acceptance Matrix Expansion (E1–E24)**: Added E21 (Partial Dispatch), E22 (PID Recycling), E23 (Microsecond TOCTOU), and E24 (Topology Mutation).

---

## 15. Final Adversarial Verdict

```text
══════════════════════════════════════════════════════════════════════════
                      FINAL ADVERSARIAL VERDICT
══════════════════════════════════════════════════════════════════════════

  🟡 READY ONLY AFTER ARCHITECTURAL CORRECTIONS
     (All required corrections have been documented and incorporated
      into Implementation Plan v1.1.0. Implementation source code is
      now eligible for authorized development under strict isolation.)

══════════════════════════════════════════════════════════════════════════
```

---

## 16. Stop Condition Enforcement

**AUDIT COMPLETE.**  
- No Prototype E implementation source code has been created (`pointer_controller.py`, `target_validator.py`, etc. do not exist).  
- Prototypes A, B, C, and D remain 100% frozen and untouched.  
- Only documentation and planning artifacts have been produced.
