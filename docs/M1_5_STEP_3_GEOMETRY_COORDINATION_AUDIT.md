# ORBIT Milestone M1.5 Step 3 — Workspace Geometry, DPI & Capability Coordination Audit

**Milestone**: M1.5 — Production Workspace / AppBar Integration  
**Step**: Step 3 — Workspace Geometry, DPI Awareness & Capability Coordination  
**Status**: **PRE-IMPLEMENTATION AUDIT**  
**Date**: September 6, 2026  
**Host Environment**: Windows 11 CoreSingleLanguage AMD64 (Build 10.0.26200), Python 3.13.7  
**Baseline Frozen Commit**: `ca87ef8`

---

## 1. Executive Summary

Milestone M1.5 Step 3 establishes the **Authoritative Geometry and Capability Coordination Layer** for ORBIT. 

When ORBIT's workspace is docked, released, resized, moved, DPI-scaled, or relocated across monitors, observation snapshots and pointer transactions must remain strictly synchronized with the physical and logical realities of the Windows desktop. 

Operating under stale coordinate or generation assumptions can result in:
1. **Mis-targeted Pointer Clicks**: Dispatching SendInput events into unintended application regions or ORBIT's own docked window.
2. **Stale Observation Hallucinations**: Action plans executing against UI elements that have shifted due to work-area resizing.
3. **Multi-Monitor / Negative Coordinate Truncation**: Flawed normalization math that clamps negative coordinates to `(0, 0)`.
4. **DPI Distortion**: Misaligned hit-testing caused by conflicting physical vs. logical DIP coordinate assumptions.

This audit evaluates the current coordinate models across Observation, Pointer, Keyboard, and Workspace adapters, identifies potential multi-monitor and DPI hazards, and specifies the architecture for `WorkspaceGeometryCoordinator`.

---

## 2. Forensic Analysis of Existing Coordinate Models

### 2.1 Observation Coordinate Model (`src/orbit/adapters/observation/`)
- **`CoordinateSpace` Enum**:
  - `PHYSICAL_PIXELS`: Hardware monitor pixels.
  - `VIRTUAL_DESKTOP`: Unified desktop bounding box spanning all monitors (`SM_XVIRTUALSCREEN`, `SM_YVIRTUALSCREEN`, `SM_CXVIRTUALSCREEN`, `SM_CYVIRTUALSCREEN`).
  - `WINDOW_RELATIVE`: Coordinates relative to window top-left.
  - `LOGICAL_DIP`: Device Independent Pixels.
- **Freshness & Generation Verification (`FreshnessEvaluator`)**:
  - Validates `snapshot.generation_id == current_generation`.
  - Rejects stale snapshots if `generation_id` mismatches (`GENERATION_MISMATCH`).
  - Checks TTL against `max_ttl_ms` (default 500ms).
- **Coordinate Mapping (`mapper.py`)**:
  - Maps Prototype D observation structures into production `ObservationSnapshot`.
  - Normalizes `RECT` structures to `BoundingBox(left, top, width, height)`.

### 2.2 Pointer Coordinate Model (`src/orbit/adapters/pointer/`)
- **Coordinate Space & Normalization (`normalize_to_sendinput`)**:
  - Normalizes physical virtual desktop coordinates `(x, y)` to Win32 `0..65535` absolute space:
    $$\text{norm\_x} = \left\lfloor \frac{(x - \text{x\_origin}) \times 65535}{\text{width} - 1} \right\rfloor$$
    $$\text{norm\_y} = \left\lfloor \frac{(y - \text{y\_origin}) \times 65535}{\text{height} - 1} \right\rfloor$$
  - Preserves negative origin coordinates (`x_origin < 0` or `y_origin < 0`).
  - Flags coordinates outside `VirtualDesktopMetrics.contains_point(x, y)` as `REJECTED_OUT_OF_BOUNDS`.
- **Topology Mutation Safety (`VirtualDesktopTopologyIdentity`)**:
  - Fingerprints `(origin_x, origin_y, width, height, monitor_count)`.
  - Verifies topology fingerprint immediately before native `SendInput` dispatch (`T6` checkpoint in `MovementExecutor`).

### 2.3 Workspace State & Generation Semantics (`src/orbit/adapters/workspace/`)
- **Authoritative Generations**:
  - `desktop_generation_id`: Incremented monotonically when workspace state transitions into `DOCKED` and out of `DOCKED` (or during reconfiguration).
  - `topology_generation_id`: Incremented on display topology/resolution change.
