# M1.6 STEP 1: FORENSIC ARCHITECTURE AUDIT
## SEMANTIC TARGET RESOLUTION & SAFE DYNAMIC COORDINATE DISPATCH

**Milestone:** M1.6 Step 1 (Audit Phase)  
**Date:** September 6, 2026  
**Auditor:** Antigravity AI (Pair Programming with Engineering Operator)  
**Host Environment:** Windows 11 AMD64 (Build 10.0.26200), Python 3.13.7  
**Baseline Status:** 260 / 260 Pytest PASS | Frozen Prototype Diff = 0 lines (`ca87ef8`)  
**Document Status:** COMPLETE & AUTHORITATIVE

---

## 1. System Trace & Forensic Questions

### Question 1: How a User Task Enters the Runtime
- **Trace:**
  1. Client sends HTTP POST `/api/v1/tasks` or WebSocket `TASK_SUBMIT` message to FastAPI gateway (`src/orbit/gateway/app.py`).
  2. Gateway invokes `OrbitOrchestrator.submit_task(session_id, prompt, task_id, context)` (`src/orbit/runtime/orchestrator.py:300`).
  3. `submit_task()` registers the task with `TaskManager.create_task()` in status `CREATED` (`src/orbit/runtime/task_manager.py:28`).
  4. An event `TASK_STATE_CHANGED` (`CREATED`) is published to `EventBus`.
  5. A new `CancellationSource` is created and stored in `self._active_cancellation_sources[task.task_id]`.
  6. An asynchronous background task `asyncio.create_task(self._execute_task_lifecycle(task.task_id, cancel_source.token))` is launched and tracked in `self._active_execution_tasks`.
- **Classification:** `CODE_PROVEN` & `TEST_PROVEN` (`tests/integration/test_orchestrator_execution.py`).

---

### Question 2: How the Orchestrator Currently Creates an ExecutionPlan
- **Trace:**
  1. Inside `_execute_task_lifecycle()`, after verifying system state and transitioning to `BUSY`, the orchestrator transitions the task: `VALIDATING` -> `READY` -> `RUNNING`.
  2. The orchestrator calls `obs.capture_screen(display_index=0)` and emits `OBSERVATION_FRAME`.
  3. The orchestrator immediately calls `self._build_synthetic_plan(task_id, task.prompt)` (`src/orbit/runtime/orchestrator.py:425`).
  4. The plan is stored in `TaskManager.set_plan(task_id, plan)` and emitted as a `PLAN_UPDATED` event.
- **Classification:** `CODE_PROVEN` & `TEST_PROVEN`.

---

### Question 3: Whether `_build_synthetic_plan` or an Equivalent Synthetic/Static Planning Mechanism Still Exists
- **Findings:**
  - **YES, IT STILL EXISTS.** In `src/orbit/runtime/orchestrator.py:579-621`:
  ```python
  def _build_synthetic_plan(self, task_id: str, prompt: str) -> ExecutionPlan:
      step_1 = Step(
          step_id=f"step_1_{uuid4().hex[:6]}",
          step_index=0,
          description="Observe display and position cursor",
          actions=[
              Action(
                  action_id=f"act_1_{uuid4().hex[:6]}",
                  task_id=task_id,
                  action_type="pointer_move",
                  tier=ActionTier.TIER_1_SAFE,
                  parameters={"x": 500, "y": 300},
              ),
              Action(
                  action_id=f"act_2_{uuid4().hex[:6]}",
                  task_id=task_id,
                  action_type="pointer_click",
                  tier=ActionTier.TIER_2_CONSTRAINED,
                  parameters={"x": 500, "y": 300, "button": "left"},
              ),
          ],
      )
      step_2 = Step(
          step_id=f"step_2_{uuid4().hex[:6]}",
          step_index=1,
          description="Type input content",
          actions=[
              Action(
                  action_id=f"act_3_{uuid4().hex[:6]}",
                  task_id=task_id,
                  action_type="type_text",
                  tier=ActionTier.TIER_2_CONSTRAINED,
                  parameters={"text": f"ORBIT automated input: {prompt}"},
              ),
          ],
      )
  ```
  - This is entirely static, single-pass, and completely blind to what is on the screen.
