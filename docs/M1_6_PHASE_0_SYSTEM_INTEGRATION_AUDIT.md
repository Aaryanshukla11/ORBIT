# M1.6 PHASE 0: SYSTEM ARCHITECTURE, CAPABILITY INTEGRATION & END-TO-END AUTONOMY READINESS AUDIT

**Milestone:** M1.6 Phase 0 (Audit & Architecture Only)  
**Date:** September 6, 2026  
**Auditor:** Antigravity AI (Pair Programming with Engineering Operator)  
**Host Environment:** Windows 11 AMD64 (Build 10.0.26200), Python 3.13.7  
**Baseline Verification:** 260 / 260 Pytest PASS | 5 / 5 Prototype Suites PASS | 0 lines diff across frozen prototype boundary (`ca87ef8`)  
**Status:** COMPLETE & AUTHORITATIVE

---

## 1. Current System Architecture Overview

ORBIT is a production-grade, local-first Windows desktop automation runtime engineered in Python 3.13+ on Windows 11 AMD64. The architecture is organized hierarchically into contracts, capability adapters (mock and production), infrastructure primitives, runtime state machines, and a FastAPI Gateway:

```
                            [Client / Web UI / CLI]
                                      |
                                      v (HTTP / WebSocket)
                            +--------------------+
                            |   FastAPI Gateway  |
                            | (WebSocketManager) |
                            +--------------------+
                                      |
                                      v
                            +--------------------+
                            | OrbitOrchestrator  |
                            |  (Runtime Engine)  |
                            +--------------------+
                                      |
               +----------------------+----------------------+
               |                      |                      |
               v                      v                      v
       [EventBus Primitives]   [TaskManager]      [CapabilityRegistry]
                                                             |
    +-----------------+-----------------+--------------------+-----------------+-----------------+
    |                 |                 |                    |                 |                 |
    v                 v                 v                    v                 v                 v
[OBSERVATION]     [POINTER]         [KEYBOARD]       [HUMAN_TAKEOVER]     [WORKSPACE]        [SAFETY]
ProductionObservation ProductionPointer ProductionKeyboard ProductionHumanTakeover ProductionWorkspace ProductionSafety
```

---

## 2. Complete Capability Inventory

Every capability subsystem in ORBIT has been audited against its interface contract, production implementation, mock implementation, safety mechanisms, and test validation status:

| Capability Subsystem | Contract Interface | Production Implementation | Mock Implementation | Lifecycle State | Validation Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Pointer Control** | `PointerCapability` | `ProductionPointerAdapter` (`MovementExecutor`, `ButtonTransactionExecutor`, `PointerStateManager`, `PointerHealthTracker`) | `MockPointerAdapter` | `READY` | `PRODUCTION_READY` (`LIVE_OS_VALIDATED`) |
| **Keyboard Control** | `KeyboardCapability` | `ProductionKeyboardAdapter` (`TextTypingExecutor`, `ShortcutExecutor`, `KeyboardStateManager`, `TargetFocusValidator`) | `MockKeyboardAdapter` | `READY` | `PRODUCTION_READY` (`LIVE_OS_VALIDATED`) |
| **Visual Observation** | `ObservationCapability` | `ProductionObservationAdapter` (`CaptureEngine`, `WindowTracker`, `AccessibilityCoordinator`, `CoordinateMapper`, `FreshnessTracker`) | `MockObservationAdapter` | `READY` | `PRODUCTION_READY` (`LIVE_OS_VALIDATED`) |
| **Human Takeover** | `HumanTakeoverCapability` | `ProductionHumanTakeoverAdapter` (`NativeInputMonitor`, `TakeoverStateManager`, `TakeoverAbiGate`, `TakeoverTelemetryLogger`) | `MockHumanTakeoverAdapter` | `READY` | `PRODUCTION_READY` (`LIVE_OS_VALIDATED`) |
| **Workspace / AppBar** | `WorkspaceCapability` | `ProductionWorkspaceAdapter` (`NativeAppBarDriver`, `WorkspaceStateManager`, `WorkspaceGeometryCoordinator`, `WorkspaceWatchdog`) | `MockWorkspaceAdapter` | `READY` | `PRODUCTION_READY` (`LIVE_OS_VALIDATED`) |
| **Safety Coordination** | `EmergencySafetyCoordinator` | `ProductionSafetyCoordinator` (Hardware release sanitizer across Pointer & Keyboard) | `MockSafetyCoordinator` | `READY` | `PRODUCTION_READY` (`LIVE_OS_VALIDATED`) |
| **Capability Registry** | `CapabilityRegistry` | Dynamic DI container with mode selection (`MOCK` vs `PRODUCTION`), per-capability overrides, and atomic lifecycle orchestration | N/A | `READY` | `PRODUCTION_READY` (`TEST_PROVEN`) |
| **Task Management** | `TaskManager` | In-memory task registry, status transitions, step indexing, cancellation tracking | N/A | `READY` | `PRODUCTION_READY` (`TEST_PROVEN`) |
| **Planning & Verification** | N/A | Hardcoded single-pass mock synthetic planner (`_build_synthetic_plan`) and immediate mock verifier | N/A | Stubbed | `MOCK_ONLY` / `NOT_IMPLEMENTED` |

