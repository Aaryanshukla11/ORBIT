# ORBIT Milestone M1.5: Production Workspace & AppBar Implementation Plan

**Milestone**: M1.5 — Production Workspace / AppBar Integration  
**Status**: **APPROVED IMPLEMENTATION PLAN**  
**Date**: September 6, 2026  
**Target Subsystem**: `src/orbit/adapters/workspace/`

---

## 1. Architectural Strategy & Principles

Milestone **M1.5** integrates the **Production Workspace & AppBar Capability** into ORBIT.

### Core Architectural Principles:
1. **Contract-Driven**: Production contracts in `src/orbit/contracts/` define the boundaries. No ad-hoc untyped dictionaries.
2. **AMD64 ABI Safety**: Explicit 64-bit ctypes structures (`APPBARDATA`, `RECT`, `MONITORINFOEXW`) with verified offsets and argument types.
3. **Fail-Closed State Machine**: Strict state transitions (`UNINITIALIZED`, `READY_FLOATING`, `REGISTERING`, `DOCKED`, `RELEASING`, `DEGRADED`, `FAILED`, `STOPPED`).
4. **Desktop Generation Parity**: Any workspace reconfiguration increments the global `desktop_generation_id`, cleanly invalidating observation frame caches and protecting pointer transactions.
5. **Fail-Safe Crash Recovery**: An independent detached watchdog process monitors parent PID and guarantees work area restoration within $<350\text{ms}$ upon ungraceful termination.
6. **Frozen Boundary Invariant**: Zero modifications to frozen prototype directories (`prototypes/prototype_a_workspace/`, `prototype_b_human_takeover/`, `prototype_c_keyboard/`, `prototype_d_observation/`).

---

## 2. Staged Implementation Breakdown

```
┌────────────────────────────────────────────────────────────────────────┐
│                        M1.5 IMPLEMENTATION STAGES                      │
├────────────────────────────────────────────────────────────────────────┤
│  M1.5A: Contracts, Data Models, State Machine & ABI Gate               │
│         ↓                                                              │
│  M1.5B: Native AppBar Driver & Window Positioning                      │
│         ↓                                                              │
│  M1.5C: Workspace Geometry Engine & DPI Awareness                     │
│         ↓                                                              │
│  M1.5D: Watchdog Crash Recovery & Safety Integration                   │
│         ↓                                                              │
│  M1.5E: Production Workspace Adapter & Orchestrator Integration        │
│         ↓                                                              │
│  M1.5F: Full Integration Testing, Live Validation & Completion Report  │
└────────────────────────────────────────────────────────────────────────┘
```

---

### Stage M1.5A: Contracts, Data Models, State Machine & ABI Gate

#### Objectives:
- Extend `WorkspaceCapability` protocol in `src/orbit/contracts/capabilities.py`.
- Define data models (`DockEdge`, `WorkspaceState`, `WorkspaceGeometry`, `DisplayMonitorInfo`).
- Implement 64-bit AMD64 ABI definitions and validation gate (`src/orbit/adapters/workspace/abi.py`).
- Implement strict state machine (`src/orbit/adapters/workspace/state.py`).

#### Files to Create:
- `src/orbit/adapters/workspace/__init__.py`
- `src/orbit/adapters/workspace/types.py`
- `src/orbit/adapters/workspace/abi.py`
- `src/orbit/adapters/workspace/state.py`
- `tests/unit/test_workspace_abi.py`
- `tests/unit/test_workspace_state_machine.py`

#### Files to Modify:
- `src/orbit/contracts/capabilities.py` (Enhance `WorkspaceCapability` protocol and models)
- `src/orbit/contracts/events.py` (Add `WORKSPACE_STATE_CHANGED` event type and payload)
- `src/orbit/contracts/commands.py` (Add `RESERVE_WORKSPACE`, `RELEASE_WORKSPACE` command payloads)

#### Validation Gate:
- ABI structure sizes and offsets verified on AMD64.
- 100% of state machine unit tests pass, confirming illegal transitions are rejected.