- **Classification:** `CODE_PROVEN`.

---

### Question 4: Exactly What Data `ObservationSnapshot` Contains
- **Source Definition:** `src/orbit/adapters/observation/snapshot.py:88-107`
  - `snapshot_id: str`: Unique snapshot identifier (`snap_...`).
  - `generation_id: int`: Monotonic desktop state generation number.
  - `timestamp_ns: int`: Monotonic timestamp in nanoseconds.
  - `timestamp_utc: datetime`: UTC timestamp of capture.
  - `capture_duration_ms: float`: Wall clock duration of observation capture.
  - `desktop_geometry: BoundingBox`: Unified virtual desktop bounding box (`left, top, width, height`).
  - `coordinate_space: CoordinateSpace`: Coordinate system (`VIRTUAL_DESKTOP`, `PHYSICAL_PIXELS`, etc.).
  - `foreground_window: Optional[ObservedWindow]`: HWND, PID, process name, window title, extended bounds (DWM frame), foreground flag, visible flag, DPI scaling.
  - `windows: List[ObservedWindow]`: All enumerated visible top-level desktop windows.
  - `detected_elements: List[ObservedElement]`: Accessible UI elements (`element_id`, `source` e.g. `WIN32_CONTROL`, `MSAA`, `UI_AUTOMATION`, `name`, `role`, `control_type`, `automation_id`, `class_name`, `bounds`, `coordinate_space`, `is_enabled`, `is_focused`, `is_offscreen`, `confidence`).
  - `detected_targets: List[ObservedTarget]`: Fused UI targets (`target_id`, `name`, `role`, `physical_bounds`, `window_relative_bounds`, `is_visible`, `is_occluded`, `confidence`, `provenance_sources`, `contradiction_notes`).
  - `confidence: ObservationConfidence`: Overall confidence (`CONFIRMED`, `PARTIALLY_CONFIRMED`, etc.).
  - `freshness_state: FreshnessState`: `FRESH` (<250ms), `AGING` (250-500ms), `STALE` (>500ms), or `UNKNOWN`.
  - `is_stale: bool`: Boolean stale flag evaluated by `FreshnessEvaluator`.
  - `invalidation_reason: Optional[str]`: Diagnostic reason if invalidated.
  - `telemetry: Dict[str, Any]`: Diagnostic performance metrics.
- **Classification:** `CODE_PROVEN` & `TEST_PROVEN`.

---

### Question 5: Whether Current Observation Capability Exposes Specific Perception Data
- **1. Screen Dimensions:** **YES.** Exposes `desktop_geometry` in snapshot (`BoundingBox(left, top, width, height)`) and `Resolution` in `FrameData`. (`CODE_PROVEN`, `LIVE_OS_VALIDATED`)
- **2. Pixels & Image Buffers:** **YES.** `capture_screen()` returns `FrameData` containing JPEG/raw bytes (`raw_bytes`). (`CODE_PROVEN`, `LIVE_OS_VALIDATED`)
- **3. Regions:** **YES.** `FrameData.roi` and `ObservedWindow.extended_bounds`, `ObservedElement.bounds` specify exact pixel bounding boxes. (`CODE_PROVEN`, `LIVE_OS_VALIDATED`)
- **4. Metadata:** **YES.** Monotonic timestamps, generation IDs, DPI scaling, process names, window titles. (`CODE_PROVEN`, `LIVE_OS_VALIDATED`)
- **5. Accessibility Information:** **YES.** MSAA and UI Automation element trees collected via `AccessibilityCoordinator` (accessible name, role, control type, automation ID). (`CODE_PROVEN`, `LIVE_OS_VALIDATED`)
- **6. Window Information:** **YES.** Enumerates visible top-level HWNDs via `WindowTracker` (`window_title`, `process_name`, `extended_bounds`, `is_foreground`). (`CODE_PROVEN`, `LIVE_OS_VALIDATED`)
- **7. UI Element Information:** **YES.** `detected_elements` in snapshot provides bounding box, name, role, control type, class name, and enabled/focus state. (`CODE_PROVEN`, `LIVE_OS_VALIDATED`)
- **8. OCR Results:** **NO.** In Prototype D, OCR is an abstract provider interface with local WinRT/Tesseract skeletons (`ocr_engine.py`), but `ProductionObservationAdapter.capture_snapshot()` does NOT call OCR. Production OCR results are **NOT_IMPLEMENTED**.
- **9. Visual-Language / Object Detection Models:** **NO.** Zero VLM or neural object detection models exist in the repository. **NOT_IMPLEMENTED**.
- **Classification:** `CODE_PROVEN` (No fake perception claims).

