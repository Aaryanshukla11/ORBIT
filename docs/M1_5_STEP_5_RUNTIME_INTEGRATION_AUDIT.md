# ORBIT Milestone M1.5 Step 5 — Runtime Integration & Production Adapter Audit

**Milestone**: M1.5 — Production Workspace / AppBar Integration  
**Step**: Step 5 — Full Production Workspace Adapter & Runtime Integration  
**Status**: **PRE-IMPLEMENTATION AUDIT**  
**Date**: September 6, 2026  
**Host Environment**: Windows 11 CoreSingleLanguage AMD64 (Build 10.0.26200), Python 3.13.7  
**Baseline Frozen Commit**: `ca87ef8`

---

## 1. Executive Summary

Steps 1 through 4 of Milestone M1.5 established the foundational types, Win32 AMD64 ABI definitions, native AppBar registration driver, window positioning gateway, multi-monitor geometry coordinator, per-monitor DPI engine, and active watchdog resilience layer.

However, these components currently exist as modular infrastructure blocks. The production adapter boundary in `src/orbit/adapters/production/production_workspace.py` is an unintegrated stub.

The objective of **Step 5** is to build the comprehensive **`ProductionWorkspaceAdapter`** under `src/orbit/adapters/workspace/adapter.py`, integrate it into `CapabilityRegistry`, `CapabilityFactory`, and `OrbitOrchestrator`, wire the `WorkspaceCapability` protocol, coordinate generation invalidation across Observation and Pointer subsystems, and establish fail-closed shutdown and human takeover handling.

---

## 2. Forensic Analysis of Existing Architecture

### 2.1 Current Workspace Components (`src/orbit/adapters/workspace/`)
```text
src/orbit/adapters/workspace/
├── types.py       - DockEdge, WorkspaceState, DisplayMonitorInfo, WorkspaceGeometry, WorkspaceHealthDetails
├── abi.py         - RECT, APPBARDATA, MONITORINFOEXW, Win32 constants, validate_workspace_abi()
├── window.py      - NativeWorkspaceWindow, Win32WindowGateway (fail-closed HWND & WNDPROC lifecycle)
├── appbar.py      - NativeAppBarDriver, Win32ShellGateway (transactional ABM lifecycle & rollback)
├── state.py       - WorkspaceStateManager (thread-safe transitions & authoritative desktop generation)
├── telemetry.py   - WorkspaceTelemetryRecorder (atomic transition & operation metrics)
├── geometry.py    - WorkspaceGeometryCoordinator, Win32TopologyGateway, CoordinateValidationResult
└── watchdog.py    - WorkspaceWatchdog, WatchdogNativeGateway, WorkspaceProbeResult, WorkspaceWatchdogPolicy
```

### 2.2 Existing Capability Interfaces (`src/orbit/contracts/capabilities.py`)
`WorkspaceCapability` currently specifies:
```python
@runtime_checkable
class WorkspaceCapability(Protocol):
    async def register_appbar(self, edge: str, size: int) -> bool: ...
    async def unregister_appbar(self) -> bool: ...
    async def get_work_area(self) -> BoundingBox: ...
    async def get_health(self) -> CapabilityHealth: ...
```
To enable rich runtime orchestration and coordinate safety, `ProductionWorkspaceAdapter` will implement these core methods while also providing typed access to `get_geometry()`, `get_workspace_state()`, `validate_target_coordinate()`, `start_watchdog()`, and `stop_watchdog()`.

### 2.3 Existing Adapter Lifecycle Conventions (`BaseCapabilityAdapter`)
All production adapters in ORBIT inherit from `BaseCapabilityAdapter`:
- Discrete lifecycle states: `UNINITIALIZED` $\to$ `INITIALIZING` $\to$ `READY` $\to$ `STOPPED` (or `DEGRADED`/`FAILED`).
- Template methods: `async _on_initialize()` and `async _on_shutdown()`.
- Common health evaluation: `async get_health() -> CapabilityHealth`.
- Exception hierarchy: `CapabilityInitializationError`, `CapabilityUnavailableError`, `WorkspaceError`.

---

## 3. Runtime Lifecycle Flows & Ownership Boundaries

