# ORBIT Milestone M1.5: Production Workspace & AppBar Integration Audit

**Milestone**: M1.5 — Production Workspace / AppBar Integration (Audit & Architecture Phase)  
**Status**: **AUDIT COMPLETE — READY FOR IMPLEMENTATION**  
**Date**: September 6, 2026  
**Environment**: Windows 11 AMD64 (Build 26200), Python 3.13.7  
**Baseline Commit**: `ca87ef8`

---

## 1. Executive Summary

Milestone **M1.5** designs the integration of the **Production Workspace & AppBar Capability** into the ORBIT production architecture. This capability manages the desktop workspace reservation, top-level docking layout (`WS_EX_TOPMOST`), Windows Shell Application Desktop Toolbar (`SHAppBarMessage`), coordinate systems, multi-monitor display metrics, and crash-recovery watchdog guards.

This audit:
1. Performs a complete forensic analysis of **Prototype A** (`prototypes/prototype_a_workspace/`).
2. Evaluates the empirical findings of live Windows 11 Desktop Window Manager (DWM) behavior.
3. Examines 64-bit AMD64 Win32 ABI signatures, thread-affinity constraints, and handle ownership.
4. Analyzes the impact of workspace edge reservation on screen coordinate systems (`Physical Desktop`, `Virtual Screen`, `Work Area Canvas`, `Monitor Bounds`).
5. Reconciles workspace state transitions with `ObservationCapability` (generation invalidation), `PointerCapability` (target bounds verification), `KeyboardCapability` (focus preservation), `HumanTakeoverCapability`, and `EmergencySafetyCoordinator`.
6. Proposes the production architecture package `src/orbit/adapters/workspace/`, strict state machine, enhanced capability contracts, event schemas, test matrix, and phased implementation plan.

---

## 2. Frozen Boundary Verification

Prior to performing this audit, frozen prototype boundaries were verified against baseline commit `ca87ef8`:
```powershell
git diff ca87ef8 -- prototypes/prototype_a_workspace/ prototypes/prototype_b_human_takeover/ prototypes/prototype_c_keyboard/ prototypes/prototype_d_observation/
```
**Verification Result**: **0 files modified, 0 lines diff**.  
All four frozen prototypes (A, B, C, D) remain 100% untouched.

---

## 3. Mandatory Phase 1 — Forensic Prototype A Audit

### 3.1 Capability Inventory

| Component / Module | Responsibility | Input | Output | State Ownership | External Dependencies | Win32 APIs Used | Handle Ownership | Thread Affinity | Shutdown / Cleanup Responsibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `appbar_native.py` (`Win32AppBar`) | Manages Win32 Application Desktop Toolbar (AppBar) registration, positioning negotiation, and edge docking. | `hwnd`, `callback_msg`, `edge`, `target_width_ratio`, `min_width`, `max_width` | Final assigned `RECT`, `bool` success | `is_registered`, `current_edge`, `current_rect` | `ctypes`, `wintypes` | `SHAppBarMessage`, `SetWindowPos`, `GetWindowRect`, `SystemParametersInfoW`, `GetSystemMetrics`, `SetProcessDpiAwarenessContext` | Borrows window `HWND`. Does not create window handles itself. | `SHAppBarMessage` calls must originate from the thread owning the `HWND`. | Invokes `SHAppBarMessage(ABM_REMOVE)` on unregister/shutdown. |
| `appbar_native.py` (Display & DPI helpers) | Queries display resolution, monitors, DPI scaling, and desktop work area. | None | `MonitorInfo` list, `(w, h)` screen dimensions, `RECT` work area | Stateless | `ctypes`, `wintypes` | `EnumDisplayMonitors`, `GetMonitorInfoW`, `shcore.GetDpiForMonitor`, `SystemParametersInfoW(SPI_GETWORKAREA)` | Allocates and cleans callback `MONITORENUMPROC`. | Thread-safe / thread-independent. | Frees temporary ctypes callbacks. |
| `workspace_prototype.py` (`WorkspacePrototypeApp`) | Interactive Tkinter visual dashboard & testbed for docking and live telemetry. | Tkinter `root` | Visual GUI, user interactions | GUI widget state, initial work area, telemetry poll timer | `tkinter`, `subprocess`, `os`, `sys` | `GetParent`, `SetWindowPos`, `FindWindowW`, `ShowWindow`, `GetWindowRect` | Owns Tkinter root and spawned child process handles. | Main Tkinter UI thread. | Calls `appbar.unregister()`, terminates child test processes on `WM_DELETE_WINDOW`. |
| `watchdog.py` (`run_watchdog`) | Independent detached watchdog process monitoring parent PID and restoring baseline work area if parent dies abruptly. | `PID`, baseline `(left, top, right, bottom)`, `log_path` | Telemetry JSON, work area restoration | Attached process handle, baseline `RECT` | `ctypes`, `wintypes`, `kernel32`, `user32` | `OpenProcess(SYNCHRONIZE)`, `WaitForSingleObject`, `SystemParametersInfoW(SPI_SETWORKAREA)`, `CloseHandle` | Owns process `HANDLE` from `OpenProcess`. | Standalone detached process. | Calls `CloseHandle(hProcess)` and restores work area via `SPI_SETWORKAREA` if delta detected. |
| `formal_test_suite.py` | Programmatic acceptance benchmark runner executing Tests A1 through A8. | Live Windows OS environment | `formal_audit_report.json`, test verdicts | Test records, created test window classes | `platform`, `subprocess`, `time` | `RegisterClassExW`, `CreateWindowExW`, `DestroyWindow`, `UnregisterClassW`, `SHAppBarMessage`, `SetWindowPos` | Creates and destroys temporary `HWND`, window class `ATOM`, and child test processes. | Dedicated test execution thread. | Cleans up all test windows, classes, and processes in each test block. |