---

### Question 6: How Pointer Actions are Represented in the Action Contract
- **Source Definition:** `src/orbit/contracts/runtime.py:80-94`
  ```python
  class Action(BaseModel):
      action_id: str
      task_id: str
      action_type: str  # "pointer_click", "pointer_move", "pointer_down", "pointer_up"
      tier: ActionTier  # TIER_1_SAFE, TIER_2_CONSTRAINED, TIER_3_HIGH_IMPACT
      stage: ActionStage  # PENDING -> AUTHORIZED -> DISPATCHED -> EXECUTING -> VERIFYING -> COMPLETED
      parameters: Dict[str, Any]  # Unvalidated dictionary, e.g. {"x": 500, "y": 300, "button": "left"}
      created_at: datetime
      dispatched_at: Optional[datetime] = None
      completed_at: Optional[datetime] = None
      verification: Optional[VerificationResult] = None
      error: Optional[ErrorDetail] = None
  ```
  - Coordinates currently reside loosely inside `action.parameters["x"]` and `action.parameters["y"]`.
  - There is no strongly typed target reference or provenance metadata inside `Action.parameters`.
- **Classification:** `CODE_PROVEN`.

---

### Question 7: Where Pointer Coordinates are Ultimately Dispatched
- **Dispatch Path:**
  1. `OrbitOrchestrator._execute_action()` reads `x = action.parameters.get("x", 100)`, `y = action.parameters.get("y", 100)`.
  2. For `pointer_click`: calls `await ptr.click(x, y, button=btn)`.
  3. For `pointer_move`: calls `await ptr.move_to(x, y)`.
  4. In `ProductionPointerAdapter`:
     - `move_to(x, y)` delegates to `MovementExecutor.execute_movement()`.
     - Coordinates are normalized to Win32 SendInput domain `0..65535` via `normalize_to_sendinput(x, y, metrics)`.
     - Injected into OS via `user32.SendInput()` with `dwExtraInfo = ORBIT_POINTER_SIGNATURE (0x4F524254)`.
- **Classification:** `CODE_PROVEN` & `LIVE_OS_VALIDATED`.

---

### Question 8: How WorkspaceGeometryCoordinator.validate_coordinate() Currently Works
- **Source Definition:** `src/orbit/adapters/workspace/geometry.py:357-436`
  ```python
  def validate_coordinate(
      self,
      x: int,
      y: int,
      expected_generation: Optional[int] = None,
      target_geometry: Optional[WorkspaceGeometry] = None,
  ) -> CoordinateValidationResult:
  ```
  - **Check 1: Desktop Generation Parity Gate:** If `expected_generation is not None` and `expected_generation != self.state_manager.desktop_generation_id`, returns `status=CoordinateValidationStatus.STALE_COORDINATE_CONTEXT`.
  - **Check 2: Virtual Desktop Bounds:** Verifies `vd.left <= x < vd.left + vd.width` and `vd.top <= y < vd.top + vd.height`. If outside, returns `status=CoordinateValidationStatus.OUT_OF_BOUNDS`.
  - **Check 3: Target Monitor Lookup:** Identifies which monitor index contains `(x, y)`.
  - **Check 4: Reserved Dock Collision:** Calls `geom.is_point_in_docked_area(x, y)`. If within docked AppBar reservation, returns `status=CoordinateValidationStatus.RESERVED_WORKSPACE_COLLISION`.
  - If all checks pass, returns `is_valid=True`, `status=CoordinateValidationStatus.VALID`.
- **Classification:** `CODE_PROVEN` & `TEST_PROVEN` (`tests/unit/test_workspace_geometry.py`).

---

