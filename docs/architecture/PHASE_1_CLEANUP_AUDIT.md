# ORBIT — Phase 1: Forensic Cleanup & Safe Pruning Audit
**Document ID:** `ORBIT-ARCH-PHASE1-AUDIT-2026`  
**Date:** 2026-09-14  
**Status:** VALIDATED FORENSIC REPORT  
**Target Architecture:** Canonical Closed-Loop Autonomous Computer-Agent Runtime (ORBIT V2 Readiness)  

---

## 1. Executive Summary & Forensic Audit Mandate

This document establishes the authoritative forensic audit for **Phase 1: Forensic Cleanup & Safe Pruning** of the ORBIT repository. In accordance with the non-negotiable architectural rules:
- **No redesign or speculative refactoring** has been performed.
- **Every candidate file and directory** was systematically analyzed across static imports, dynamic `sys.path` lookups, unit/integration test suites, entry points, configuration manifests, and production runtime call graphs.
- **Safety First Invariant**: If a component is reachable or its retirement risk is non-zero, it is marked `KEEP — PROVEN`, `KEEP — FOUNDATION`, or `REFACTOR — DEFERRED`. Only proven dead, obsolete, or unreferenced assets are slated for `DELETE` or `ARCHIVE`.

```
                         ORBIT AUTHORITATIVE EXECUTION TOPOLOGY
                         
      ┌──────────────────────────────────────────────────────────────────┐
      │          FastAPI / WebSocket Gateway (app.py, protocol.py)       │
      └────────────────────────────────┬─────────────────────────────────┘
                                       │
                                       ▼
      ┌──────────────────────────────────────────────────────────────────┐
      │        OrbitOrchestrator (src/orbit/runtime/orchestrator.py)     │
      └────────────────────────────────┬─────────────────────────────────┘
                                       │
                                       ▼
      ┌──────────────────────────────────────────────────────────────────┐
      │     AgentExecutionLoop (src/orbit/runtime/cognitive/agent_loop)  │
      ├────────────────────────────────┬─────────────────────────────────┤
      │  Planning & Reasoning:         │  Physical Gated Dispatch:       │
      │  - HierarchicalGoalDecomposer  │  - PlanDirective                │
      │  - ProgressGraph               │  - PrimitiveComposer            │
      │  - RuntimeFeasibility          │  - PrimitiveValidator           │
      │  - AgentPlanner                │  - PrimitiveExecutionController │
      │  - SemanticFeasibility         │         │                       │
      │  - ClarificationManager        │         ▼                       │
      │  - DecisionEngine (Agent / Cog)│    Capability Adapters / Provs  │
      ├────────────────────────────────┴─────────────────────────────────┤
      │  Perception & Multi-Channel Evidence Grounding:                  │
      │  - DesktopObserver (Win32, UIA, OCR, Vision)                     │
      │  - EvidenceBasedTargetLocator + GroundingValidator               │
      │  - VLMGroundingVerifier (Strict semantic boundary)               │
      ├──────────────────────────────────────────────────────────────────┤
      │  Verification & Memory Lifecycle:                                │
      │  - MultiEvidenceActionVerifier (Step Delta Contract)             │
      │  - GoalVerifier (Task-Level Independent Verification)            │
      │  - TaskScopedMemory (Wiped & Zeroized upon task exit)            │
      └──────────────────────────────────────────────────────────────────┘
```

---

## 2. In-Depth Forensic Investigation Areas

### 2.1. Prototype → Production Coupling

#### Forensic Tracing:
1. **Source Code Check**: `src/orbit/adapters/observation/adapter.py` (lines 71–74):
   ```python
   proto_d_dir = str(Path(__file__).resolve().parents[4] / "prototypes" / "prototype_d_observation")
   if proto_d_dir not in sys.path:
       sys.path.insert(0, proto_d_dir)
   from coordinate_mapper import CoordinateMapper
   from capture_engine import CaptureEngine
   from window_tracker import WindowTracker
   from accessibility_coordinator import AccessibilityCoordinator
   from freshness_tracker import FreshnessTracker
   ```
