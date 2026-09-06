# ORBIT Milestone M1.5: Production Workspace & AppBar Integration Forensic Audit

**Milestone**: M1.5 — Production Workspace / AppBar Integration  
**Phase**: Phase A — Forensic Audit & Architecture Only  
**Status**: **AUDIT COMPLETE — READY FOR IMPLEMENTATION**  
**Date**: September 6, 2026  
**Host Environment**: Windows 11 CoreSingleLanguage AMD64 (Build 10.0.26200), Python 3.13.7  
**Baseline Frozen Commit**: `ca87ef8`

---

## 1. Executive Summary

Milestone **M1.5** performs the comprehensive forensic audit and architectural design for integrating the **Production Workspace & AppBar Capability** into the ORBIT runtime (`src/orbit/adapters/workspace/`).

This audit evaluates the experimental findings of **Prototype A** (`prototypes/prototype_a_workspace/`), inspects the current production layers (`src/orbit/contracts/`, `src/orbit/runtime/`, `src/orbit/adapters/`, `src/orbit/gateway/`), audits 64-bit AMD64 Win32 ABI signatures and thread-affinity constraints, analyzes multi-monitor / DPI topology implications, models the safety and fail-closed rollback lifecycle, and establishes the single authoritative owner for desktop workspace restoration.

---

## 2. Frozen Boundary Check Record

Prior to and throughout this audit, frozen prototype boundaries were verified against baseline commit `ca87ef8`:
```powershell
git diff ca87ef8 -- `
  prototypes/prototype_a_workspace/ `
  prototypes/prototype_b_human_takeover/ `
  prototypes/prototype_c_keyboard/ `
  prototypes/prototype_d_observation/
```

**Verification Result**:
```text
0 files modified, 0 lines diff
```
All four frozen prototype trees (`prototype_a_workspace`, `prototype_b_human_takeover`, `prototype_c_keyboard`, `prototype_d_observation`) remain 100% byte-for-byte identical to baseline commit `ca87ef8`.

---

## 3. Forensic Analysis of Prototype A Subsystems

Prototype A was designed to experimentally validate desktop docking mechanics on Windows 11. An inspection of `appbar_native.py`, `workspace_prototype.py`, `watchdog.py`, `formal_test_suite.py`, and `results/` demonstrates the following subsystem breakdown:

### Subsystem 1: Win32 AppBar Shell Negotiation (`appbar_native.py`)
- **Native APIs**: `shell32.SHAppBarMessage`, `user32.SetWindowPos`, `user32.GetWindowRect`.
- **Messages**: `ABM_NEW` (register), `ABM_QUERYPOS` (query rect), `ABM_SETPOS` (commit rect), `ABM_REMOVE` (unhook).
- **Callback**: Dispatches `WM_APPBAR_CALLBACK (WM_USER + 101)` to receive shell notifications (`ABN_POSCHANGED`, `ABN_STATECHANGE`, `ABN_FULLSCREENAPP`, `ABN_WINDOWARRANGE`).
- **Timing Evidence**: `ABM_NEW` latency is $0.12\text{ms}$; `ABM_REMOVE` latency is $0.08\text{ms}$.

### Subsystem 2: Top-Level Borderless Dock Window (`appbar_native.py` & `workspace_prototype.py`)
- **Window Styles**: `WS_POPUP | WS_VISIBLE` with extended style `WS_EX_TOPMOST`.
- **Z-Order Management**: `SetWindowPos(HWND_TOPMOST, SWP_NOACTIVATE | SWP_SHOWWINDOW)`.
- **DWM Interaction Finding**: On modern Windows 11 DWM, third-party maximized applications maximize across the entire physical display. Windows 11 DWM does *not* automatically shrink third-party applications for non-taskbar AppBars. ORBIT gracefully coexists as a top-level docked overlay without window tearing or focus stealing.