---

## 3. End-to-End Execution Trace & Connection Audit

To assess autonomy readiness, we trace a complete hypothetical multi-step desktop task:
> *"Open Notepad, locate the text area, click it, type 'Hello ORBIT', verify the text appeared on screen, and recover safely if the desktop geometry reconfigures."*

```
Pipeline Stage                             Connection Status      Actual Implementation Reality
-----------------------------------------------------------------------------------------------------------------------------
1. User / Task Request                     CONNECTED              WebSocket / HTTP Gateway submits task payload cleanly.
2. Task Creation                           CONNECTED              TaskManager creates Task(status=CREATED).
3. Planning                                MOCK_ONLY              Orchestrator builds static dummy plan with fixed (500,300).
4. Execution Plan Creation                 CONNECTED              ExecutionPlan model encapsulates steps and actions.
5. Runtime Orchestrator Startup            CONNECTED              Orchestrator transitions system to BUSY, starts lifecycle.
6. Capability Resolution                   CONNECTED              Registry resolves typed production adapters.
7. Observation Capture                     PARTIALLY_CONNECTED    Calls obs.capture_screen(), but ignores rich snapshot metadata.
8. Target Interpretation                   MISSING                No visual locator translates "Notepad text area" to bounding box.
9. Coordinate Generation                   MISSING                Coordinates are hardcoded constants, not computed from UI elements.
10. Generation & Freshness Validation      MISSING_IN_LOOP        Orchestrator does not validate generation before dispatching action.
11. Synthetic Action Dispatch              CONNECTED              Pointer / Keyboard SendInput dispatches with dwExtraInfo signature.
12. Human Takeover Preemption              CONNECTED              Physical mouse/key input triggers immediate hook preemption.
13. Post-Action Observation                MISSING                Orchestrator does not capture post-action observation frame.
14. Visual / Semantic Verification         MOCK_ONLY              Hardcoded VerificationStatus.PASSED with confidence=1.0.
15. Dynamic Sense-Plan-Act Loop            MISSING                Linear single-pass execution without replanning or retry branches.
16. Task Completion / Failure              CONNECTED              Transitions task to COMPLETED or FAILED, emits events to EventBus.
```

---

## 4. The Autonomy Gap Analysis

The central finding of this audit is: **ORBIT has 6 world-class, production-ready, Win32-validated capability adapters, but the Runtime Orchestrator currently executes tasks via an open-loop, static single-pass dummy planner.**

### Prioritized Blocker List