---

### 3.2 Windows API Forensics & AMD64 ABI Verification

Every native Windows API used in Prototype A was audited for 64-bit AMD64 calling conventions, ctypes type safety, error codes, and thread requirements:

#### 1. `shell32.SHAppBarMessage`
- **DLL**: `shell32.dll`
- **C Signature**: `UINT_PTR SHAppBarMessage(DWORD dwMessage, PAPPBARDATA pData);`
- **ctypes argtypes**: `[wintypes.DWORD, ctypes.POINTER(APPBARDATA)]`
- **ctypes restype**: `ctypes.c_uint64` (or `wintypes.UINT_PTR`)
- **Structure `APPBARDATA` Layout (AMD64 64-bit)**:
  ```c
  typedef struct _AppBarData {
      DWORD  cbSize;            // Offset  0, Size 4 bytes
      // [4 bytes padding for 8-byte alignment]
      HWND   hWnd;              // Offset  8, Size 8 bytes
      UINT   uCallbackMessage;  // Offset 16, Size 4 bytes
      UINT   uEdge;             // Offset 20, Size 4 bytes
      RECT   rc;                // Offset 24, Size 16 bytes (4x LONG)
      LPARAM lParam;            // Offset 40, Size 8 bytes
  } APPBARDATA;                 // Total Size: 48 bytes
  ```
- **Return Value & Error Handling**:
  - `ABM_NEW`: Returns non-zero `TRUE` on success; `FALSE` (0) on failure.
  - `ABM_QUERYPOS` / `ABM_SETPOS`: Returns `TRUE` / non-zero. The shell modifies `pData->rc` in-place to the agreed coordinates.
  - `ABM_REMOVE`: Returns `TRUE` (non-zero).
- **Thread / Lifetime Requirements**: Must be called on the thread that created `hWnd` and runs its message loop.
- **AMD64 ABI Verification**: `sizeof(APPBARDATA) == 48`. Explicit structure alignment verified.

#### 2. `user32.SetWindowPos`
- **DLL**: `user32.dll`
- **C Signature**: `BOOL SetWindowPos(HWND hWnd, HWND hWndInsertAfter, int X, int Y, int cx, int cy, UINT uFlags);`
- **ctypes argtypes**: `[wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]`
- **ctypes restype**: `wintypes.BOOL`
- **Flags Used**: `SWP_NOACTIVATE (0x0010) | SWP_SHOWWINDOW (0x0040) | SWP_NOZORDER (0x0004)`
- **Target Z-Order**: `HWND_TOPMOST ((HWND)-1)`
- **Error Handling**: Returns non-zero `TRUE` on success, `0` on failure (`kernel32.GetLastError()`).