2. **Other Prototypes**:
   - `prototypes/prototype_a_workspace/`: **0 references** in `src/`.
   - `prototypes/prototype_b_human_takeover/`: **0 references** in `src/`.
   - `prototypes/prototype_c_keyboard/`: **0 references** in `src/`.
   - `prototypes/prototype_e_pointer/`: **0 references** in `src/`.
3. **Configuration Check**: `pyproject.toml` and `pyrightconfig.json` include `extraPaths` for all 5 prototypes.
4. **Test Suite Check**: `tests/unit/test_observation_mapper.py` imports `prototypes.prototype_d_observation.app_types`.

#### Decision & Migration Path:
- `prototypes/prototype_d_observation/` **MUST NOT be deleted in Phase 1** because `ProductionObservationAdapter` actively instantiates its internal engines (`CoordinateMapper`, `CaptureEngine`, `WindowTracker`, `AccessibilityCoordinator`, `FreshnessTracker`).
- `src/orbit/runtime/perception/` already possesses native Win32/UIA/OCR implementations (`Win32WindowObserver`, `UIAElementObserver`, `DesktopScreenshotObserver`).
- **Classification**: `prototypes/prototype_d_observation/` -> **`KEEP — FOUNDATION`** (until clean native migration in Phase 2). Prototypes A, B, C, E -> **`ARCHIVE`**.

---

### 2.2. AI Model Subsystems Triplicate Investigation

The codebase contains 3 distinct packages under `src/orbit/runtime/`:
1. `src/orbit/runtime/models/` (12 files)
2. `src/orbit/runtime/model_providers/` (5 files)
3. `src/orbit/runtime/model_runtime/` (6 files + 3 provider adapters)

#### Forensic Dependency Graph:
- **`runtime/models/`**: Defines data models (`ModelDescriptor`, `ModelCapability`, `ModelGenerateRequest`), model catalog (`ModelRegistry`), discovery engine (`ModelDiscoveryEngine`), inventory scanner (`ModelInventoryEngine`), and lifecycle manager (`ModelLifecycleManager`).
- **`runtime/model_providers/`**: Concrete network/HTTP drivers connecting to backend engines: `OllamaProvider` (11434), `LMStudioProvider` (1234), `CloudModelProvider` (OpenAI, Anthropic, Gemini).
- **`runtime/model_runtime/`**: Runtime execution session manager (`ModelSessionManager`), dynamic multi-model prompt router (`ModelRouter`), and abstract runtime instances (`LocalModelRuntime`, `RemoteModelRuntime`, `MockModelRuntime`).

#### Forensic Findings:
- **These are NOT duplicate/redundant implementations.** They represent 3 functional tiers of the Model Subsystem:
  - Layer 1: Discovery & Catalog (`models/`)
  - Layer 2: Driver / Protocol Adapters (`model_providers/`)
  - Layer 3: Session Lifecycle & Routing Engine (`model_runtime/`)
- `OrbitOrchestrator` initializes `ModelManager` (catalog/discovery) and `ModelSessionManager` (execution sessions).
- **Classification**: All 3 packages -> **`KEEP — FOUNDATION`** / **`REFACTOR — DEFERRED`** (Consolidation into `orbit.runtime.models` is scheduled for a dedicated model-system phase).

---

### 2.3. Decision Engines: `CognitiveDecisionEngine` vs `AgentDecisionEngine`

#### Forensic Tracing:
1. `src/orbit/runtime/cognitive/engine.py` (`CognitiveDecisionEngine`):
   - Implements `decide_next_step(observation, objective, history) -> CognitiveDecision`.
   - Uses hardcoded string prompt templates (`DECISION_SYSTEM_PROMPT`) and regex-based JSON extraction.
   - **Production Reachability**: `AgentExecutionLoop.__init__` instantiates `self._decision_engine = decision_engine or CognitiveDecisionEngine(model_session_manager=model_session_manager)`.
   - **Test Callers**: `test_cognitive_decision_engine.py`, `test_agent_execution_loop.py`, `test_capability_aware_agent_loop.py`.