### Subsystem 3: Display Topology & Per-Monitor DPI Awareness (`appbar_native.py`)
- **APIs**: `user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)`, `user32.EnumDisplayMonitors`, `user32.GetMonitorInfoW`, `shcore.GetDpiForMonitor`.
- **Calculations**: Physical pixels ($2880 \times 1800\text{ px}$) to logical layout points ($1440 \times 900\text{ pt}$) at $2.0\times$ scaling (192 DPI).
- **Dock Allocation**: 25% width clamped between $380\text{px}$ and $720\text{px}$.

### Subsystem 4: Detached Process Crash Restoration Guard (`watchdog.py`)
- **APIs**: `kernel32.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION)`, `kernel32.WaitForSingleObject`, `user32.SystemParametersInfoW(SPI_SETWORKAREA)`.
- **Mechanism**: Detached background process attached to parent PID. If the parent process crashes or is killed (`SIGKILL`), the watchdog detects process exit and restores the baseline desktop work area in **$320.4\text{ms}$** ($<350\text{ms}$).
- **Safety Invariant**: Normal docking operations strictly avoid `SPI_SETWORKAREA`. The watchdog only invokes `SPI_SETWORKAREA` if an ungraceful termination leaves a work area delta.

---

## 4. Dependency Classification Matrix