#### 3. `user32.SystemParametersInfoW`
- **DLL**: `user32.dll`
- **C Signature**: `BOOL SystemParametersInfoW(UINT uiAction, UINT uiParam, PVOID pvParam, UINT fWinIni);`
- **ctypes argtypes**: `[wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]`
- **ctypes restype**: `wintypes.BOOL`
- **Actions**:
  - `SPI_GETWORKAREA (0x0030)`: `uiParam = 0`, `pvParam = &RECT`, `fWinIni = 0`. Reads primary monitor work area.
  - `SPI_SETWORKAREA (0x002F)`: `uiParam = 0`, `pvParam = &RECT`, `fWinIni = SPIF_SENDCHANGE (0x02) | SPIF_UPDATEINIFILE (0x01)`. Used strictly by watchdog for crash recovery.
- **Safety Invariant**: Production ORBIT normal docking strictly avoids calling `SPI_SETWORKAREA` directly to prevent desktop distortion.

#### 4. `user32.EnumDisplayMonitors` & `user32.GetMonitorInfoW`
- **DLL**: `user32.dll`
- **C Signatures**:
  - `BOOL EnumDisplayMonitors(HDC hdc, LPCRECT lprcClip, MONITORENUMPROC lpfnEnum, LPARAM dwData);`
  - `BOOL GetMonitorInfoW(HMONITOR hMonitor, LPMONITORINFO lpmi);`
- **Structure `MONITORINFOEXW` Layout (AMD64)**:
  `cbSize (4) + rcMonitor (16) + rcWork (16) + dwFlags (4) + szDevice (64) = 104 bytes`.
- **Error Handling**: Returns `TRUE` while enumerating. `GetMonitorInfoW` returns `TRUE` on success.

#### 5. `shcore.GetDpiForMonitor`
- **DLL**: `shcore.dll`
- **C Signature**: `HRESULT GetDpiForMonitor(HMONITOR hmonitor, int dpiType, UINT *dpiX, UINT *dpiY);`
- **ctypes argtypes**: `[wintypes.HMONITOR, ctypes.c_int, ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT)]`
- **ctypes restype**: `ctypes.c_long` (`HRESULT`, `S_OK == 0`)
- **Fallback**: If `shcore.dll` is absent or call fails, falls back to `96` DPI ($1.0\times$ scale).

#### 6. `user32.SetProcessDpiAwarenessContext`
- **DLL**: `user32.dll`
- **C Signature**: `BOOL SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT value);`
- **Value**: `DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 ((DPI_AWARENESS_CONTEXT)-4)`
- **ctypes argtypes**: `[ctypes.c_void_p]`
- **ctypes restype**: `wintypes.BOOL`

#### 7. `kernel32.OpenProcess` & `kernel32.WaitForSingleObject`
- **DLL**: `kernel32.dll`
- **C Signatures**:
  - `HANDLE OpenProcess(DWORD dwDesiredAccess, BOOL bInheritHandle, DWORD dwProcessId);`
  - `DWORD WaitForSingleObject(HANDLE hHandle, DWORD dwMilliseconds);`
  - `BOOL CloseHandle(HANDLE hObject);`
- **Desired Access**: `SYNCHRONIZE (0x00100000) | PROCESS_QUERY_LIMITED_INFORMATION (0x1000)`
- **Error Handling**: `OpenProcess` returns `NULL` on failure. `WaitForSingleObject` returns `WAIT_OBJECT_0 (0x00000000)` when the target process terminates.

---

### 3.3 AppBar Lifecycle Analysis

The complete state progression of an Application Desktop Toolbar under Windows 11:

```
                  ┌──────────────────────┐
                  │    UNINITIALIZED     │
                  └──────────┬───────────┘
                             │ initialize()
                             ▼
                  ┌──────────────────────┐
                  │        READY         │◄─────────────────────────┐
                  │      (FLOATING)      │                          │
                  └──────────┬───────────┘                          │
                             │ reserve_workspace(edge, size)        │
                             ▼                                      │
                  ┌──────────────────────┐                          │
                  │     REGISTERING      │                          │
                  │ (ABM_NEW/QUERY/SET)  │                          │
                  └──────────┬───────────┘                          │
                             │ Shell Agrees / SetWindowPos          │
                             ▼                                      │
                  ┌──────────────────────┐                          │
                  │        DOCKED        │                          │
                  │   (ACTIVE APPBAR)    │                          │
                  └──────────┬───────────┘                          │
                             │ release_workspace()                  │
                             ▼                                      │
                  ┌──────────────────────┐                          │
                  │      RELEASING       │                          │
                  │     (ABM_REMOVE)     │──────────────────────────┘
                  └──────────┬───────────┘
                             │ Native Failure / Exception
                             ▼
                  ┌──────────────────────┐
                  │   FAILED / DEGRADED  │
                  └──────────────────────┘
```