### Question 9: How desktop_generation_id is Propagated
- **In Workspace Adapter:** `WorkspaceStateManager` increments `desktop_generation_id` atomically whenever the AppBar is docked, undocked, resized, or when display resolution/topology changes. (`CODE_PROVEN`)
- **In Observation Adapter:** `ProductionObservationAdapter.capture_snapshot()` stamps `snapshot.generation_id` with the current generation. `FreshnessEvaluator` checks if `snapshot.generation_id != current_generation`, marking stale if mismatch. (`CODE_PROVEN`)
- **In Pointer Execution:** **UNCONNECTED.** `ProductionPointerAdapter.move_to()` and `click()` do NOT accept or check `desktop_generation_id`. Pointer executes strictly in normalized virtual desktop coordinates.
- **In Orchestrator:** **UNCONNECTED.** The orchestrator currently does NOT track or verify `desktop_generation_id` between observation capture and pointer dispatch.
- **Classification:** `CODE_PROVEN`.

---

### Question 10: How Human Takeover Cancellation Propagates Through an Active Task
- **Trace:**
  1. Low-level Windows hooks (`WH_MOUSE_LL`, `WH_KEYBOARD_LL`) intercept physical user events.
  2. Events without ORBIT signatures trigger `on_takeover_detected` callback in `OrbitOrchestrator._on_physical_takeover_detected`.
  3. `OrbitOrchestrator.handle_human_takeover()`:
     - Transitions `_system_sm` to `HUMAN_TAKEOVER_ACTIVE`.
     - Calls `src.cancel(reason)` on all tokens in `_active_cancellation_sources`.
     - Calls `self.safety.emergency_stop_all()` to release held mouse buttons and keys.
  4. Inside `_execute_task_lifecycle()`: checks `cancel_token.is_cancelled` before step/action execution.
  5. Inside `_execute_action()`: checks `cancel_token.is_cancelled` before capability dispatch and immediately cancels action.
  6. However, `_execute_action()` does NOT pass `cancel_token` into `ptr.click(x, y)` or `ptr.move_to(x, y)`.
- **Classification:** `CODE_PROVEN` & `TEST_PROVEN` (`tests/integration/test_takeover_orchestrator_flow.py`).

---

### Question 11: Whether a Coordinate Can Currently Reach the Pointer Adapter Without Passing Through Workspace Validation
- **Finding:** **YES, 100% OF THE TIME.**
  - In `OrbitOrchestrator._execute_action()` (`src/orbit/runtime/orchestrator.py:516-526`):
    - `x` and `y` are extracted from `action.parameters` and dispatched directly to `ptr.click(x, y)` or `ptr.move_to(x, y)`.
    - `workspace.validate_coordinate()` is NEVER called in `OrbitOrchestrator`.
    - Any coordinate—even inside the reserved dock area or outside screen bounds—reaches `ProductionPointerAdapter` without workspace validation.
- **Classification:** `CODE_PROVEN`.

---

### Question 12: Identification of Every Existing Hardcoded/Synthetic Action Coordinate
- **In `src/orbit/runtime/orchestrator.py`:**
  - Line 518: `x = action.parameters.get("x", 100)` (fallback default)
  - Line 519: `y = action.parameters.get("y", 100)` (fallback default)
  - Line 524: `x = action.parameters.get("x", 100)` (fallback default)
  - Line 525: `y = action.parameters.get("y", 100)` (fallback default)
  - Line 591: `parameters={"x": 500, "y": 300}` (in `_build_synthetic_plan` step 1 move)
  - Line 598: `parameters={"x": 500, "y": 300, "button": "left"}` (in `_build_synthetic_plan` step 1 click)
- **Classification:** `CODE_PROVEN`.

---

## 2. Epistemic Classification Summary