2. `src/orbit/runtime/cognitive/agent_decision.py` (`AgentDecisionEngine`):
   - Implements `decide_next_step(observation, objective, history) -> CognitiveDecision`.
   - Employs modular architecture: `AgentReasoningContextBuilder`, `StructuredDecisionParser`, `ModelRouter`.
   - **Test Callers**: `test_step4_decision_brain.py`, `test_astra6_architecture_invariants.py`.

#### Forensic Findings:
- Both engines are active and conform to the same `decide_next_step` interface.
- Deleting `engine.py` without updating `AgentExecutionLoop.__init__` would break default execution.
- **Classification**: `engine.py` -> **`KEEP — FOUNDATION`** / **`REFACTOR — DEFERRED`**; `agent_decision.py` -> **`KEEP — PROVEN`**.

---

### 2.4. Verification Systems Forensic Analysis

#### Forensic Distinction: Step Verification vs Goal Verification
```
                ┌────────────────────────────────────────────────────────┐
                │             AgentExecutionLoop Execution Step          │
                └───────────────────────────┬────────────────────────────┘
                                            │
               [Physical Action Dispatched via PrimitiveExecutionController]
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │      STEP / ACTION TRANSITION VERIFICATION    │
                    │   (Evaluates atomic state delta per step)     │
                    │   - MultiEvidenceActionVerifier               │
                    │   - AgentStateTransitionVerifier              │
                    └───────────────────────┬───────────────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │       TASK / GOAL LEVEL VERIFICATION          │
                    │   (Evaluates overall user goal completion)    │
                    │   - GoalVerifier                              │
                    └───────────────────────────────────────────────┘
```

1. **`src/orbit/runtime/task_completion/multi_evidence_verifier.py` (`MultiEvidenceActionVerifier`)**:
   - **Role**: Step-level verification evaluating UI Automation changes, OCR token appearance, window focus transitions, and canvas delta against `ActionOutcomeContract`.
   - **Status**: **`KEEP — PROVEN`** (Authoritative Step Verifier).
2. **`src/orbit/runtime/task_completion/goal_verifier.py` (`GoalVerifier`)**:
   - **Role**: Independent task-level verifier assessing whether the end condition of the entire user objective has been achieved.
   - **Status**: **`KEEP — PROVEN`** (Authoritative Goal Verifier).
3. **`src/orbit/runtime/agent/verifier.py` (`AgentStateTransitionVerifier`)**:
   - **Role**: Validates state delta transitions between pre- and post-desktop snapshots in `agent_loop.py`.
   - **Status**: **`KEEP — PROVEN`**.
4. **`src/orbit/runtime/verification/` (`ActionVerifier`, `strategies.py`)**:
   - **Role**: Milestone M1.6 Step 2 legacy verification strategies.
   - **Reachability**: Imported as an optional argument in `OrbitOrchestrator.__init__` and referenced in 3 test suites (`test_action_verification.py`, `test_post_action_verification.py`, `test_action_verification_flow.py`).
   - **Status**: **`KEEP — FOUNDATION`** / **`REFACTOR — DEFERRED`** (Preserved to prevent test regression).

---

### 2.5. Production Re-export Shims (`src/orbit/adapters/production/`)

#### Forensic Tracing:
1. `src/orbit/adapters/production/production_safety.py`:
   - Contains full implementation of `ProductionSafetyCoordinator` (77 lines).
   - Instantiated by `src/orbit/adapters/factory.py` and `OrbitOrchestrator`.
   - **Decision**: **`KEEP — PROVEN`**.
2. Compatibility Aliases:
   - `production_keyboard.py` (re-exports `ProductionKeyboardAdapter`)
   - `production_observation.py` (re-exports `ProductionObservationAdapter`)
   - `production_pointer.py` (re-exports `ProductionPointerAdapter`)
   - `production_takeover.py` (re-exports `ProductionHumanTakeoverAdapter`)
   - `production_workspace.py` (re-exports `ProductionWorkspaceAdapter`)
   - **Decision**: **`KEEP — FOUNDATION`** / **`REFACTOR — DEFERRED`** (Used by `factory.py`, `test_production_adapters.py`, `test_adapter_modes.py`).