#### Investigation of Abnormal States & Edge Cases:

1. **Registration Failure (`ABM_NEW` returns 0)**:
   - *Cause*: Shell (Explorer.exe) is restarting, busy, or HWND is invalid.
   - *Handling*: Fail closed. Mark state as `FAILED`, do not claim workspace is reserved, log diagnostic reason, keep window in floating mode.
2. **Duplicate Registration**:
   - *Cause*: Calling `reserve_workspace()` when already in `DOCKED` state.
   - *Handling*: Idempotent. If the requested edge and size match current geometry, return immediately with success; if edge/size changed, perform atomic reconfiguration via `ABM_QUERYPOS` & `ABM_SETPOS` without unregistering.
3. **Explorer.exe Crash / Restart**:
   - *Cause*: Windows Shell restarts during an active session (`WM_APPBAR_CALLBACK` or `TaskbarCreated` message emitted).
   - *Handling*: The shell loses all previous AppBar registrations. The adapter must listen for `RegisterWindowMessageW("TaskbarCreated")` and automatically re-register the AppBar (`ABM_NEW` + `ABM_SETPOS`).
4. **Unexpected Window Destruction**:
   - *Cause*: External process terminates window, or UI crashes.
   - *Handling*: The background watchdog detects process termination and verifies baseline work area. Adapter unhooks cleanly on `WM_DESTROY`.
5. **Release Failure (`ABM_REMOVE` error)**:
   - *Cause*: Shell unresponsive.
   - *Handling*: Transition to `DEGRADED`, issue warning event, destroy window handle cleanly, let watchdog ensure desktop work area restoration.

---

### 3.4 Handle & Resource Ownership

| OS Resource | Creator | Owner | Transfer Rules | Cleanup Function | Cleanup Timing | Failure Cleanup Behavior |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Window HWND** | `CreateWindowExW` | Adapter UI Window Manager | Non-transferable (Thread-bound) | `user32.DestroyWindow(hwnd)` | Adapter `stop()` or window close | Destroyed in `finally:` block; verified via `IsWindow(hwnd) == 0`. |
| **Window Class Atom** | `RegisterClassExW` | Process Instance (`HINSTANCE`) | Process-wide | `user32.UnregisterClassW(name, hInst)` | Adapter shutdown | Unregistered in `finally:` block. |
| **AppBar Registration** | `SHAppBarMessage(ABM_NEW)` | Windows Shell (`explorer.exe`) bound to `HWND` | Non-transferable | `SHAppBarMessage(ABM_REMOVE, &abd)` | Before window destruction on undock/stop | Watchdog verifies work area if ungraceful termination occurs. |
| **Watchdog Process Handle** | `kernel32.OpenProcess` | Watchdog Process | Watchdog-internal | `kernel32.CloseHandle(hProcess)` | On target PID termination | Closed in `finally:` block in `watchdog.py`. |
| **Monitor Enum Callback** | `MONITORENUMPROC` | Monitor query function | Temporary | Garbage collected by Python runtime | End of `enum_monitors()` | Ctypes callback reference held until function returns. |

---

### 3.5 Coordinate System Analysis