| Architectural Component | Repository Evidence | Classification |
| :--- | :--- | :--- |
| Task Ingestion & Lifecycle | `OrbitOrchestrator.submit_task`, `TaskManager` | `CODE_PROVEN` & `TEST_PROVEN` |
| Observation Capture (Frames) | `ProductionObservationAdapter.capture_screen` (GDI) | `CODE_PROVEN` & `LIVE_OS_VALIDATED` |
| Observation Capture (Snapshot) | `ProductionObservationAdapter.capture_snapshot` | `CODE_PROVEN` & `LIVE_OS_VALIDATED` |
| Top-level Window Enumeration | `WindowTracker.enumerate_visible_windows` | `CODE_PROVEN` & `LIVE_OS_VALIDATED` |
| Accessibility Tree Extraction | `AccessibilityCoordinator` (MSAA/UIA) | `CODE_PROVEN` & `LIVE_OS_VALIDATED` |
| OCR Text Extraction | `ocr_engine.py` (optional skeleton, uncalled) | `NOT_IMPLEMENTED` in production pipeline |
| Semantic Computer Vision / VLM | Zero vision-language models in repository | `NOT_IMPLEMENTED` |
| Workspace Coordinate Gate | `WorkspaceGeometryCoordinator.validate_coordinate` | `CODE_PROVEN` & `TEST_PROVEN` |
| Pre-Dispatch Coordinate Gate in Runtime | Orchestrator bypasses workspace validation | `NOT_IMPLEMENTED` (Gap to be closed) |
| Hardcoded Action Coordinates | `_build_synthetic_plan` uses (500, 300) | `CODE_PROVEN` (Gap to be eliminated) |
| Target Resolution Domain Model | No typed `TargetLocator` or `ResolvedTarget` | `NOT_IMPLEMENTED` (Gap to be built) |

---

## 3. M1.6 Step 1 Design & Implementation Plan

### A. Location of New Subsystem
- Directory: `src/orbit/runtime/targeting/`
- Files:
  - `src/orbit/runtime/targeting/__init__.py`
  - `src/orbit/runtime/targeting/models.py` (Typed domain models: `TargetIntent`, `TargetBoundingBox`, `ResolvedTarget`, `TargetResolutionResult`, `TargetResolutionStatus`, `TargetEvidence`, `SafeActionPoint`)
  - `src/orbit/runtime/targeting/locator.py` (`TargetLocator` protocol and `EvidenceBasedTargetLocator` implementation supporting genuine observation evidence: element matching by name/role/class/automation_id, window matching by title/process, and explicit bounding boxes)
  - `src/orbit/runtime/targeting/action_point.py` (`calculate_safe_action_point()` calculating safe interior point with zero-area, inverted bounds, integer overflow checks)

### B. Pre-Dispatch Workspace Validation Gate
- In `OrbitOrchestrator._execute_action()`:
  - Before any `pointer_click` or `pointer_move`:
  1. Retrieve `x`, `y`, and `expected_generation` from action parameters / target context.
  2. If `workspace` capability is available:
     - Invoke `workspace.validate_coordinate(x, y, expected_generation=expected_generation)`.
     - If validation fails (`status != VALID`):
       - Fail closed! Do NOT dispatch to pointer adapter.
       - Set `action.stage = ActionStage.FAILED`.
       - Record error with exact validation failure reason (`RESERVED_WORKSPACE_COLLISION`, `OUT_OF_BOUNDS`, `STALE_COORDINATE_CONTEXT`).
       - Raise `RuntimeError` or emit structured failure.
  3. Ensure `MockWorkspaceAdapter` also implements `validate_coordinate()` and `get_desktop_generation()` to ensure test parity without breaking mock execution.

### C. Remove / Isolate Unsafe Hardcoded Coordinates
- In `OrbitOrchestrator`:
  - Deprecate `_build_synthetic_plan()` or restrict it explicitly to development/test fixtures where explicitly requested.
  - Require actions with targets to provide `TargetIntent` or resolved coordinates validated through workspace gate.
  - Remove fallback `100, 100` defaults in `_execute_action()`; fail closed with descriptive `ValueError` if required coordinates are missing.

### D. Human Takeover & Cancellation Gate
- In `_execute_action()`, forward `cancel_token` to `ptr.click(x, y, cancellation_token=cancel_token)` and `ptr.move_to(x, y, cancellation_token=cancel_token)`.
- Re-check `cancel_token.is_cancelled` and `self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE` immediately prior to workspace validation and pointer dispatch.

---

## 4. Audit Sign-Off
Forensic audit complete. All 12 questions answered with concrete repository evidence.
Proceed to implementation of M1.6 Step 1.