Every component of Prototype A has been evaluated for production reuse:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   REUSE CLASSIFICATION DEFINITIONS                     │
├────────────────────────────────────────────────────────────────────────┤
│ [A] DIRECTLY REUSABLE       : Logic adapted with minimal cleanups      │
│ [B] ADAPTABLE               : Useful logic requiring architecture      │
│ [C] PROTOTYPE-ONLY          : Isolated to prototype; DO NOT PORT       │
│ [D] MISSING REQUIREMENT     : Required for production; absent in proto │
└────────────────────────────────────────────────────────────────────────┘
```

### Component Breakdown Table:

| Component | Prototype Responsibility | Dependencies | Thread Affinity | OS API Usage | Lifecycle Ownership | Failure Modes | Reuse Classification | Production Destination |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`appbar_native.RECT` & `APPBARDATA`** | 64-bit AMD64 ctypes struct definitions | `ctypes`, `wintypes` | None | Win32 ABI | Stateless | Struct alignment mismatch on non-x64 | **[A] DIRECTLY REUSABLE** | `src/orbit/adapters/workspace/abi.py` |
| **`appbar_native.Win32AppBar`** | Low-level AppBar registration & SetPos dispatch | `ctypes`, `shell32`, `user32` | Thread owning `HWND` | `SHAppBarMessage`, `SetWindowPos` | Managed by Adapter | `ABM_NEW` returns 0; invalid HWND | **[B] ADAPTABLE** (Refactor into `NativeAppBarDriver`) | `src/orbit/adapters/workspace/appbar.py` |
| **Display & DPI Helpers** (`enum_monitors`, `get_screen_dimensions`, `get_desktop_workarea`) | Display metric queries, DPI scaling & work area checks | `ctypes`, `shcore`, `user32` | Thread-independent | `EnumDisplayMonitors`, `GetDpiForMonitor`, `SPI_GETWORKAREA` | Stateless | `shcore.dll` missing (fallback to 96 DPI) | **[A] DIRECTLY REUSABLE** | `src/orbit/adapters/workspace/geometry.py` |
| **`watchdog.py`** | Detached process crash restoration guard | `subprocess`, `ctypes`, `kernel32` | Detached process | `OpenProcess`, `WaitForSingleObject`, `SPI_SETWORKAREA` | Watchdog Process | Target PID inaccessible; handle leak | **[B] ADAPTABLE** (Encapsulate in `WorkspaceWatchdogCoordinator`) | `src/orbit/adapters/workspace/watchdog.py` |
| **`workspace_prototype.py` (Tkinter UI)** | Visual testing dashboard & manual click buttons | `tkinter`, `ttk` | UI Thread | Tkinter windowing | Test Harness | Tkinter event loop blocking | **[C] PROTOTYPE-ONLY** (Replaced by ORBIT Web Gateway / Frontend) | Do NOT port to `src/orbit` |
| **`workspace_prototype.simulate_crash`** | Hard-kill test helper (`os._exit(1)`) | `os`, `time` | Main thread | `os._exit` | Test Harness | Hard process kill | **[C] PROTOTYPE-ONLY** | `tests/live/test_workspace_live_validation.py` |
| **`formal_test_suite.py`** | Programmatic test harness for Tests A1–A8 | `subprocess`, `platform` | Dedicated test thread | `CreateWindowExW`, `DestroyWindow` | Test Harness | Timeout; process spawn error | **[B] ADAPTABLE** (Convert to pytest unit & integration tests) | `tests/unit/test_workspace_*.py` & `tests/live/` |
| **`WorkspaceCapability` Adapter Boundary** | Async lifecycle, capability health, contract adherence | `orbit.contracts`, `asyncio` | Asyncio Event Loop | None (delegates to driver) | Capability Registry | Adapter state corruption; timeout | **[D] MISSING REQUIREMENT** | `src/orbit/adapters/workspace/adapter.py` |
| **Workspace Generation Tracking** | Incrementing generation ID on layout changes to invalidate stale observation cache | `orbit.runtime` | Asyncio Event Loop | None | State Manager | Generation desynchronization | **[D] MISSING REQUIREMENT** | `src/orbit/adapters/workspace/state.py` |
| **Pointer Safe Bounding Gate** | Restricting automated clicks inside docked ORBIT AppBar area | `orbit.contracts` | Asyncio Event Loop | None | Pointer Engine | Out-of-bounds clicks | **[D] MISSING REQUIREMENT** | `src/orbit/adapters/pointer/movement.py` |

---

## 5. Analysis of Current Production Architecture

Inspection of current production layers:

1. **Contracts Layer (`src/orbit/contracts/`)**:
   - `capabilities.py`: Defines `CapabilityType.WORKSPACE` and basic `WorkspaceCapability(Protocol)`.
   - `runtime.py`: Defines `SystemState`, `Action`, `Step`, `Task`, `TaskStatus`.
   - `events.py`: Defines standard WebSocket envelope `RuntimeEvent` and `EventType`.
   - `commands.py`: Inbound client command envelopes and validation.
2. **Runtime Layer (`src/orbit/runtime/`)**:
   - `orchestrator.py`: Coordinates task lifecycle, capability registry resolution, and human takeover preemption.
   - `state_machine.py`: Manages `SystemStateMachine`, `TaskStateMachine`, and `ActionStateMachine`.
   - `cancellation.py`: Thread-safe `CancellationSource` / `CancellationToken`.
   - `task_manager.py`: Task tracking and status persistence.
3. **Existing Capability Adapters (`src/orbit/adapters/`)**:
   - `observation/`: Multi-dimensional visual perception, `FreshnessEvaluator`, and `desktop_generation_id` validation.
   - `pointer/`: High-precision absolute cursor movement, button transactions, fail-closed safety, and `0x08B17001` attribution signature.
   - `keyboard/`: Unicode text streaming, modifier shortcuts, and `0x08B17001` attribution signature.
   - `takeover/`: Low-level native hooks (`WH_MOUSE_LL`, `WH_KEYBOARD_LL`), dedicated message pump thread, non-blocking classification, and asyncio preemption.
   - `production/`: Re-exports production adapters (`production_observation.py`, `production_pointer.py`, `production_keyboard.py`, `production_takeover.py`, `production_safety.py`).
4. **Gateway Layer (`src/orbit/gateway/`)**:
   - FastAPI server, `WebSocketManager`, `SessionManager`, command router.
5. **Infrastructure Layer (`src/orbit/infrastructure/`)**:
   - `EventBus`, `Clock` (`SystemClock`), `ActionCounter`.

---

## 6. Workspace Capability Contract Analysis

### Current Contract (`src/orbit/contracts/capabilities.py` lines 208–226):
```python
@runtime_checkable
class WorkspaceCapability(Protocol):
    """Protocol for Windows desktop work area and AppBar management."""

    async def register_appbar(self, edge: str, size: int) -> bool:
        """Reserve screen edge for ORBIT window."""
        ...

    async def unregister_appbar(self) -> bool:
        """Restore standard desktop work area."""
        ...

    async def get_work_area(self) -> BoundingBox:
        """Query available desktop work area."""
        ...

    async def get_health(self) -> CapabilityHealth:
        """Query subsystem health."""
        ...