- **Workspace Geometry Model (`WorkspaceGeometry`)**:
  - Encapsulates `physical_display` (full virtual desktop bounds), `work_area` (usable canvas after taskbar & dock reservation), `docked_bounds` (ORBIT's reserved slice), `dock_edge`, and `monitors` list (`DisplayMonitorInfo`).

---

## 3. Coordinate Safety Invariants & Risk Analysis

### 3.1 Multi-Monitor & Negative Coordinate Hazards
1. **Negative Virtual Coordinates**:
   - Secondary monitors positioned to the left or above the primary monitor have negative top-left coordinates (e.g. `left = -1920`, `top = 0`).
   - *Requirement*: The geometry coordinator must never clamp `x < 0` or `y < 0` to 0. All bounding boxes and normalization math must use virtual desktop relative offsets `(x - x_origin)`.
2. **Non-Uniform Multi-Monitor Grids**:
   - Multi-monitor configurations may have discontinuous or L-shaped bounds.
   - *Requirement*: Coordinates must be validated against both total virtual desktop bounds and individual monitor bounding boxes.

### 3.2 DPI Awareness Hazards
1. **Mixed-DPI Setups**:
   - Primary monitor at 192 DPI (200% scale) and secondary at 96 DPI (100% scale).
   - In Per-Monitor DPI Aware V2 mode, Win32 APIs return physical pixels for window geometries when queried with appropriate per-monitor APIs (`GetDpiForMonitor` via `Shcore.dll`).
2. **DPI Query Fallbacks**:
   - If `GetDpiForMonitor` is unavailable or fails, query `GetDpiForSystem` or `GetDeviceCaps(LOGPIXELSX)`.
   - If DPI cannot be verified, explicitly report uncertainty (`is_dpi_aware=False`, `scale_factor=1.0`) without fabricating scale assumptions.

### 3.3 Generation Desynchronization Hazards
1. **Stale Snapshot Reuse**:
   - If AppBar docks at $t=100$, usable work area shifts by 720px. An observation captured at $t=90$ has `generation_id = 1`, but active generation is now `2`.
   - *Requirement*: Any action or coordinate evaluation referencing a generation prior to the current `desktop_generation_id` must be rejected fail-closed with `STALE_COORDINATE_CONTEXT`.
2. **Point Collision with Reserved Dock**:
   - An action intended for third-party applications must not click inside `docked_bounds` unless explicitly targeting ORBIT's UI.

---

## 4. Architecture for M1.5 Step 3 Implementation

### 4.1 Component: `WorkspaceGeometryCoordinator` (`src/orbit/adapters/workspace/geometry.py`)
Responsible for:
1. **Topology Discovery**:
   - Enumerate attached monitors via `EnumDisplayMonitors` and `GetMonitorInfoExW`.
   - Query per-monitor DPI via `GetDpiForMonitor` (`MDT_EFFECTIVE_DPI = 0`).
   - Query virtual desktop bounds (`SM_XVIRTUALSCREEN`, `SM_YVIRTUALSCREEN`, `SM_CXVIRTUALSCREEN`, `SM_CYVIRTUALSCREEN`).
   - Calculate usable desktop canvas and monitor-specific work areas.
2. **Authoritative Geometry Resolution**:
   - Constructs immutable `WorkspaceGeometry` snapshot with active `desktop_generation_id` and `topology_generation_id`.
   - Provides point-in-canvas and point-in-dock predicates.
3. **Coordinate Validation & Gating**:
   - `validate_coordinate(x, y, generation_id)`: Verifies coordinate validity against virtual desktop metrics and validates generation parity.
   - `is_point_in_usable_canvas(x, y)`: Ensures target point falls strictly within unreserved work area.
   - `is_point_in_docked_area(x, y)`: Identifies if point falls within ORBIT dock.

### 4.2 Win32 API Definitions (`src/orbit/adapters/workspace/abi.py`)
Add explicit ctypes signatures for:
- `EnumDisplayMonitors` (`user32.dll`)
- `GetMonitorInfoW` (`user32.dll`)
- `MonitorFromPoint` (`user32.dll`)
- `MonitorFromRect` (`user32.dll`)
- `GetDpiForMonitor` (`shcore.dll` with fallback)
- `GetDpiForSystem` (`user32.dll` with fallback)

---

## 5. Fail-Safe Error Protocols

| Condition | Failure Mode | Action Taken |
| :--- | :--- | :--- |
| Coordinate outside virtual desktop | `OUT_OF_BOUNDS` | Reject movement / validation fail-closed |
| Generation mismatch ($G_{target} \neq G_{active}$) | `STALE_COORDINATE_CONTEXT` | Invalidate snapshot; force observation refresh |
| Target coordinate inside ORBIT dock | `RESERVED_WORKSPACE_COLLISION` | Reject execution or flag workspace hazard |
| Monitor handle resolution fails | `GEOMETRY_UNAVAILABLE` | Fallback to primary virtual desktop bounds |
| DPI query fails | `DPI_UNAVAILABLE` | Mark `scale_factor=1.0`, record diagnostic flag |

---

## 6. Execution Plan

1. **ABI Extension**: Add monitor enumeration and DPI ctypes signatures to `abi.py`.
2. **Geometry Coordinator**: Implement `WorkspaceGeometryCoordinator` in `geometry.py`.
3. **Coordinator Integration**: Expose geometry queries and coordinate validation through `src/orbit/adapters/workspace/`.
4. **Unit & Coordination Tests**:
   - `test_workspace_geometry.py`: Virtual desktop topology, negative coordinates, multi-monitor, DPI scaling, and coordinate validation gates.
   - Generation parity tests linking workspace state transitions with observation and pointer coordinate validation.
5. **Full Regression Validation**:
   - Pytest suite
   - 5 Prototype test suites
   - Frozen boundary diff verification