---

### Stage M1.5B: Native AppBar Driver & Window Positioning

#### Objectives:
- Implement `NativeAppBarDriver` encapsulating `SHAppBarMessage(ABM_NEW, ABM_QUERYPOS, ABM_SETPOS, ABM_REMOVE)` and `SetWindowPos(HWND_TOPMOST)`.
- Implement thread-safe Win32 message loop registration and shell notification handling (`RegisterWindowMessageW("TaskbarCreated")`).

#### Files to Create:
- `src/orbit/adapters/workspace/appbar.py`
- `tests/unit/test_workspace_appbar.py`

#### Validation Gate:
- Native AppBar driver executes `ABM_NEW` / `ABM_SETPOS` / `ABM_REMOVE` cleanly against test windows.
- Zero handle leaks verified on cleanup.

---

### Stage M1.5C: Workspace Geometry Engine & DPI Awareness

#### Objectives:
- Implement `WorkspaceGeometryEngine` calculating 25% edge reservation, minimum (380px) and maximum (720px) clamping.
- Implement Per-Monitor DPI Awareness v2 scaling calculations and multi-monitor enumeration (`EnumDisplayMonitors`, `GetDpiForMonitor`).
- Calculate exact `usable_work_area` canvas dimensions.

#### Files to Create:
- `src/orbit/adapters/workspace/geometry.py`
- `tests/unit/test_workspace_geometry.py`

#### Validation Gate:
- Geometry arithmetic produces exact pixel bounds for Right and Left edges on $2880 \times 1800$ and $1920 \times 1080$ displays.
- Clamping boundaries strictly enforced.

---

### Stage M1.5D: Watchdog Crash Recovery & Safety Integration

#### Objectives:
- Implement `WorkspaceWatchdogCoordinator` managing detached `watchdog.py` process lifecycle.
- Guarantee that upon abnormal process termination, baseline desktop work area is restored in $<350\text{ms}$.
- Implement `emergency_stop_all()` safety integration for workspace cleanup.

#### Files to Create:
- `src/orbit/adapters/workspace/watchdog.py`
- `tests/unit/test_workspace_watchdog.py`

#### Validation Gate:
- Simulated child process hard-kill verifies that watchdog restores baseline work area with zero lingering distortion.

---

### Stage M1.5E: Production Workspace Adapter & Orchestrator Integration

#### Objectives:
- Implement `ProductionWorkspaceAdapter` in `src/orbit/adapters/workspace/adapter.py`.
- Re-export `ProductionWorkspaceAdapter` in `src/orbit/adapters/production/production_workspace.py`.
- Wire generation invalidation into `OrbitOrchestrator` and `ObservationCapability`.
- Expose truthful health telemetry.

#### Files to Create:
- `src/orbit/adapters/workspace/adapter.py`
- `src/orbit/adapters/workspace/telemetry.py`
- `tests/integration/test_workspace_runtime_integration.py`

#### Files to Modify:
- `src/orbit/adapters/production/production_workspace.py`
- `src/orbit/runtime/orchestrator.py`

#### Validation Gate:
- Full integration tests pass: docking increments generation ID, invalidates observation cache, and publishes WebSocket events.

---

### Stage M1.5F: Full Integration Testing, Live Validation & Completion Report

#### Objectives:
- Execute full ORBIT test suite (`pytest -v`).
- Execute all 5 prototype regression suites (A, B, C, D, E).
- Execute controlled live Windows 11 validation script.
- Verify frozen prototype diff against `ca87ef8` (0 lines diff).
- Create `docs/M1_5_WORKSPACE_COMPLETION_REPORT.md`.

#### Validation Gate:
- 100% test pass rate across all suites.
- 0 files modified in frozen prototype directories.

---

## 3. Strict Stop Condition

The authorized scope for this phase is **AUDIT + ARCHITECTURE + IMPLEMENTATION PLAN ONLY**.

Do NOT proceed into source code modifications or implementation until explicitly authorized.