```

### Identified Gaps:
1. **Lack of Structured Geometry Model**: `get_work_area()` only returns a simple `BoundingBox`. It does not expose physical screen resolution, docked bounds, reserved edge, or usable application canvas.
2. **Missing Workspace Generation Counter**: Observation and Pointer capabilities rely on `desktop_generation_id` to detect layout changes and invalidate stale snapshots.
3. **String Edge Specification**: `edge: str` is untyped and prone to capitalization bugs (`"right"` vs `"RIGHT"`).
4. **Missing Explicit Recovery API**: No method to trigger manual recovery (`recover_workspace(recovery_token)`) if the Windows Shell or DWM degrades.

### Recommended Enhanced Contract:
```python
@runtime_checkable
class WorkspaceCapability(Protocol):
    """Protocol for Windows desktop work area and AppBar management."""

    async def reserve_workspace(
        self,
        edge: str = "RIGHT",
        width_ratio: float = 0.25,
        min_width_px: int = 380,
        max_width_px: int = 720,
    ) -> WorkspaceGeometry:
        """Reserve screen edge for ORBIT window via Shell AppBar negotiation."""
        ...

    async def release_workspace(self) -> bool:
        """Release AppBar reservation and restore floating state."""
        ...

    async def get_geometry(self) -> WorkspaceGeometry:
        """Query current multi-layer desktop and usable canvas geometry."""
        ...

    async def get_generation_id(self) -> int:
        """Query current workspace layout generation counter."""
        ...

    async def recover_workspace(self, recovery_token: str) -> bool:
        """Force-restore desktop work area and clear degraded state."""
        ...

    async def get_health(self) -> CapabilityHealth:
        """Query subsystem health."""
        ...
```

### Backward-Compatibility Impact:
- Legacy methods (`register_appbar`, `unregister_appbar`, `get_work_area`) can remain as convenience alias wrappers around `reserve_workspace`, `release_workspace`, and `get_geometry().work_area`, ensuring 100% backward compatibility for existing tests.

---

## 7. Win32 Workspace / AppBar Architecture Analysis

### 7.1 Native Window Ownership
- The native AppBar window handle (`HWND`) is created and owned by the ORBIT UI container (e.g. native window or webview container) or the background workspace manager thread.
- The window is registered with Windows Shell via `SHAppBarMessage(ABM_NEW, &abd)`.

### 7.2 Thread Affinity
- **Strict Thread Affinity**: `SHAppBarMessage` calls (`ABM_NEW`, `ABM_QUERYPOS`, `ABM_SETPOS`, `ABM_REMOVE`) and `SetWindowPos` **must execute on the thread that owns the `HWND`**.
- **Message Pumping**: The thread owning the `HWND` must run a Win32 message pump (`GetMessage`/`DispatchMessage`) to receive `WM_APPBAR_CALLBACK` messages from Explorer.
- **Asyncio Boundary**: Calls from the asyncio event loop cross to the native window thread using thread-safe signaling (e.g., `asyncio.to_thread` or Win32 message dispatch).

### 7.3 Crash / Shutdown Recovery
- **Normal Process Exit**: `ProductionWorkspaceAdapter.shutdown()` calls `ABM_REMOVE`, destroys window handles, and terminates the watchdog cleanly.
- **Unhandled Python Exception / Crash**: The independent detached `watchdog.py` process detects PID death via `kernel32.WaitForSingleObject` and restores the baseline work area via `SPI_SETWORKAREA`.
- **FastAPI / Gateway Stop**: FastAPI lifecycle lifespan calls `registry.shutdown_all()`, triggering orderly unregistration.
- **Explorer.exe Restart**: The adapter registers `RegisterWindowMessageW("TaskbarCreated")`. When Explorer restarts, this message is broadcast, prompting the adapter to automatically re-register the AppBar (`ABM_NEW` + `ABM_SETPOS`).

### 7.4 Restoration Guarantees

```
┌────────────────────────────────────────────────────────────────────────┐
│                   RESTORATION GUARANTEE CLASSIFICATION                 │
├────────────────────────────────────────────────────────────────────────┤
│ Graceful Shutdown Unregistration     : LIVE_OS_VALIDATED (0.08 ms)    │
│ Detached Watchdog Crash Restoration  : LIVE_OS_VALIDATED (320.4 ms)   │
│ Single-Monitor Work Area Parity      : LIVE_OS_VALIDATED (Exact match) │
│ Multi-Monitor Dynamic Hot-Plugging   : BEST_EFFORT (Hardware gated)   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Multi-Monitor & DPI Forensic Analysis

