# ORBIT Milestone M1.5 Step 4 — Workspace Watchdog, Failure Recovery & Lifecycle Resilience Audit

**Milestone**: M1.5 — Production Workspace / AppBar Integration  
**Step**: Step 4 — Workspace Watchdog, Failure Recovery & Lifecycle Resilience  
**Status**: **PRE-IMPLEMENTATION AUDIT**  
**Date**: September 6, 2026  
**Host Environment**: Windows 11 CoreSingleLanguage AMD64 (Build 10.0.26200), Python 3.13.7  
**Baseline Frozen Commit**: `ca87ef8`

---

## 1. Executive Summary

Milestone M1.5 Step 4 introduces the **Production Workspace Watchdog and Lifecycle Resilience Layer**.

In Windows desktop automation, external events can asynchronously disrupt the desktop environment while ORBIT is operating:
1. **Third-Party Shell Crashes / Restarts (`explorer.exe`)**: Destroys AppBar registrations silently.
2. **Display Resolution / Topology Changes**: Monitor disconnection, hotplugging, or resolution resizing invalidates the negotiated dock geometry.
3. **External Window Destruction**: The native AppBar HWND could be closed or destroyed externally.
4. **Human Interaction / Dragging**: Users or third-party utilities may force-move or resize the docked window.

If ORBIT's in-memory state continues to assume the workspace is `DOCKED` and healthy when native resources have mutated, coordinate calculations will hallucinate and pointer actions will click into incorrect areas. 

Step 4 establishes an active, bounded watchdog that continuously probes native state, classifies anomalies, increments generation counters fail-closed, and executes safe bounded recovery.

---

## 2. Native State Observability Analysis

### 2.1 Native State That CAN Be Reliably Observed
| Observable State | Win32 Mechanism | Diagnostic Value |
| :--- | :--- | :--- |
| **Window Handle Existence** | `user32.IsWindow(hWnd)` | Confirms whether HWND is a live Win32 window. |
| **Window Physical Rect** | `user32.GetWindowRect(hWnd, &rect)` | Verifies whether the window remains positioned at negotiated coordinates. |
| **Window Visibility & Minimized** | `user32.IsWindowVisible(hWnd)`, `user32.IsIconic(hWnd)` | Detects if window was hidden or minimized. |
| **Virtual Desktop Dimensions** | `GetSystemMetrics(SM_CXVIRTUALSCREEN, ...)` | Detects full virtual screen size mutations. |
| **Monitor Topologies & Work Areas** | `EnumDisplayMonitors`, `GetMonitorInfoW` | Detects monitor disconnection, DPI change, or resolution change. |

### 2.2 Native State That CANNOT Be Directly Inspected
- **Direct Shell AppBar Registration Query**: Windows does not provide a read-only Win32 API to query "is window $H$ currently registered in the Shell's internal AppBar table" without issuing `SHAppBarMessage(ABM_GETSTATE)` or modifying state.
- **Epistemic Principle**: The watchdog must infer AppBar consistency from HWND validity, `GetWindowRect` parity with negotiated bounds, and Shell notification callback records (`WM_APPBAR_CALLBACK`), rather than fabricating false certainty.

---

## 3. Watchdog Ownership & Lifecycle Model

```text
                  Owner (Adapter / Runtime)
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
      start_watchdog()                  stop_watchdog()
            │                                 │
     (Spawns Task)                      (Cancels Task)
            │                                 │
            ▼                                 ▼
     [RUNNING LOOP]                     [STOPPED STATE]
     • probe_health()                   • Drain in-flight probes
     • evaluate_consistency()           • Zero orphan threads
     • handle_recovery()                • Idempotent repeated calls
```

### Invariants:
1. **Explicit Lifecycle**: Watchdog is explicitly startable (`start()`) and stoppable (`stop()`).
2. **Deterministic Shutdown**: Shutdown cancels the background worker and awaits task completion with timeout containment.
3. **No Duplicate Workers**: Calling `start()` while running is an idempotent no-op (or rejects duplicate instantiation).
4. **Zero Orphan Tasks**: Worker is owned and tracked as a single `asyncio.Task` or daemon thread.

---

## 4. Health States & Failure Classification

### 4.1 Health States
- `HEALTHY`: Native window exists, geometry matches expectations, topology is unchanged.
- `DEGRADED`: Geometry mismatch, transient probe error, or topology change detected; automatic recovery eligible.
- `FAILED`: Window destroyed, unrecoverable native error, or recovery budget exhausted; requires operator reset.
- `STOPPED`: Watchdog inactive or cleanly stopped.
- `UNKNOWN`: Insufficient evidence to determine health.

### 4.2 Failure Categories
```text
WINDOW_DESTROYED           - HWND is no longer a valid window (IsWindow == False)
INVALID_HWND               - HWND is 0 or None while expected state is DOCKED
GEOMETRY_MISMATCH          - Live GetWindowRect deviates from negotiated bounds
TOPOLOGY_CHANGED           - Virtual desktop metrics or monitor count changed
DPI_CONTEXT_CHANGED        - Display DPI scale mutated
APPBAR_OPERATION_FAILED    - Native Shell message returned error
NATIVE_PROBE_FAILED        - Exception during Win32 health probe query
RECOVERY_BUDGET_EXHAUSTED  - Maximum consecutive recovery attempts exceeded
```

---

## 5. Recovery Policy & Bounded Budget

### 5.1 Recovery Invariants
- **Bounded Budget**: Maximum $N$ recovery attempts (default `max_recovery_attempts = 3`) within a sliding cooldown window (`recovery_cooldown_sec = 2.0`).
- **Fail-Closed on Exhaustion**: If $N$ attempts fail, watchdog transitions workspace state to `FAILED`, raises an alarm, and halts autonomous retry loops.
- **Safe Automatic Recovery vs. Operator Recovery**:
  * *Automatic*: Refreshing cached geometry on `TOPOLOGY_CHANGED` or re-asserting `SetWindowPos` on minor positional drift.
  * *Operator-Required*: Window destruction or Shell crash requires explicit operator recovery token (`"CONFIRM_OPERATOR_MANUAL_RESET"`).

---

## 6. Generation Invalidation & Safety Boundary

When a material failure or recovery occurs:
```text
Watchdog Detects Anomaly (e.g. WINDOW_DESTROYED or GEOMETRY_MISMATCH)
                           │
                           ▼
 WorkspaceStateManager.transition_to(DEGRADED / FAILED)
                           │
                           ▼
 desktop_generation_id incremented (Authoritative)
                           │
       ┌───────────────────┴───────────────────┐
       ▼                                       ▼
Observation Snapshot Rejected          Pointer Coordinate Validations Fail
(Freshness: GENERATION_MISMATCH)       (Gate: STALE_COORDINATE_CONTEXT)
```

---

## 7. Human Takeover Coordination (M1.4 Integration)

- When `HumanTakeoverCapability` reports takeover is active (`HUMAN_TAKEOVER_ACTIVE`):
  1. The watchdog continues passive health observation and diagnostic recording.
  2. Autonomous disruptive recovery (window repositioning, AppBar recreation) is strictly **SUPPRESSED**.
  3. The watchdog must not fight the human operator for desktop geometry control.

---

## 8. Next Steps (Step 4 Implementation)

1. Implement `src/orbit/adapters/workspace/watchdog.py`.
2. Re-export watchdog models in `src/orbit/adapters/workspace/__init__.py`.
3. Create comprehensive test suite `tests/unit/test_workspace_watchdog.py`.
4. Validate full production regression suite and frozen prototype baselines.
