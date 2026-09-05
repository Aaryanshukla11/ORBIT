# ORBIT Milestone M1.5: Production Workspace & AppBar Test Matrix

**Milestone**: M1.5 — Production Workspace / AppBar Integration  
**Status**: **APPROVED SPECIFICATION**  
**Date**: September 6, 2026  
**Target Subsystem**: `src/orbit/adapters/workspace/`

---

## 1. Test Suite Architecture

The M1.5 test matrix consists of three validation layers:
1. **Unit Tests (`tests/unit/test_workspace_*.py`)**: Isolated, deterministic tests covering ABI alignment, state machines, geometry arithmetic, DPI math, generation tracking, and cancellation.
2. **Integration Tests (`tests/integration/test_workspace_runtime_integration.py`)**: End-to-end tests validating adapter lifecycle, Orchestrator wiring, EventBus publishing, Observation freshness invalidation, and Emergency Safety coordination.
3. **Live OS Validation (`tests/live/test_workspace_live_validation.py`)**: Controlled Windows 11 live tests validating `SHAppBarMessage` interaction, `WS_EX_TOPMOST` docking, and watchdog crash restoration.

---

## 2. Unit Test Matrix

| Test ID | Test Category | Target Functionality | Input / Conditions | Expected Outcome | Verification Metric |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **UT-WS-01** | ABI Validation | AMD64 `APPBARDATA` structure size and offsets | Ctypes struct inspection on 64-bit Python | `sizeof(APPBARDATA) == 48`, `hWnd` offset = 8, `uCallbackMessage` = 16, `rc` = 24 | Exact byte alignment |
| **UT-WS-02** | ABI Validation | AMD64 `RECT` structure size and helper properties | Ctypes `RECT(0, 0, 1920, 1080)` | `width == 1920`, `height == 1080`, `to_dict()` valid | Math correctness |
| **UT-WS-03** | State Machine | Normal progression lifecycle | `UNINITIALIZED` $\to$ `READY_FLOATING` $\to$ `REGISTERING` $\to$ `DOCKED` $\to$ `RELEASING` $\to$ `READY_FLOATING` | All transitions succeed without error | `current_state` matches |
| **UT-WS-04** | State Machine | Illegal state transition rejection | Attempt `UNINITIALIZED` $\to$ `DOCKED` or `DOCKED` $\to$ `REGISTERING` | Raises `StateTransitionError` | Transition rejected |
| **UT-WS-05** | State Machine | Terminal state isolation | Attempt transition out of `STOPPED` | Raises `StateTransitionError` | Terminal lock |
| **UT-WS-06** | State Machine | Degraded recovery workflow | `DOCKED` $\to$ `DEGRADED` $\to$ `recover_workspace("CONFIRM_RESET")` $\to$ `READY_FLOATING` | State resets cleanly with valid token | Token gate enforced |
| **UT-WS-07** | Geometry | 25% Right-Edge Docking calculation | Display $2880 \times 1800$, ratio 0.25, min 380, max 720 | Docked: $(2160, 0, 2880, 1800)$ [720px]; Usable Canvas: $(0, 0, 2160, 1800)$ | Exact pixel bounds |
| **UT-WS-08** | Geometry | 25% Left-Edge Docking calculation | Display $2880 \times 1800$, ratio 0.25 | Docked: $(0, 0, 720, 1800)$ [720px]; Usable Canvas: $(720, 0, 2880, 1800)$ | Exact pixel bounds |
| **UT-WS-09** | Geometry | Minimum / Maximum Width Clamping | Request width 200px (clamp to 380px); Request 1000px (clamp to 720px) | Clamped bounds returned | Bounding box clamped |
| **UT-WS-10** | Geometry | DPI Scaling arithmetic | 192 DPI (2.0x scale) on $2880 \times 1800$ | Logical dimensions $1440 \times 900$; Docked 360pt | DPI scale factor |
| **UT-WS-11** | Generation ID | Desktop Generation Increment on Layout Change | Initial `gen = 1` $\to$ Dock $\to$ `gen = 2` $\to$ Undock $\to$ `gen = 3` | Generation counter monotonically increments | `generation_id` parity |
| **UT-WS-12** | Telemetry | Telemetry aggregation & health model | Record registration latency, current edge, error count | `CapabilityHealth` reports `HEALTHY` and truthful details | Health details dictionary |

---

## 3. Integration Test Matrix