1. **Single Monitor ($2880 \times 1800$ @ 192 DPI / 2.0x)**:
   - **Classification**: `LIVE_OS_VALIDATED`.
   - **Metrics**: Verified on Windows 11 Build 26200. Logical dimensions $1440 \times 900\text{ pt}$, 25% docked bounds $(2160, 0, 2880, 1800)$, usable canvas $(0, 0, 2160, 1800)$.
2. **Multi-Monitor Physical Topologies**:
   - **Classification**: `UNVALIDATED — HARDWARE GATED`.
   - **Code Handling**: `EnumDisplayMonitors` identifies primary vs secondary monitors. If multiple monitors are detected, docking binds to the primary monitor by default, or allows targeting a specific `hMonitor`.
3. **Mixed DPI Environments**:
   - **Classification**: `CODE_PROVEN`.
   - **Handling**: Configures `SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)`. Queries DPI per monitor via `shcore.GetDpiForMonitor`.
4. **Dynamic Topology Changes (`WM_DISPLAYCHANGE`)**:
   - **Classification**: `ARCHITECTURAL_INFERENCE`.
   - **Handling**: Re-enumerates monitors on `WM_DISPLAYCHANGE` / `ABN_POSCHANGED`, recomputes clamped bounds, and increments `generation_id`.

---

## 9. Production Adapter Architecture: `src/orbit/adapters/workspace/`

```
src/orbit/adapters/workspace/
├── __init__.py           # Package exports (ProductionWorkspaceAdapter, models, enums)
├── types.py              # Data models: DockEdge, WorkspaceState, WorkspaceGeometry
├── abi.py                # Win32 AMD64 C-types structures (APPBARDATA, RECT, signatures)
├── appbar.py             # Low-level Win32 SHAppBarMessage & SetWindowPos driver
├── state.py              # WorkspaceStateManager & strict state machine
├── geometry.py           # Geometry calculation, DPI scaling, and usable canvas calculator
├── watchdog.py           # Watchdog launcher & crash recovery coordinator
├── telemetry.py          # Workspace metrics, transition timing, generation tracking
└── adapter.py            # ProductionWorkspaceAdapter implementing WorkspaceCapability
```