---

### 2.6. Frontend UI Architecture Audit

#### Forensic Tracing:
1. `frontend/package.json`: Configures React 18, Vite 6, and Electron (`main: electron/main.cjs`).
2. `frontend/index.html`: Mounts React application root (`<script type="module" src="/src/main.tsx"></script>`).
3. `frontend/electron/`: Production Electron runner (`dev-runner.cjs`), main window manager (`main.cjs`), and preload bridge (`preload.cjs`).
4. `frontend/src/`: Modern React 18 + TypeScript application with 9 Context providers, 8 full-page views, and WebSocket client.
5. `frontend/app.js` & `frontend/styles.css`:
   - "ORBIT Milestone M0 Developer Console Client".
   - 0 imports, 0 callers, 0 runtime connections.
   - **Decision**: **`DELETE`**.
6. Empty directories: `frontend/src/services/api/`, `frontend/src/hooks/` -> **`DELETE`** (empty folders).

---

## 3. Detailed Disposition Dossier for DELETE / ARCHIVE Candidates

### Candidate 1: `frontend/app.js`
- **Path:** `frontend/app.js`
- **Category:** `DELETE`
- **Why obsolete:** Milestone M0 developer console DOM script. Completely superseded by React 18 frontend in `frontend/src/`.
- **Who imports it:** None (0 references in codebase).
- **Who calls it:** None. `frontend/index.html` loads `/src/main.tsx`.
- **Tests referencing it:** None.
- **Runtime reachability:** 0% unreachable.
- **Replacement:** `frontend/src/services/websocket/OrbitWebSocketClient.ts` + `frontend/src/context/TaskConsoleContext.tsx`.
- **Risk:** Zero.
- **Decision:** **DELETE**.

---

### Candidate 2: `frontend/styles.css`
- **Path:** `frontend/styles.css`
- **Category:** `DELETE`
- **Why obsolete:** Milestone M0 static CSS stylesheet.
- **Who imports it:** None (0 references).
- **Who calls it:** None.
- **Tests referencing it:** None.
- **Runtime reachability:** 0% unreachable.
- **Replacement:** `frontend/src/styles/tokens.css` + `frontend/src/styles/index.css`.
- **Risk:** Zero.
- **Decision:** **DELETE**.

---

### Candidate 3: Root PNG Image Dumps (6 files)
- **Path:** `captured_desktop.png`, `captured_notepad.png`, `child_typed_notepad.png`, `printwindow_notepad.png`, `test_text.png`, `typed_notepad.png`
- **Category:** `DELETE`
- **Why obsolete:** Temporary debug screenshot dumps generated during local test runs.
- **Who imports it:** None.
- **Who calls it:** None.
- **Tests referencing it:** None.
- **Runtime reachability:** 0% unreachable.
- **Replacement:** Dynamic memory screenshots in `ObservationSnapshot`.
- **Risk:** Zero.
- **Decision:** **DELETE**.

---

### Candidate 4: Root Excel & Temporary Logs (4 files)
- **Path:** `verdict.xlsx`, `~$verdict.xlsx`, `acceptance_test_results.json`, `test_results_phase_abcdfg.txt`
- **Category:** `DELETE`
- **Why obsolete:** One-off evaluation test dumps and lock files from historical audit runs.
- **Who imports it:** None.
- **Who calls it:** None.
- **Tests referencing it:** None.
- **Runtime reachability:** 0% unreachable.
- **Replacement:** `orbit.runtime.history.ExecutionHistoryStore` (SQLite).
- **Risk:** Zero.
- **Decision:** **DELETE**.

---

