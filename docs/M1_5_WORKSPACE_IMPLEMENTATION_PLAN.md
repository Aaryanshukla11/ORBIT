# ORBIT Milestone M1.5: Production Workspace & AppBar Implementation Plan

**Milestone**: M1.5 — Production Workspace / AppBar Integration  
**Phase**: Phase A — Implementation Plan  
**Status**: **APPROVED IMPLEMENTATION PLAN**  
**Date**: September 6, 2026  
**Target Subsystem**: `src/orbit/adapters/workspace/`

---

## 1. Architectural Strategy & Overview

Milestone **M1.5** integrates the **Production Workspace & AppBar Capability** into ORBIT under `src/orbit/adapters/workspace/`.

### Core Engineering Principles:
1. **Contract-Driven Boundaries**: Full integration with `src/orbit/contracts/capabilities.py`, `events.py`, and `commands.py`.
2. **AMD64 ABI Correctness**: Verified 64-bit ctypes structures (`APPBARDATA` 48 bytes, `RECT` 16 bytes).
3. **Fail-Closed State Machine**: Strict lifecycle state transitions with zero illegal bypasses.
4. **Desktop Generation Parity**: Layout changes increment `desktop_generation_id`, invalidating observation cache in `FreshnessEvaluator`.
5. **Watchdog Guard**: Independent detached watchdog process ensuring $<350\text{ms}$ desktop restoration upon ungraceful crash.
6. **Frozen Boundary Invariant**: Zero modifications to frozen prototype directories.

---

## 2. Atomic Implementation Steps

### STEP 1: Contracts, Data Models, State Machine & ABI Gate

- **Goal**: Establish the core data types, 64-bit AMD64 ABI definitions with validation gate, enhanced `WorkspaceCapability` protocol, and strict state machine.
- **Files**:
  - `src/orbit/adapters/workspace/__init__.py` [NEW]
  - `src/orbit/adapters/workspace/types.py` [NEW]
  - `src/orbit/adapters/workspace/abi.py` [NEW]
  - `src/orbit/adapters/workspace/state.py` [NEW]
  - `src/orbit/contracts/capabilities.py` [MODIFY - Enhance WorkspaceCapability protocol & models]
  - `src/orbit/contracts/events.py` [MODIFY - Add WORKSPACE_STATE_CHANGED event & payload]
  - `src/orbit/contracts/commands.py` [MODIFY - Add RESERVE_WORKSPACE, RELEASE_WORKSPACE command payloads]
  - `tests/unit/test_workspace_abi.py` [NEW]
  - `tests/unit/test_workspace_state_machine.py` [NEW]
- **Dependencies**: `orbit.contracts.capabilities`, `ctypes`, `pydantic`.
- **Tests**:
  - `pytest tests/unit/test_workspace_abi.py` (Verify 48-byte `APPBARDATA` size, field offsets, `RECT` arithmetic).
  - `pytest tests/unit/test_workspace_state_machine.py` (Verify valid flows, illegal transitions, terminal states).
- **Stop Condition**: All unit tests in Step 1 pass with 100% success; ABI gate passes on 64-bit AMD64.

---

### STEP 2: Native AppBar Driver & Window Positioning

- **Goal**: Implement the low-level Win32 AppBar driver encapsulating `SHAppBarMessage(ABM_NEW, ABM_QUERYPOS, ABM_SETPOS, ABM_REMOVE)` and `SetWindowPos(HWND_TOPMOST)`.
- **Files**:
  - `src/orbit/adapters/workspace/appbar.py` [NEW]
  - `tests/unit/test_workspace_appbar.py` [NEW]
- **Dependencies**: `src/orbit/adapters/workspace/abi.py`, `src/orbit/adapters/workspace/types.py`.
- **Tests**:
  - `pytest tests/unit/test_workspace_appbar.py` (Test driver registration, query, setpos, unregistration against synthetic/test window handles).
- **Stop Condition**: Native driver registers and unregisters cleanly; zero handle leaks.

---

### STEP 3: Workspace Geometry Engine & DPI Awareness