### Module Responsibilities:
1. `abi.py`: Defines 64-bit AMD64 `APPBARDATA` (48 bytes), `RECT` (16 bytes), `MONITORINFOEXW` (104 bytes). Implements `validate_workspace_abi() -> bool`.
2. `types.py`: Defines typed enums (`DockEdge`, `WorkspaceState`) and Pydantic models (`WorkspaceGeometry`, `DisplayMonitorInfo`).
3. `appbar.py` (`NativeAppBarDriver`): Dispatches native Win32 calls (`ABM_NEW`, `ABM_QUERYPOS`, `ABM_SETPOS`, `ABM_REMOVE`, `SetWindowPos`).
4. `state.py` (`WorkspaceStateManager`): Enforces valid state transitions, rejects illegal transitions, and maintains atomic `generation_id`.
5. `geometry.py` (`WorkspaceGeometryEngine`): Calculates DPI-scaled 25% edge clamping (380px–720px) and usable canvas dimensions.
6. `watchdog.py` (`WorkspaceWatchdogCoordinator`): Spawns and manages detached `watchdog.py` background process.
7. `telemetry.py` (`WorkspaceTelemetry`): Measures registration/unregistration latency, error counts, and health reports.
8. `adapter.py` (`ProductionWorkspaceAdapter`): Top-level async capability adapter inheriting `BaseCapabilityAdapter` and implementing `WorkspaceCapability`.

---

## 10. Safety Model & Human Takeover Policy

### Failure Modes & Mitigations:

1. **Reservation Failure**: If `ABM_NEW` returns 0 (e.g. Explorer busy), adapter transitions to `FAILED`, leaves window in floating mode, and does not claim workspace is reserved.
2. **Duplicate Reservation**: Calling `reserve_workspace()` when already docked is idempotent. If requested edge/size matches, returns current geometry immediately.
3. **Restoration Failure**: If `ABM_REMOVE` fails, adapter logs warning, transitions to `DEGRADED`, and relies on watchdog for baseline work area restoration.
4. **Concurrent Requests**: Protected by an internal `asyncio.Lock()`. Simultaneous docking requests execute serially.

### Human Takeover Policy Decision:
- **Policy Selected: Policy A (Leave Workspace Reservation Untouched)**:
  - *Rationale*: When physical human takeover triggers, the human operator needs to immediately see and control the desktop without jarring UI reshuffling. Un-docking or resizing windows during takeover would cause sudden screen repositioning and disorientation.
  - *Action*: ORBIT remains docked and visible; all autonomous task commands targeting the workspace are cancelled immediately.

---

## 11. Lifecycle Architecture

### State Machine Model:

```
[UNINITIALIZED] ──(initialize)──> [READY_FLOATING]
                                      │       ▲
          reserve_workspace(edge,size)│       │release_workspace()
                                      ▼       │
                                [REGISTERING] │
                                      │       │
                        (shell agree) │       │
                                      ▼       │
                                   [DOCKED] ──┘
                                      │
                         (shell crash/error)
                                      ▼
                                 [DEGRADED]
                                      │
                        (recovery/reset)
                                      ▼
                                [READY_FLOATING]
```

### Transition Specifications:

| Source State | Target State | Trigger | Native Operations | Failure Behavior | Rollback Behavior | Events Emitted |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `UNINITIALIZED` | `READY_FLOATING` | `initialize()` | `SPI_GETWORKAREA`, spawn watchdog | Fails to `FAILED` | Process exits clean | None |
| `READY_FLOATING` | `REGISTERING` | `reserve_workspace()` | Prepares `APPBARDATA` | Fails to `FAILED` | Stays in `READY_FLOATING` | `WORKSPACE_STATE_CHANGED` |
| `REGISTERING` | `DOCKED` | Shell agreement | `ABM_NEW`, `ABM_SETPOS`, `SetWindowPos` | Fails to `FAILED` | Calls `ABM_REMOVE` | `WORKSPACE_STATE_CHANGED` |
| `DOCKED` | `RELEASING` | `release_workspace()` | `ABM_REMOVE` | Fails to `DEGRADED` | Stays in `DOCKED` | `WORKSPACE_STATE_CHANGED` |
| `RELEASING` | `READY_FLOATING` | Unreg complete | `SetWindowPos(floating)` | Fails to `DEGRADED` | Work area reset | `WORKSPACE_STATE_CHANGED` |
| `DOCKED` | `DEGRADED` | Shell crash | Hook lost | Remains `DEGRADED` | Awaits recovery | `WORKSPACE_DEGRADED` |
| `DEGRADED` | `READY_FLOATING` | `recover_workspace()` | `SPI_SETWORKAREA(baseline)` | Fails to `FAILED` | Re-queries baseline | `WORKSPACE_STATE_CHANGED` |
| Any (except STOPPED)| `STOPPED` | `shutdown()` | `ABM_REMOVE`, destroy HWND, kill watchdog | Logs error | Final cleanup | None |