### Candidate 5: Root Scratch Scripts (15 files)
- **Path:** `scratch_debug_verifier.py`, `scratch_inspect_ocr.py`, `scratch_reproduce_failure.py`, `scratch_test_child_typing.py`, `scratch_test_click_type.py`, `scratch_test_focus.py`, `scratch_test_live_verifier.py`, `scratch_test_obs_ocr.py`, `scratch_test_ocr.py`, `scratch_test_paint_launch.py`, `scratch_test_paint_launch2.py`, `scratch_test_printwindow.py`, `scratch_test_synthetic_ocr.py`, `scratch_test_typing.py`, `scratch_test_typing_printwindow.py`
- **Category:** `ARCHIVE`
- **Why obsolete:** Ad-hoc manual triage scripts from earlier milestone development.
- **Who imports it:** None.
- **Who calls it:** None.
- **Tests referencing it:** None.
- **Runtime reachability:** 0% unreachable.
- **Replacement:** Canonical test suite under `tests/unit/`, `tests/integration/`, `tests/live/`.
- **Risk:** Zero.
- **Decision:** **ARCHIVE** (Move to `archive/root_scratch/`).

---

### Candidate 6: `scratch/` Directory (103 files)
- **Path:** `scratch/`
- **Category:** `ARCHIVE`
- **Why obsolete:** 103 one-off investigation scripts from Milestones M1.1 through M1.9.
- **Who imports it:** None of the production `src/` modules import from `scratch/`.
- **Who calls it:** None in CI/CD or production runtime.
- **Tests referencing it:** None in `tests/`.
- **Runtime reachability:** 0% unreachable.
- **Replacement:** Canonical automated tests in `tests/`.
- **Risk:** Zero.
- **Decision:** **ARCHIVE** (Move to `archive/scratch/`).

---

### Candidate 7: Prototypes A, B, C, E
- **Path:** `prototypes/prototype_a_workspace/`, `prototypes/prototype_b_human_takeover/`, `prototypes/prototype_c_keyboard/`, `prototypes/prototype_e_pointer/`
- **Category:** `ARCHIVE`
- **Why obsolete:** Completed milestone R&D prototypes. Production capabilities are self-contained in `src/orbit/adapters/`.
- **Who imports it:** 0 references in `src/`.
- **Who calls it:** None in production.
- **Tests referencing it:** Only prototype-internal test suites inside each prototype directory.
- **Runtime reachability:** 0% unreachable.
- **Replacement:** `src/orbit/adapters/workspace/`, `src/orbit/adapters/takeover/`, `src/orbit/adapters/keyboard/`, `src/orbit/adapters/pointer/`.
- **Risk:** Zero.
- **Decision:** **ARCHIVE** (Move to `archive/prototypes/`).

---

## 4. Master File-by-File Disposition Matrix