| ID | Priority | Category | Affected Modules | Description & Safety Impact |
| :--- | :--- | :--- | :--- | :--- |
| **GAP-1** | **P0 — SAFETY BLOCKER** | Target Resolution & Coordinate Generation | `src/orbit/runtime/orchestrator.py`, `src/orbit/contracts/runtime.py` | **Blind Coordinate Dispatch:** Coordinates are hardcoded to fixed values (e.g. `(500, 300)`). No dynamic target locator resolves visual element intent to physical screen coordinates. Dispatching unverified coordinates can click arbitrary controls. |
| **GAP-2** | **P0 — SAFETY BLOCKER** | Generation Parity Enforcement | `src/orbit/runtime/orchestrator.py`, `src/orbit/adapters/workspace/` | **Missing Generation Validation in Action Loop:** Although `ProductionWorkspaceAdapter.validate_coordinate()` exists, the orchestrator does not invoke it before `pointer.move_to` / `pointer.click`. Reconfiguration during execution could click stale coordinates. |
| **GAP-3** | **P1 — CORE AUTONOMY** | Post-Action Verification | `src/orbit/runtime/orchestrator.py`, `src/orbit/contracts/runtime.py` | **Mock Action Verification:** `_execute_action()` hardcodes `VerificationStatus.PASSED` with `confidence=1.0` without capturing post-action screen state. ORBIT cannot know if a click opened a window or failed. |
| **GAP-4** | **P1 — CORE AUTONOMY** | Closed-Loop Iterative Execution | `src/orbit/runtime/orchestrator.py`, `src/orbit/runtime/task_manager.py` | **Absence of Sense-Plan-Act-Verify Loop:** The runtime plans all steps upfront in a linear sequence instead of iteratively observing, planning one step, acting, verifying outcome, and deciding the next step. |
| **GAP-5** | **P2 — RELIABILITY** | Bounded Retries & Focus Recovery | `src/orbit/runtime/orchestrator.py` | **No Action Retry Policy:** If an action fails verification (e.g. window takes 200ms to appear), the entire task fails immediately rather than retrying with bounded backoff. |
| **GAP-6** | **P2 — RELIABILITY** | Snapshot Underutilization | `src/orbit/adapters/observation/adapter.py`, `src/orbit/runtime/orchestrator.py` | **Raw JPEG vs Rich Snapshot:** `ProductionObservationAdapter.capture_snapshot()` provides MSAA/UIA accessibility elements, window bounding boxes, and ground-truth fusion, but the orchestrator only requests raw JPEG frames. |
| **GAP-7** | **P3 — HARDENING** | Target HWND Tracking | `src/orbit/runtime/orchestrator.py`, `src/orbit/adapters/keyboard/adapter.py` | **Unbound Keyboard Focus:** Keyboard `type_text` supports `target_hwnd` focus validation, but the orchestrator does not track active target HWNDs across steps. |

---

## 5. Cross-Capability Safety Matrix

```
Interaction Matrix          Existing Protection            Vulnerability / Race Risk          Required M1.6 Hardening
--------------------------------------------------------------------------------------------------------------------------------
Observation × Pointer       TTL Monotonic Freshness        Pointer dispatches on stale frame  Orchestrator enforces snapshot generation == workspace generation
Observation × Keyboard      TargetFocusValidator           Typing into shifted focus window   Orchestrator binds target_hwnd from observation snapshot
Workspace × Observation     desktop_generation_id Bump     Stale frame after dock resize      FreshnessEvaluator rejects stale frame (GENERATION_MISMATCH)
Workspace × Pointer         validate_coordinate Gate       Clicking inside reserved dock area Orchestrator gates all pointer dispatches via validate_coordinate()
Pointer × Takeover          Preemption Token + ExtraInfo   Pointer fighting human user        Low-level hook triggers immediate preemption & emergency_stop_all()
Keyboard × Takeover         KeyOwner.ORBIT Tracking        Typing fighting human user         Hook preempts typing; sanitizes only ORBIT-held modifier keys
Workspace × Takeover        is_takeover_active_fn Query    Watchdog fighting human for space  Watchdog suppresses recovery while takeover is active
Cancellation × Pointer/Kbd  CancellationToken Propagation  Late dispatch after cancellation   Pre- and post-dispatch cancellation checkpoints halt hardware
Runtime Shutdown × Native   registry.shutdown_all() Lock   Orphan HWNDs / hook threads        Deterministic shutdown order: cancel -> stop hooks -> unregister -> destroy
```

---

## 6. M1.6 Architectural Scope Options