- **Goal**: Implement the geometry calculation engine computing 25% edge reservation, minimum (380px) and maximum (720px) clamping, DPI scaling, and usable canvas dimensions.
- **Files**:
  - `src/orbit/adapters/workspace/geometry.py` [NEW]
  - `tests/unit/test_workspace_geometry.py` [NEW]
- **Dependencies**: `src/orbit/adapters/workspace/types.py`, `src/orbit/adapters/workspace/abi.py`.
- **Tests**:
  - `pytest tests/unit/test_workspace_geometry.py` (Verify 25% width calculations, clamping, DPI scaling factors, and multi-monitor bounds).
- **Stop Condition**: Pixel-accurate bounds verified for right and left dock positions.

---

### STEP 4: Watchdog Crash Recovery & Safety Integration

- **Goal**: Implement the detached watchdog launcher and coordinator guaranteeing $<350\text{ms}$ desktop restoration upon abnormal process termination.
- **Files**:
  - `src/orbit/adapters/workspace/watchdog.py` [NEW]
  - `tests/unit/test_workspace_watchdog.py` [NEW]
- **Dependencies**: `src/orbit/adapters/workspace/abi.py`, `subprocess`.
- **Tests**:
  - `pytest tests/unit/test_workspace_watchdog.py` (Verify detached process spawning, PID tracking, and graceful watchdog termination).
- **Stop Condition**: Watchdog lifecycle verified; clean termination confirmed.

---

### STEP 5: Production Workspace Adapter & Orchestrator Integration

- **Goal**: Implement `ProductionWorkspaceAdapter` uniting driver, state machine, geometry engine, and watchdog; re-export in `src/orbit/adapters/production/production_workspace.py`; wire into `OrbitOrchestrator`.
- **Files**:
  - `src/orbit/adapters/workspace/telemetry.py` [NEW]
  - `src/orbit/adapters/workspace/adapter.py` [NEW]
  - `src/orbit/adapters/production/production_workspace.py` [MODIFY - Replace stub with ProductionWorkspaceAdapter]
  - `src/orbit/runtime/orchestrator.py` [MODIFY - Wire generation invalidation & workspace event emissions]
  - `tests/integration/test_workspace_runtime_integration.py` [NEW]
- **Dependencies**: `src/orbit/adapters/workspace/*`, `src/orbit/runtime/orchestrator.py`.
- **Tests**:
  - `pytest tests/integration/test_workspace_runtime_integration.py` (Verify full adapter lifecycle, event bus publishing, observation freshness invalidation on docking).
- **Stop Condition**: End-to-end integration tests pass; truthful capability health exposed.

---

### STEP 6: Full Regression Validation, Live Windows Test & Completion Report

- **Goal**: Run complete test suites, execute live Windows 11 validation, verify 0-line diff on frozen prototypes, and produce the completion report.
- **Files**:
  - `tests/live/test_workspace_live_validation.py` [NEW]
  - `docs/M1_5_WORKSPACE_COMPLETION_REPORT.md` [NEW]
- **Dependencies**: All preceding steps.
- **Tests**:
  - `python -m pytest -v` (100% passing)
  - `python prototypes/prototype_a_workspace/formal_test_suite.py` (PASS)
  - `python prototypes/prototype_b_human_takeover/formal_test_suite.py` (PASS)
  - `python prototypes/prototype_c_keyboard/formal_test_suite.py` (PASS)
  - `python prototypes/prototype_d_observation/formal_test_suite.py` (PASS)
  - `python prototypes/prototype_e_pointer/phase2c_validation.py` (PASS)
  - `python tests/live/test_workspace_live_validation.py` (LIVE_OS_VALIDATED)
  - `git diff ca87ef8 -- prototypes/` (0 lines diff)
- **Stop Condition**: 100% test pass rate across all suites; completion report committed.

---

## 3. Strict Stop Condition

The authorized scope for this phase is **AUDIT + ARCHITECTURE + IMPLEMENTATION PLAN ONLY**.

Do NOT proceed into source code modifications or implementation until explicitly authorized.