### 3.1 Runtime Startup Flow (`OrbitOrchestrator.initialize()`)
```text
OrbitOrchestrator.initialize()
               │
               ▼
   CapabilityRegistry.initialize_all()
               │
               ▼
   ProductionWorkspaceAdapter._on_initialize()
               │
   ┌───────────┴────────────────────────────────────────┐
   │ 1. Validate Win32 AMD64 ABI Gate                  │
   │ 2. Instantiate StateManager & Telemetry            │
   │ 3. Instantiate GeometryCoordinator                 │
   │ 4. Initialize Native Window & AppBar Driver        │
   │ 5. Register AppBar (if configured) or READY_FLOAT  │
   │ 6. Instantiate & Start WorkspaceWatchdog           │
   │ 7. Expose Ready Geometry & Active Generation       │
   └────────────────────────────────────────────────────┘
               │
               ▼
   Capability marked READY in Registry
               │
               ▼
   Orchestrator transitions SystemState -> IDLE
```

### 3.2 Runtime Shutdown Flow (`OrbitOrchestrator.shutdown()`)
```text
OrbitOrchestrator.shutdown()
               │
               ▼
   CapabilityRegistry.shutdown_all()
               │
               ▼
   ProductionWorkspaceAdapter._on_shutdown()
               │
   ┌───────────┴────────────────────────────────────────┐
   │ 1. Stop WorkspaceWatchdog gracefully               │
   │ 2. Unregister AppBar via ABM_REMOVE                │
   │ 3. Destroy Native Window HWND & Unregister Class   │
   │ 4. Transition StateManager to STOPPED              │
   │ 5. Increment desktop_generation_id (Invalidate)    │
   └────────────────────────────────────────────────────┘
```

### 3.3 Human Takeover Flow (M1.4 Coordination)
When `HumanTakeoverCapability` signals `HUMAN_TAKEOVER_ACTIVE`:
1. `OrbitOrchestrator.handle_human_takeover()` runs emergency safety stop.
2. `WorkspaceWatchdog` checks `is_takeover_active()` and suppresses autonomous disruptive window repositioning/AppBar operations.
3. When takeover is released via `release_takeover()`, normal watchdog recovery resumes.

---

## 4. Capability Coordination Touchpoints

### 4.1 Observation Coordination
- `ProductionObservationAdapter.capture_snapshot()` stamps `generation_id = current_generation`.
- When workspace docks or releases, `WorkspaceStateManager` increments `desktop_generation_id`.
- Freshness checks in `FreshnessEvaluator` fail with `GENERATION_MISMATCH` for any observation captured prior to the workspace transition.

### 4.2 Pointer Coordination
- `ProductionPointerAdapter` and `MovementExecutor` validate target coordinates against `VirtualDesktopMetrics`.
- When workspace docks, the geometry coordinator validates that coordinates targeting third-party applications do not collide with `docked_bounds` (`RESERVED_WORKSPACE_COLLISION`).
- If an action plan was generated under an obsolete generation, pre-dispatch validation rejects it fail-closed with `STALE_COORDINATE_CONTEXT`.

---

## 5. Implementation Strategy

1. **Implement `ProductionWorkspaceAdapter` (`src/orbit/adapters/workspace/adapter.py`)**:
   - Encapsulates `WorkspaceStateManager`, `NativeAppBarDriver`, `WorkspaceGeometryCoordinator`, `WorkspaceWatchdog`, `WorkspaceTelemetryRecorder`.
   - Implements `register_appbar()`, `unregister_appbar()`, `get_work_area()`, `get_health()`, `get_geometry()`, `validate_coordinate()`, `recover_workspace()`.
2. **Update Production Adapter Exports & Factory**:
   - `src/orbit/adapters/production/production_workspace.py` re-exports `ProductionWorkspaceAdapter`.
   - `src/orbit/adapters/factory.py` wires `ProductionWorkspaceAdapter` for `CapabilityType.WORKSPACE`.
   - `src/orbit/adapters/workspace/__init__.py` exports `ProductionWorkspaceAdapter`.
3. **Orchestrator & Capability Integration**:
   - Ensure `OrbitOrchestrator` wires `ProductionWorkspaceAdapter` into health reporting, human takeover callbacks, and action validation.
4. **Comprehensive Unit & Integration Tests**:
   - `tests/unit/test_workspace_adapter.py`: Adapter lifecycle, initialization, dock/undock, watchdog management, health reports.
   - `tests/integration/test_workspace_runtime_integration.py`: Factory instantiation, registry lifecycle, orchestrator startup/shutdown, observation/pointer coordination.
5. **Full Regression Validation**:
   - Pytest suite
   - 5 Prototype test suites
   - Frozen boundary diff verification