Reserving a screen edge (e.g. Right $25\% = 720\text{px}$ on a $2880 \times 1800$ display) creates a multi-layered coordinate hierarchy:

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                 PHYSICAL DISPLAY (2880 x 1800)                          │
├────────────────────────────────────────────────────────────┬────────────────────────────┤
│                                                            │                            │
│                 USABLE WORKSPACE CANVAS                    │     ORBIT DOCKED APPBAR    │
│              (RECT: 0, 0, 2160, 1800 - Width 2160px)       │  (RECT: 2160, 0, 2880,1800 │
│                                                            │       Width: 720px)        │
│                                                            │                            │
│   • Target coordinates for automated desktop tasks         │   • ORBIT UI container     │
│   • Normal third-party application canvas                  │   • System telemetry       │
│   • Observation Region of Interest (ROI) default           │   • Interaction controls   │
│                                                            │   • Protected from clicks  │
│                                                            │                            │
└────────────────────────────────────────────────────────────┴────────────────────────────┘
```

#### Reconciled Coordinate Layers:

1. **Physical Desktop Coordinates**: The full hardware display frame buffer (e.g. $[0, 2880) \times [0, 1800)$).
2. **Virtual Desktop Coordinates**: The multi-monitor coordinate bounding box (can have negative origins if secondary monitors are to the left/above).
3. **Usable Work Area Canvas**: The area available for target desktop applications. When docked on the right, this is $[0, 2160) \times [0, 1800)$.
4. **Docked Reserved Area**: The bounding box occupied by the ORBIT AppBar (e.g. $[2160, 2880) \times [0, 1800)$).
5. **Logical DPI Coordinates**: Scaled layout coordinates ($1440 \times 900\text{ pt}$ at $2.0\times$ scaling).

#### Required Production Behaviors:
1. **Shared Workspace Geometry Model**: `WorkspaceGeometry` exposing `physical_bounds`, `work_area_bounds`, `docked_bounds`, `docked_edge`, and `is_docked`.
2. **Workspace Generation Tracking (`workspace_generation_id`)**:
   - Any layout transition (`DOCKED` $\to$ `FLOATING`, `FLOATING` $\to$ `DOCKED`, or resize) **increments the global `desktop_generation_id`**.
3. **Observation Freshness Invalidation**:
   - Incremented generation immediately flags pre-docking observation frames as `GENERATION_MISMATCH` in `FreshnessEvaluator`, preventing stale visual reasoning.
4. **Pointer Target Safety Boundary**:
   - Pointer movement / click transactions validate coordinates against `WorkspaceGeometry`. By default, synthetic clicks inside the docked ORBIT AppBar area are rejected with `CLICK_TARGET_INSIDE_ORBIT_RESERVATION` unless explicitly flagged as self-interaction.

---

### 3.6 Capability Interaction Analysis

#### 1. Observation Capability
- **Screenshot Bounds**: Full-screen captures continue to capture the physical desktop ($2880 \times 1800$).
- **Region of Interest (ROI)**: When ORBIT is docked, `ObservationCapability` can provide automatic cropping to the `Usable Work Area Canvas` $[0, 2160) \times [0, 1800)$, preventing the LLM/agent from perceiving ORBIT's own UI as part of the target application.
- **Freshness Invalidation**: Reconfiguring the workspace increments `desktop_generation_id`, cleanly invalidating stale snapshots.

#### 2. Pointer Capability
- **In-flight Transactions**: If a workspace resize or docking transition occurs during an active pointer transaction, the generation check rejects post-dispatch verification or pauses movement.
- **Edge Collision**: Automated pointer movements are constrained to the usable canvas unless target window is explicitly identified.

#### 3. Keyboard Capability
- **Focus Integrity**: Docking and undocking use `SWP_NOACTIVATE` so that the currently focused target user application does not lose focus or modifier states.

#### 4. Human Takeover Capability
- **Non-disruptive Preemption**: When human takeover triggers, the ORBIT window remains visible and docked; it does **not** undock or shift position, avoiding sudden screen reshuffling while the human operates the PC.
- **Preemption of Workspace Commands**: Any in-flight workspace reconfiguration command (`reserve_workspace`, `release_workspace`) is cancelled cleanly.

#### 5. Emergency Safety Coordination
- **Fail-Closed Shutdown**: During `emergency_stop_all()` or runtime shutdown, the workspace adapter cleanly calls `ABM_REMOVE` to release the shell reservation and terminates the watchdog process.
- **Watchdog Backup**: If the entire Python process is hard-killed (e.g. `SIGKILL`), the independent `watchdog.py` process detects PID termination within $350\text{ms}$ and restores baseline work area geometry.

---

## 4. Mandatory Phase 2 — Production Architecture Reconciliation

### Inspection of Existing Production Layers

1. `src/orbit/contracts/capabilities.py`:
   - Contains `WorkspaceCapability(Protocol)` and `CapabilityType.WORKSPACE`.
   - Existing protocol defines: `register_appbar(edge: str, size: int) -> bool`, `unregister_appbar() -> bool`, `get_work_area() -> BoundingBox`, `get_health() -> CapabilityHealth`.
   - *Audit Finding*: The contract needs extension in M1.5 to support structured `WorkspaceGeometry`, `get_workspace_generation() -> int`, `recover_workspace() -> bool`, and typed edge enums (`DockEdge`).
2. `src/orbit/contracts/events.py`:
   - Outbound WebSocket events currently lack typed workspace lifecycle events.
   - *Requirement*: Propose `EventType.WORKSPACE_STATE_CHANGED` and `WorkspaceStatePayload`.
3. `src/orbit/contracts/commands.py`:
   - Needs inbound command types: `RESERVE_WORKSPACE`, `RELEASE_WORKSPACE`, `RECONFIGURE_WORKSPACE`.
4. `src/orbit/runtime/orchestrator.py`:
   - Already instantiates and exposes `self.workspace` via `CapabilityRegistry`.
   - Needs to wire generation invalidation and pass workspace geometry to task planning.
5. `src/orbit/adapters/production/production_workspace.py`:
   - Currently a stub raising `WorkspaceError("Production workspace live AppBar is deferred to Milestone M5")`.
   - Will be replaced with the production adapter bridging to `src/orbit/adapters/workspace/`.

---

## 5. Mandatory Phase 3 — Proposed Production Design

### Package Structure: `src/orbit/adapters/workspace/`

```
src/orbit/adapters/workspace/
    ├── __init__.py           # Package exports (ProductionWorkspaceAdapter, models, enums)
    ├── types.py              # Data models: DockEdge, WorkspaceGeometry, DisplayMonitorInfo
    ├── abi.py                # Win32 AMD64 C-types structures, APPBARDATA, RECT, signatures
    ├── appbar.py             # Low-level Win32 SHAppBarMessage & SetWindowPos driver
    ├── state.py              # WorkspaceStateManager & strict state machine
    ├── geometry.py           # Geometry calculation, DPI scaling, and usable canvas calculator
    ├── watchdog.py           # Watchdog launcher & crash recovery coordinator
    ├── telemetry.py          # Workspace metrics, transition timing, generation tracking
    └── adapter.py            # ProductionWorkspaceAdapter implementing WorkspaceCapability