### Option A: Closed-Loop Autonomous Execution Engine (RECOMMENDED)
- **Objective:** Transform ORBIT from a static single-pass action dispatcher into a true closed-loop autonomous desktop automation engine.
- **Core Additions:**
  1. Semantic visual target locator (`TargetLocator`) mapping UI elements to bounding boxes.
  2. Orchestrator coordinate validation gate (`workspace.validate_coordinate`) before dispatch.
  3. Post-action verification engine (`ActionVerifier`) inspecting visual diffs and focus state.
  4. Dynamic Sense-Plan-Act-Verify execution loop (`ExecutionStateMachine`) with bounded retries.
  5. Multi-step target HWND tracking and focus re-assertion.
- **Why Recommended:** Directly eliminates all P0 and P1 blockers, achieves genuine end-to-end task autonomy, and reuses all 6 production capability adapters without unnecessary refactoring.

### Option B: Static Plan Expansion with Semantic Target Locator
- **Objective:** Implement visual element target resolution into the existing static plan generator without post-action verification loops.
- **Flaw:** Leaves execution open-loop. In desktop environments where windows take variable milliseconds to render, open-loop execution fails frequently.

### Option C: Runtime Gateway Safety Hardening Only
- **Objective:** Add coordinate validation gates to the orchestrator, leaving autonomous planning and verification to external client scripts.
- **Flaw:** Does not advance ORBIT's autonomy capabilities; leaves the core mission incomplete.

---

## 7. Proposed M1.6 Atomic Implementation Roadmap

```
+-----------------------------------------------------------------------------------+
| M1.6 STEP 1: Semantic Target Resolution & Dynamic Coordinate Mapping Engine       |
| - TargetSelector & TargetLocator resolving visual/accessibility targets to BoundingBox|
| - Pre-dispatch Workspace Coordinate Gate validation (P0 Blocker Resolution)       |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| M1.6 STEP 2: Post-Action Visual & Semantic Verification Engine                    |
| - ActionVerifier capturing post-action ObservationSnapshot                        |
| - Visual change detection, accessibility property assertion, VerificationResult    |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| M1.6 STEP 3: Closed-Loop Sense-Plan-Act-Verify Execution Machine                  |
| - Iterative step execution loop with dynamic state progression                    |
| - Bounded action retry policies with backoff and focus re-assertion               |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| M1.6 STEP 4: Cross-Capability Autonomy Safety & Human Takeover Preemption        |
| - Full integration of generation parity, cancellation, and takeover preemption   |
| - Target HWND lifecycle tracking across multi-step plans                          |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| M1.6 STEP 5: End-to-End Autonomous Task Validation & Production Hardening         |
| - Multi-step E2E task execution test suite against live Windows applications     |
| - Full regression gates, frozen boundary verification, and final acceptance report |
+-----------------------------------------------------------------------------------+
```

---

## 8. Frozen Boundaries

The following prototype directories remain **PERMANENTLY FROZEN** relative to baseline commit `ca87ef8` (enforced via `git diff ca87ef8 -- prototypes/` = 0 lines diff):
1. `prototypes/prototype_a_workspace/`
2. `prototypes/prototype_b_human_takeover/`
3. `prototypes/prototype_c_keyboard/`
4. `prototypes/prototype_d_observation/`
5. `prototypes/prototype_e_pointer/`

---

## 9. Baseline Verification Evidence

- **Production Pytest Suite:** `260 passed in 4.42s` (100% Green)
- **Prototype A Suite:** `7/7 passed`
- **Prototype B Suite:** `10/10 passed`
- **Prototype C Suite:** `14/14 passed`
- **Prototype D Suite:** `15/15 passed`
- **Prototype E Suite:** `71/71 passed`
- **Frozen Diff:** `0 files modified, 0 lines diff` relative to `ca87ef8`

---

## 10. Audit Conclusion

Milestone M1.5 established complete, production-ready, Win32-hardened capability adapters across all 6 core subsystems. The path forward for Milestone M1.6 is clearly defined: **implement Option A (Closed-Loop Autonomous Execution Engine)** across 5 atomic steps to bridge the planning and verification gaps, enabling safe, verified, multi-step desktop task execution.