| Test ID | Test Category | Target Subsystem | Setup & Action | Expected Outcome | Verification Gate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **IT-WS-01** | Adapter Lifecycle | `ProductionWorkspaceAdapter` | `initialize()` $\to$ `is_ready == True`, captures baseline work area, spawns watchdog coordinator | Subsystem transitions to `READY_FLOATING` | Lifecycle verified |
| **IT-WS-02** | Idempotent Docking | `ProductionWorkspaceAdapter` | Call `reserve_workspace(RIGHT)` twice consecutively | Second call returns existing geometry without redundant native registration | Zero redundant `ABM_NEW` |
| **IT-WS-03** | EventBus Publishing | Runtime Event Pipeline | Dock and Undock workspace via adapter | Publishes `EventType.WORKSPACE_STATE_CHANGED` with valid `WorkspaceGeometry` payload | Event sequence & payload |
| **IT-WS-04** | Observation Freshness | `ObservationCapability` + Workspace | Capture observation frame at `gen = 1` $\to$ Dock workspace (`gen = 2`) $\to$ Query `FreshnessEvaluator` | Evaluator returns `FreshnessState.STALE` with `GENERATION_MISMATCH` | Stale cache rejection |
| **IT-WS-05** | Pointer Safety Boundary | `PointerCapability` + Workspace | Attempt synthetic click inside docked AppBar $(2500, 500)$ during active task | Rejected or flagged as reserved area interaction | Safety boundary gate |
| **IT-WS-06** | Human Takeover Preemption | `HumanTakeoverCapability` + Workspace | Trigger physical takeover while workspace is docked | Workspace remains docked; active workspace task commands cancelled | State stability preserved |
| **IT-WS-07** | Emergency Safety Stop | `EmergencySafetyCoordinator` | Invoke `emergency_stop_all()` | Verifies workspace integrity; preserves fail-closed safety | Safe resting state |
| **IT-WS-08** | Shutdown Cleanup | Capability Registry Shutdown | Invoke `shutdown()` on adapter | Calls `ABM_REMOVE`, cleans native window class, terminates watchdog | Zero leaked handles |

---

## 4. Live Windows 11 Validation Matrix

| Test ID | Test Name | Setup & Prerequisites | Action Procedure | Expected Result | Cleanup Procedure | Evidence Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **LIVE-WS-01** | Native Window Creation & Topmost Dock | Live Windows 11 AMD64 display | Create `WS_EX_TOPMOST` borderless window; dock to Right 25% edge | Window created at $(2160, 0, 720 \times 1800)$; visible on top | `DestroyWindow(hwnd)` | `LIVE_OS_VALIDATED` |
| **LIVE-WS-02** | Native AppBar Shell Negotiation | Top-level window created | Call `SHAppBarMessage(ABM_NEW, ABM_QUERYPOS, ABM_SETPOS)` | Shell acknowledges registration; returns assigned rect | `ABM_REMOVE` | `LIVE_OS_VALIDATED` |
| **LIVE-WS-03** | Normal Floating App Coexistence | ORBIT docked at Right 25% | Launch Notepad at $(100, 100, 1200 \times 800)$ | Notepad floats cleanly in usable 75% canvas; ORBIT remains visible | Terminate Notepad | `LIVE_OS_VALIDATED` |
| **LIVE-WS-04** | Maximized App Boundary Observation | ORBIT docked at Right 25% | Maximize Notepad via `ShowWindow(SW_MAXIMIZE)` | Notepad maximizes across monitor; ORBIT overlay remains stable | Terminate Notepad | `LIVE_OS_VALIDATED` |
| **LIVE-WS-05** | Clean Unregistration & Work Area Match | Active docked AppBar | Call `ABM_REMOVE`, destroy window, query `SPI_GETWORKAREA` | Post-unregistration work area exactly matches pre-launch baseline | Window destroyed | `LIVE_OS_VALIDATED` |
| **LIVE-WS-06** | Abnormal Termination & Watchdog Recovery | Child process docked + detached `watchdog.py` | Forcefully kill child PID via `taskkill /F /PID` | Watchdog detects PID exit; verifies/restores work area in $<350\text{ms}$ | Watchdog self-terminates | `LIVE_OS_VALIDATED` |
| **LIVE-WS-07** | Per-Monitor DPI Scaling (192 DPI) | Per-Monitor DPI Awareness v2 | Query monitor DPI via `GetDpiForMonitor` and compute pixel metrics | Exact $2.0\times$ scale detected; logical layout matches physical pixels | None | `LIVE_OS_VALIDATED` |
| **LIVE-WS-08** | Multi-Monitor Topology Evaluation | Multi-display hardware (if attached) | Enumerate monitors via `EnumDisplayMonitors` | Multi-monitor bounds mapped (or flagged as single-monitor) | None | `LIVE_OS_VALIDATED` / `HARDWARE_GATED` |

---

## 5. Verification Rules

1. **Epistemic Honesty**: If a test runs against a mock or synthetic environment, it must be marked `SYNTHETICALLY_SIMULATED`. Only real Win32 API calls on host Windows OS may be marked `LIVE_OS_VALIDATED`.
2. **Zero Leak Rule**: Every live window (`HWND`), class (`WNDCLASSEXW`), and child process must be cleaned up in a `finally:` block.
3. **Restoration Integrity**: Baseline desktop work area must be checked before and after tests to ensure zero lingering desktop distortion.