```

### Component Responsibilities & Interfaces:

1. `abi.py`:
   - Defines exact 64-bit AMD64 `ctypes.Structure` classes (`RECT`, `APPBARDATA`, `MONITORINFOEXW`).
   - Declares explicit `argtypes` and `restype` for `SHAppBarMessage`, `SetWindowPos`, `SystemParametersInfoW`, `EnumDisplayMonitors`, `GetDpiForMonitor`, `SetProcessDpiAwarenessContext`.
   - Provides ABI validation function `validate_workspace_abi() -> bool`.
2. `types.py`:
   - `DockEdge(str, Enum)`: `LEFT = "LEFT"`, `RIGHT = "RIGHT"`, `TOP = "TOP"`, `BOTTOM = "BOTTOM"`, `NONE = "NONE"`.
   - `WorkspaceState(str, Enum)`: `UNINITIALIZED`, `READY_FLOATING`, `REGISTERING`, `DOCKED`, `RELEASING`, `DEGRADED`, `FAILED`, `STOPPED`.
   - `WorkspaceGeometry(BaseModel)`: `physical_display: BoundingBox`, `work_area: BoundingBox`, `docked_bounds: Optional[BoundingBox]`, `dock_edge: DockEdge`, `is_docked: bool`, `generation_id: int`.
3. `appbar.py` (`NativeAppBarDriver`):
   - Encapsulates `SHAppBarMessage(ABM_NEW)`, `ABM_QUERYPOS`, `ABM_SETPOS`, `ABM_REMOVE`.
   - Dispatches `SetWindowPos(HWND_TOPMOST, SWP_NOACTIVATE | SWP_SHOWWINDOW)`.
   - Handles Win32 message registration (`RegisterWindowMessageW("TaskbarCreated")`).
4. `state.py` (`WorkspaceStateManager`):
   - Enforces valid state transitions and rejects illegal transitions.
   - Manages atomic state locks and generation ID counter (`generation_id`).
5. `geometry.py` (`WorkspaceGeometryEngine`):
   - Computes DPI-aware 25% edge clamping (380px–720px).
   - Calculates usable application canvas dimensions.
   - Evaluates multi-monitor placement if multiple displays are present.
6. `watchdog.py` (`WorkspaceWatchdogCoordinator`):
   - Spawns detached `watchdog.py` process monitoring parent PID.
   - Passes baseline work area parameters via command line.
   - Cleans up watchdog upon graceful shutdown.
7. `adapter.py` (`ProductionWorkspaceAdapter`):
   - Inherits `BaseCapabilityAdapter` and implements `WorkspaceCapability`.
   - Orchestrates driver, state machine, geometry engine, and watchdog.
   - Exposes truthful health telemetry.

---

## 6. Mandatory Phase 4 — State Machine Design

### Minimal Correct State Model:

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

### Transition Table:

| Source State | Target State | Trigger Event | Preconditions | Side Effects | Cancellation Behavior |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `UNINITIALIZED` | `READY_FLOATING` | `initialize()` | Valid AMD64 ABI | Captures baseline work area; spawns watchdog. | Synchronous; non-cancellable |
| `READY_FLOATING` | `REGISTERING` | `reserve_workspace(edge, size)` | Target HWND valid | Prepares `APPBARDATA`; enters registration. | Aborts before `ABM_NEW` if cancelled. |
| `REGISTERING` | `DOCKED` | Shell agreement | `ABM_NEW` & `ABM_SETPOS` ok | Positions window (`SetWindowPos`); increments `generation_id`; publishes event. | Atomic once shell commits. |
| `REGISTERING` | `FAILED` | Shell rejection | `ABM_NEW` returns 0 | Logs error; records health failure. | Non-cancellable. |
| `DOCKED` | `RELEASING` | `release_workspace()` | Currently DOCKED | Prepares `ABM_REMOVE`. | Non-cancellable. |
| `RELEASING` | `READY_FLOATING` | Shell remove ok | `ABM_REMOVE` succeeds | Restores floating rect; increments `generation_id`. | Non-cancellable. |
| `DOCKED` | `DEGRADED` | Explorer crash / hook loss | Shell signal lost | Flags degraded health; schedules re-registration. | Non-cancellable. |
| `DEGRADED` | `READY_FLOATING` | `recover_workspace()` | Reset token verified | Resets work area; reinitializes baseline. | Non-cancellable. |
| Any (except STOPPED) | `STOPPED` | `shutdown()` | Process shutdown | Unregisters AppBar; destroys window; cleans watchdog. | Non-cancellable. |

### Illegal Transitions (Strictly Rejected):
- `UNINITIALIZED` $\to$ `DOCKED` (Must initialize and capture baseline first).
- `DOCKED` $\to$ `REGISTERING` (Must either reconfigure or release first).
- `STOPPED` $\to$ `DOCKED` (Terminal state).

---

## 7. Mandatory Phase 5 — Contract Design

### Proposed Enhanced `WorkspaceCapability` Protocol:

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

---

## 8. Mandatory Phase 6 — Event and Telemetry Design

### Outbound Events:

1. `EventType.WORKSPACE_STATE_CHANGED`:
   - **Producer**: `ProductionWorkspaceAdapter`
   - **Payload**:
     ```json
     {
       "state": "DOCKED",
       "previous_state": "READY_FLOATING",
       "geometry": {
         "physical_display": {"left": 0, "top": 0, "width": 2880, "height": 1800},
         "work_area": {"left": 0, "top": 0, "width": 2160, "height": 1800},
         "docked_bounds": {"left": 2160, "top": 0, "width": 720, "height": 1800},
         "dock_edge": "RIGHT",
         "is_docked": true,
         "generation_id": 4
       },
       "timestamp_utc": "2026-09-06T02:00:00Z"
     }
     ```
   - **Consumers**: Frontend Gateway, `ObservationCapability` (generation invalidation), `TaskManager`.

2. `EventType.WORKSPACE_DEGRADED`:
   - **Producer**: `ProductionWorkspaceAdapter`
   - **Payload**: `{"reason": "EXPLORER_SHELL_RESTART", "recommended_action": "RECOVER_WORKSPACE"}`

---

## 9. Conclusion & Readiness

The forensic audit of Prototype A and architectural reconciliation confirm:
1. **Zero Blocker / Zero Architectural Contradiction**: All Win32 APIs, 64-bit ABI structures, thread-affinity boundaries, and coordinate interactions are fully mapped.
2. **Safety Invariants Preserved**: Normal operations avoid invasive `SPI_SETWORKAREA`; watchdog ensures $<350\text{ms}$ crash restoration.
3. **Observation & Pointer Alignment**: Workspace generation ID cleanly integrates with existing freshness and target validation mechanisms.

**Final Status**: **AUDIT & ARCHITECTURE COMPLETE — READY FOR M1.5 IMPLEMENTATION**