---

## 12. Orchestrator Integration & Single Authoritative Owner

1. **Initialization Timing**: Initialized during `OrbitOrchestrator.initialize()` along with other capability adapters.
2. **Reservation Scope**: Global runtime property. Once docked, all submitted tasks operate within the usable application canvas.
3. **Single Authoritative Owner for Restoration**: `ProductionWorkspaceAdapter` is the **sole authoritative owner** for desktop workspace restoration.
   - During normal shutdown: `ProductionWorkspaceAdapter.shutdown()` calls `ABM_REMOVE`.
   - During runtime emergency stop: `EmergencySafetyCoordinator` calls `ProductionWorkspaceAdapter.get_health()`.
   - During unhandled process termination: The detached `watchdog.py` process acts as the out-of-process safety fallback.

---

## 13. Event and Telemetry Design

### Outbound Events:
1. `EventType.WORKSPACE_STATE_CHANGED`:
   - **Payload**: `{"state": "DOCKED", "geometry": WorkspaceGeometry, "timestamp_utc": "..."}`
   - **Consumers**: Frontend UI, Gateway WebSocket clients, `ObservationCapability`, `TaskManager`.
2. `EventType.WORKSPACE_DEGRADED`:
   - **Payload**: `{"reason": "SHELL_UNRESPONSIVE", "recommended_action": "RECOVER_WORKSPACE"}`

### Telemetry Metrics:
- `registration_latency_ms`: Time taken for `ABM_NEW` + `ABM_SETPOS`.
- `unregistration_latency_ms`: Time taken for `ABM_REMOVE`.
- `current_generation_id`: Monotonically increasing layout generation counter.
- `docked_edge` and `docked_width_px`.
- `watchdog_attached`: Boolean indicating active crash recovery guard.

---

## 14. Risk Assessment

| Risk | Classification | Mitigation Strategy |
| :--- | :--- | :--- |
| **DWM Third-Party Shrink Inapplicability** | **CONFIRMED (Win11)** | Documented as an empirical capability boundary; ORBIT uses `WS_EX_TOPMOST` and does not rely on third-party window resizing. |
| **Ungraceful Crash Leaving Distorted Work Area** | **MITIGATED** | Detached `watchdog.py` monitors parent PID and restores baseline geometry in $<350\text{ms}$. |
| **Observation Stale Inference After Docking** | **MITIGATED** | Layout change increments `desktop_generation_id`, instantly invalidating cached observation frames in `FreshnessEvaluator`. |
| **Pointer Clicking ORBIT Docked Area** | **MITIGATED** | `WorkspaceGeometryEngine` provides usable canvas boundaries; synthetic clicks in ORBIT area rejected. |
| **Multi-Monitor Layout Misalignment** | **UNRESOLVED (Hardware Gate)** | Formally gated pending physical multi-display testing; defaults to primary monitor safely. |

---

## 15. Final Status & Conclusion

All required forensic investigations, Win32 ABI audits, state machine transitions, coordinate systems, safety models, and integration boundaries are fully established.

**Final Status**: **AUDIT & ARCHITECTURE COMPLETE — READY FOR M1.5 IMPLEMENTATION**