| Subsystem / Path | Files | Classification | Action in Phase 1 |
| :--- | :---: | :---: | :--- |
| **`src/orbit/adapters/base.py`, `factory.py`** | 2 | **KEEP — PROVEN** | Retain |
| **`src/orbit/adapters/keyboard/`** | 9 | **KEEP — PROVEN** | Retain |
| **`src/orbit/adapters/mocks/`** | 7 | **KEEP — PROVEN** | Retain |
| **`src/orbit/adapters/observation/`** | 6 | **KEEP — FOUNDATION** | Retain (Refactor prototype dependency in Phase 2) |
| **`src/orbit/adapters/pointer/`** | 8 | **KEEP — PROVEN** | Retain |
| **`src/orbit/adapters/production/`** | 7 | **KEEP — FOUNDATION** | Retain (`production_safety.py` is active; re-exports preserved) |
| **`src/orbit/adapters/takeover/`** | 7 | **KEEP — PROVEN** | Retain |
| **`src/orbit/adapters/workspace/`** | 10 | **KEEP — PROVEN** | Retain |
| **`src/orbit/contracts/`** | 6 | **KEEP — PROVEN** | Retain |
| **`src/orbit/gateway/`** | 5 | **KEEP — PROVEN** | Retain |
| **`src/orbit/infrastructure/`** | 3 | **KEEP — PROVEN** | Retain |
| **`src/orbit/models/`** | 2 | **KEEP — PROVEN** | Retain |
| **`src/orbit/runtime/agent/`** | 7 | **KEEP — PROVEN** | Retain |
| **`src/orbit/runtime/capabilities/`** | 5 | **KEEP — PROVEN** | Retain |
| **`src/orbit/runtime/cognitive/`** | 22 | **KEEP — PROVEN** | Retain (`engine.py` preserved for default loop stability) |
| **`src/orbit/runtime/diagnostics/`** | 3 | **KEEP — PROVEN** | Retain |
| **`src/orbit/runtime/environment/`** | 9 | **KEEP — PROVEN** | Retain |
| **`src/orbit/runtime/history/`** | 3 | **KEEP — PROVEN** | Retain |
| **`src/orbit/runtime/memory/`** | 2 | **KEEP — PROVEN** | Retain |
| **`src/orbit/runtime/model_providers/`**| 5 | **KEEP — FOUNDATION** | Retain (Consolidation deferred) |
| **`src/orbit/runtime/model_runtime/`**  | 9 | **KEEP — FOUNDATION** | Retain (Consolidation deferred) |
| **`src/orbit/runtime/models/`**         | 12 | **KEEP — FOUNDATION** | Retain (Consolidation deferred) |
| **`src/orbit/runtime/perception/`**     | 16 | **KEEP — PROVEN** | Retain |
| **`src/orbit/runtime/targeting/`**      | 4 | **KEEP — PROVEN** | Retain |
| **`src/orbit/runtime/task_completion/`**| 5 | **KEEP — PROVEN** | Retain |
| **`src/orbit/runtime/verification/`**   | 7 | **KEEP — FOUNDATION** | Retain (Legacy test suite dependency) |
| **`src/orbit/runtime/world_model/`**    | 3 | **KEEP — PROVEN** | Retain |
| **`src/orbit/runtime/orchestrator.py`** | 1 | **KEEP — PROVEN** | Retain |
| **`src/orbit/runtime/cancellation.py`** | 1 | **KEEP — PROVEN** | Retain |
| **`src/orbit/runtime/state_machine.py`**| 1 | **KEEP — PROVEN** | Retain |
| **`src/orbit/runtime/task_manager.py`** | 1 | **KEEP — PROVEN** | Retain |
| **`frontend/src/` & `frontend/electron/`**| 60+ | **KEEP — PROVEN** | Retain React 18 + TypeScript + Electron UI |
| **`frontend/app.js`, `styles.css`**     | 2 | **DELETE** | Remove obsolete M0 scripts |
| **`frontend/src/services/api/`, `hooks/`**| 2 | **DELETE** | Remove empty directories |
| **Root Image Dumps (`.png`)**           | 6 | **DELETE** | Remove test artifacts |
| **Root Spreadsheets / Test Dumps**      | 4 | **DELETE** | Remove test outputs |
| **Root Scratch Scripts (`scratch_*.py`)**| 15 | **ARCHIVE** | Move to `archive/root_scratch/` |
| **`scratch/` Directory**                | 103 | **ARCHIVE** | Move to `archive/scratch/` |
| **`prototypes/prototype_a, b, c, e`**   | 80+ | **ARCHIVE** | Move to `archive/prototypes/` |
| **`prototypes/prototype_d_observation/`**| 20 | **KEEP — FOUNDATION** | Retain until Phase 2 adapter migration |
| **`docs/architecture/`**                | 7 | **KEEP — PROVEN** | Retain specifications |
| **`docs/` Milestone Reports**          | 80+ | **ARCHIVE** | Move to `archive/docs/milestones/` |
| **`tests/`**                            | 150+| **KEEP — PROVEN** | Retain full test suite |

---

## 5. Phase 1 Execution Checklist

1. [x] Comprehensive static import & dynamic path analysis.
2. [x] Publish `docs/architecture/PHASE_1_CLEANUP_AUDIT.md`.
3. [ ] Safely delete confirmed dead files (`frontend/app.js`, `frontend/styles.css`, root temporary PNGs, Excel dumps, and test output logs).
4. [ ] Clean empty frontend directories (`frontend/src/services/api/`, `frontend/src/hooks/`).
5. [ ] Archive non-production scratch scripts and legacy prototypes (Prototypes A, B, C, E) into `archive/`.
6. [ ] Preserve all working production code, test suites, and model/decision/verification foundations untouched.
