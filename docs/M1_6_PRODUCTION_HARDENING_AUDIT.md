# ORBIT — Milestone M1.6 Production Hardening Audit
**Phase 0 Forensic Audit & Pointer Dispatch Path Classification**
**Date:** 2026-09-06
**Status:** COMPLETE (Pre-Modification Baseline)

---

## 1. Executive Summary

An adversarial forensic audit was conducted across the ORBIT runtime codebase in response to [`docs/M1_6_INDEPENDENT_FORENSIC_AUDIT.md`](file:///c:/Users/Aaryan%20shukla/OneDrive/Desktop/ORBIT/docs/M1_6_INDEPENDENT_FORENSIC_AUDIT.md).

Two critical production-path vulnerabilities were identified and mapped:
1. **P1-HARDENING-1 (Unsafe Autonomous Synthetic Fallback):** In [`src/orbit/runtime/orchestrator.py`](file:///c:/Users/Aaryan%20shukla/OneDrive/Desktop/ORBIT/src/orbit/runtime/orchestrator.py), when a task is submitted without structured `target_intent` metadata, the runtime currently falls back to `_build_synthetic_plan()`, dispatching hardcoded cursor movements and clicks to coordinates `(500, 300)`.
2. **P1-HARDENING-2 (Unchecked Direct WebSocket Pointer Commands):** In [`src/orbit/gateway/websocket_manager.py`](file:///c:/Users/Aaryan%20shukla/OneDrive/Desktop/ORBIT/src/orbit/gateway/websocket_manager.py), inbound `MOVE_POINTER`, `CLICK_POINTER`, and button commands directly invoke pointer capability methods without validating coordinates against `WorkspaceAdapter` geometry (AppBar reserved bounds, desktop generation) or preempting when `HumanTakeover` is active.

This document traces every pointer dispatch path and classifies its safety boundary prior to the implementation of the hardening patch.

---

## 2. Comprehensive Pointer Dispatch Path Inventory & Classification

All pointer dispatch paths in the ORBIT repository have been exhaustively traced and classified according to the 4 standard safety categories:

- **Category A:** Fully safety-gated (protected by coordinate validation, generation consistency, and human takeover preemption).
- **Category B:** Development/test-only (isolated test harnesses or explicit development test fixtures).
- **Category C:** Privileged/debug-only (administrative or recovery tools with explicit token boundaries).
- **Category D:** Unsafe or bypassing (production-reachable paths that omit mandatory safety barriers or fabricate coordinates).

| Path ID | Entry Point / Call Site | Target Capability Call | Workspace Geometry Check | Generation Parity Check | Human Takeover Preemption | Current Classification | Target Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P-01** | `ClosedLoopExecutionEngine.execute_task_action` (`src/orbit/runtime/execution/engine.py:541, 576`) | `ptr.click()`, `ptr.move_to()` | YES (`wsp.validate_coordinate`) | YES (`safe_point.desktop_generation_id`) | YES (`AutonomousDispatchGate` at 8 boundaries) | **A. Fully safety-gated** | **A. Fully safety-gated** |
| **P-02** | `OrbitOrchestrator._execute_action` (`src/orbit/runtime/orchestrator.py:763, 765`) | `ptr.click()`, `ptr.move_to()` | YES (`wsp.validate_coordinate`) | YES (`expected_generation`) | YES (`SystemState.HUMAN_TAKEOVER_ACTIVE`) | **A. Fully safety-gated** | **A. Fully safety-gated** |
| **P-03** | `OrbitOrchestrator._execute_task_lifecycle` fallback (`src/orbit/runtime/orchestrator.py:568`) | Calls `_build_synthetic_plan()` generating `(500, 300)` actions, routed to `_execute_action()` | NO (coordinates hardcoded) | NO (fallback generation only) | PARTIAL (caught in `_execute_action`) | **D. Unsafe or bypassing** | **B. Development/test-only** (Fails closed on missing `target_intent` unless explicitly flagged) |
| **P-04** | `WebSocketManager._dispatch_command` for `MOVE_POINTER` (`src/orbit/gateway/websocket_manager.py:270`) | `ptr.move_to(move_payload.x, move_payload.y)` | NO (only adapter topology check) | NO | NO (ignores human takeover state) | **D. Unsafe or bypassing** | **A. Fully safety-gated** |
| **P-05** | `WebSocketManager._dispatch_command` for `CLICK_POINTER` (`src/orbit/gateway/websocket_manager.py:289`) | `ptr.click(click_payload.x, click_payload.y, ...)` | NO | NO | NO (ignores human takeover state) | **D. Unsafe or bypassing** | **A. Fully safety-gated** |
| **P-06** | `WebSocketManager._dispatch_command` for `POINTER_BUTTON_DOWN` / `POINTER_BUTTON_UP` (`src/orbit/gateway/websocket_manager.py:314, 332`) | `ptr.press_down()`, `ptr.release_up()` | NO | NO | NO (ignores human takeover state) | **D. Unsafe or bypassing** | **A. Fully safety-gated** |
| **P-07** | `WebSocketManager._dispatch_command` for `POINTER_EMERGENCY_RELEASE` / `RECOVER_POINTER_LOCKOUT` (`src/orbit/gateway/websocket_manager.py:349, 368`) | `ptr.emergency_release_all()`, `ptr.recover_locked_state()` | N/A (Release / Token reset) | N/A | YES (Safe emergency reset) | **C. Privileged/debug-only** | **C. Privileged/debug-only** |
| **P-08** | Unit & Live Pointer Adapter Tests (`tests/unit/test_pointer_*.py`, `tests/live/test_live_pointer_adapter.py`) | Direct adapter calls | N/A | N/A | N/A | **B. Development/test-only** | **B. Development/test-only** |

---

## 3. Forensic Trace: P1-HARDENING-1 (Synthetic Fallback Reachability)

### 3.1 Call Site & Reachability Analysis
- **Call site:** `src/orbit/runtime/orchestrator.py:568` in `OrbitOrchestrator._execute_task_lifecycle()`:
  ```python
  # Step 2: Target Resolution & Plan Generation
  target_intent_data = task.metadata.get("target_intent")
  if target_intent_data:
      ... # ClosedLoopExecutionEngine
  else:
      # Compatibility development plan explicitly marked
      active_gen = self.workspace.get_desktop_generation() if self.workspace and hasattr(self.workspace, "get_desktop_generation") else 0
      plan = self._build_synthetic_plan(task_id, task.prompt, generation_id=active_gen)
      ...
  ```
- **Definition:** `src/orbit/runtime/orchestrator.py:1020–1083`:
  ```python
  def _build_synthetic_plan(self, task_id: str, prompt: str, generation_id: int = 0) -> ExecutionPlan:
      # Creates pointer_move and pointer_click actions with x=500, y=300
  ```
- **Vulnerability:** If an external client or production operator submits a task without `context={"target_intent": ...}`, the system does not reject it. Instead, it silently synthesizes a plan with `(500, 300)` and dispatches OS pointer movements and clicks.
- **Root Cause:** Legacy development bootstrap path retained from M0 without a strict fail-closed production guard.

### 3.2 Remediation Plan
1. **Enforce Strict Fail-Closed Rule:** If `target_intent_data` is missing:
   - Check if `task.metadata.get("is_synthetic_development") is True` or `task.metadata.get("allow_synthetic_fallback") is True`.
   - If `False` (the default for all standard/production submissions): Immediately transition task to `TaskStatus.FAILED` with `ErrorDetail(code="TARGET_INTENT_REQUIRED", message="Autonomous execution requires structured TargetIntent in task metadata; synthetic fallback is disabled for production tasks.", recoverable=False)`.
   - Dispatch **ZERO** pointer events, **ZERO** keyboard events, and **ZERO** OS actions.
2. **Explicit Development Opt-In:** Only if explicitly flagged with `is_synthetic_development=True` / `allow_synthetic_fallback=True` may `_build_synthetic_plan()` be invoked for legacy integration fixture tests.

---

## 4. Forensic Trace: P1-HARDENING-2 (WebSocket Pointer Security)

### 4.1 Inbound Dispatch Flow Analysis
- In `src/orbit/gateway/websocket_manager.py:266–345`:
  ```python
  elif cmd.command_type == CommandType.MOVE_POINTER:
      move_payload: MovePointerPayload = payload
      if self._orchestrator.registry.is_ready(CapabilityType.POINTER):
          ptr = self._orchestrator.registry.resolve_typed(CapabilityType.POINTER, PointerCapability)
          await ptr.move_to(move_payload.x, move_payload.y)
  ```
- **Vulnerabilities Identified:**
  1. **Zero Takeover Preemption:** If an operator triggers Human Takeover (`SystemState.HUMAN_TAKEOVER_ACTIVE`), inbound WebSocket `MOVE_POINTER` and `CLICK_POINTER` commands are still executed.
  2. **Zero Workspace Geometry Validation:** The coordinates are not checked against `wsp.validate_coordinate()`. If the coordinates lie inside the reserved AppBar dock area (`RESERVED_COLLISION`) or outside monitor bounds (`COORDINATE_OUT_OF_BOUNDS`), the command is passed directly to the low-level pointer adapter.
  3. **Zero Generation Parity Check:** In multi-monitor or docked environments, stale client coordinates could collide with newly created workspace reservations.

### 4.2 Remediation Plan
1. **Centralized WebSocket Pointer Guard (`_validate_pointer_dispatch`):**
   - Before executing any pointer movement or click in `WebSocketManager`:
     - **Check 1: Human Takeover:** Query `self._orchestrator.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE` or `is_human_takeover_active()`. If active, raise `RuntimeError("Pointer action blocked: Human takeover is currently active")` with code `HUMAN_TAKEOVER_ACTIVE`.
     - **Check 2: Workspace Coordinate Validation:** Query `wsp = self._orchestrator.workspace` (or registry). If coordinates `(x, y)` are specified, execute `wsp.validate_coordinate(int(x), int(y), expected_generation=...)`. If `x, y` are `None` (current position click), query `cur_pos` and validate `(cur_pos.x, cur_pos.y)`. If invalid, raise `RuntimeError(f"Workspace coordinate validation blocked pointer dispatch to ({x}, {y}): [{status}] {msg}")`.
   - On rejection:
     - Catch exception in `_process_inbound_text` and emit `EventType.ERROR` with specific code (`HUMAN_TAKEOVER_ACTIVE`, `COORDINATE_OUT_OF_BOUNDS`, `RESERVED_COLLISION`, `GENERATION_MISMATCH`).
     - Produce **ZERO** OS pointer movements or clicks.

---

## 5. Summary Matrix & Audit Sign-Off

```
+-----------------------------------------------------------------------------------------------+
| GAPS IDENTIFIED AND CLASSIFIED                                                                |
+------------------------------------+-----------------------+----------------------------------+
| Gap Description                    | Pre-Patch Class       | Post-Patch Target                |
+------------------------------------+-----------------------+----------------------------------+
| Missing TargetIntent Fallback      | D. Unsafe/Bypassing   | B. Dev-Only (Fail Closed Prod)   |
| Direct WS MOVE_POINTER             | D. Unsafe/Bypassing   | A. Fully safety-gated            |
| Direct WS CLICK_POINTER            | D. Unsafe/Bypassing   | A. Fully safety-gated            |
| Direct WS POINTER_BUTTON_DOWN/UP   | D. Unsafe/Bypassing   | A. Fully safety-gated            |
+------------------------------------+-----------------------+----------------------------------+
```

**Phase 0 Audit Verdict:** AUDIT COMPLETE — Vulnerabilities fully mapped. Ready for implementation.
