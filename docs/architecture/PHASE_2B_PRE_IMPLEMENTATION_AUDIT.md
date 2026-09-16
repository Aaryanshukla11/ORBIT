# ORBIT — Phase 2B Pre-Implementation Audit Report
**Intent → Action Routing + Reliable File Actions**

---

## 1. Executive Summary
This pre-implementation audit documents the execution path, component interactions, and root causes of failure modes observed during Phase 1.6 real-desktop evaluation:
1. **"Open Edge" Failure**: Natural language intent `"Open Edge"` failed to route to `LAUNCH_APPLICATION` and fell through to UI element target resolution.
2. **"Save As test.png" Failure**: Paint drawing succeeded, but downstream file persistence (`"save it as test.png on Desktop"`) did not reliably execute or create `Desktop/test.png`.

This document identifies minimal, non-breaking architectural enhancements within the existing ORBIT execution pipeline to make intent routing and file persistence deterministic without introducing out-of-scope model-first or brain redesigns.

---

## 2. End-to-End Execution Call Graph
The current runtime execution path from user prompt to goal completion is:

```
User Prompt ("Open Paint, draw a red circle, and save it as test.png on the Desktop")
   │
   ▼
[OrbitOrchestrator.execute_goal()]
   │
   ├─► [GoalVerifier.decompose_goal()]
   │      └── Decomposes prompt into SubgoalRequirements (LAUNCH, DRAW, SAVE)
   │
   ▼
[CognitiveDecisionEngine.decide_next_step() / AgentDecisionEngine]
   │
   ├─► [AgentPlanner.generate_candidate_plans()]
   │      └── Evaluates prompt context & decomposes into ActionSpec candidates
   │
   ├─► [PrimitiveComposer.compose_from_decision()]
   │      └── Maps ActionSpec → Canonical ExecutionPrimitive
   │
   ├─► [PrimitiveValidator.validate()]
   │      └── Validates target parameters, coordinate bounds, action safety
   │
   ▼
[PrimitiveExecutionController.dispatch_physical_action()]
   │
   ├─► Action Type: LAUNCH_APPLICATION ──► [ApplicationLauncher.launch_and_verify()]
   │                                         └── Native Win32 / Shell launch & focus check
   │
   ├─► Action Type: DRAW ────────────────► [CanvasDrawingProvider / PointerAdapter]
   │                                         └── Physical stroke injection
   │
   ├─► Action Type: SAVE_FILE ───────────► [SaveFileWorkflow / KeyboardAdapter / PointerAdapter]
   │                                         └── UI dialog handling, path typing, commit
   │
   ▼
[MultiEvidenceActionVerifier.verify_execution()]
   │  └── Verifies immediate step evidence (window focus, canvas diff, artifact on disk)
   │
   ▼
[GoalVerifier.verify_goal_satisfaction()]
   │  └── Evaluates all SubgoalRequirements with evidence & provenance
   │
   ▼
Result Status (COMPLETE only if ALL requirements are satisfied)
```

---

## 3. Relevant Files and Classes

| Layer | Files | Key Classes / Components |
|---|---|---|
| **Contracts & Action Models** | `src/orbit/runtime/agent/contracts.py` | `AbstractActionType`, `ActionSpec`, `ExecutionPrimitive` |
| **Goal & Requirement Decomposition** | `src/orbit/runtime/task_completion/goal_verifier.py` | `GoalVerifier`, `SubgoalRequirement`, `RequirementType` |
| **Application Management** | `src/orbit/runtime/capabilities/application_launcher.py` | `ApplicationLauncher`, `APPROVED_APPLICATION_REGISTRY` |
| **Planning & Intent Routing** | `src/orbit/runtime/cognitive/agent_planner.py`<br>`src/orbit/runtime/cognitive/primitive_composer.py` | `AgentPlanner`, `PrimitiveComposer` |
| **Validation** | `src/orbit/runtime/cognitive/primitive_validator.py` | `PrimitiveValidator` |
| **Execution Pipeline** | `src/orbit/runtime/cognitive/primitive_execution_controller.py` | `PrimitiveExecutionController` |
| **Adapters & Providers** | `src/orbit/runtime/adapters/keyboard.py`<br>`src/orbit/runtime/capabilities/canvas_drawer.py` | `KeyboardAdapter`, `CanvasDrawingProvider` |
| **Action & Artifact Verification** | `src/orbit/runtime/task_completion/multi_evidence_verifier.py`<br>`src/orbit/runtime/task_completion/artifact_verifier.py` | `MultiEvidenceActionVerifier`, `ArtifactVerifier` |

---

## 4. Root Cause Analysis

### Root Cause A: "Open Edge" Launch Failure
1. **Hardcoded Application Whitelist in Planner**:
   In `src/orbit/runtime/cognitive/agent_planner.py` (`AgentPlanner.generate_candidate_plans()`), application name matching checked only a static tuple `("notepad", "paint", "calculator", "calc", "word", "excel", "browser")`. `"edge"` and `"msedge"` were absent.
2. **Fallback to Visual Target Locator**:
   Because `"edge"` was not matched in the application launching branch, candidate generation fell through to generic UI element interaction (`CLICK`), assigning `control_name="Edge"`. `TargetLocator` then attempted to ground a nonexistent button named `"Edge"`.
3. **Registry Gaps in `application_launcher.py`**:
   `APPROVED_APPLICATION_REGISTRY` lacked explicit mappings for `"edge"` and `"chrome"`.

### Root Cause B: "Save As test.png" Execution Failure
1. **Missing Canonical `SAVE_FILE` Action Type**:
   `AbstractActionType` contained `FILE_WRITE` (intended for background filesystem APIs), but lacked a first-class `SAVE_FILE` action type for desktop GUI application file persistence.
2. **Missing Save Decomposition in Planner & Composer**:
   `AgentPlanner.generate_candidate_plans()` and `PrimitiveComposer` lacked candidate generation logic for save actions, causing file saving instructions to fall through to generic clicks or unhandled actions.
3. **Lack of Desktop Save Workflow in Execution Controller**:
   `PrimitiveExecutionController.dispatch_physical_action()` had no workflow to handle Windows Save / Save As dialogs (e.g., sending `Ctrl+S`, waiting for the modal dialog, typing the absolute target path into the file dialog, pressing Enter, handling overwrite confirmations, and verifying file creation).

---

## 5. Proposed Minimal Architecture Changes

1. **Extend `AbstractActionType`**:
   - Add `SAVE_FILE = "SAVE_FILE"` to `AbstractActionType` in `src/orbit/runtime/agent/contracts.py`.
   - Add `SAVE_FILE` to `TIER1_COMPUTER_PRIMITIVES`.
2. **Expand Application Registry**:
   - Add `"edge": "msedge.exe"`, `"msedge": "msedge.exe"`, `"browser": "msedge.exe"`, `"chrome": "chrome.exe"`, `"wordpad": "write.exe"`, `"word": "winword.exe"`, `"excel": "excel.exe"` to `APPROVED_APPLICATION_REGISTRY`.
3. **Enhance Semantic Routing in `AgentPlanner` & `PrimitiveComposer`**:
   - In `AgentPlanner.generate_candidate_plans()`:
     - Match general launch verbs (`open`, `launch`, `start`, `run`) against the application registry and aliases.
     - Detect file save intent (`save`, `save as`, `export`) and extract target path / filename, proposing `AbstractActionType.SAVE_FILE`.
   - In `PrimitiveComposer`:
     - Compose `ExecutionPrimitive` for `AbstractActionType.SAVE_FILE` with `target_path`, `filename`, `format`, and fallback parameters.
4. **Implement Save Execution Workflow in `PrimitiveExecutionController`**:
   - In `PrimitiveExecutionController._dispatch_save_file()`:
     - Send `Ctrl+S` (or application-specific save hotkey) to the active window via `KeyboardAdapter`.
     - Allow dialog focus settlement.
     - Type the target filepath into the active file dialog.
     - Press `Enter` to commit save.
     - If overwrite prompt appears, confirm it.
     - Physically verify file presence on disk and check non-zero file size.
5. **Action Verification & Provenance**:
   - In `MultiEvidenceActionVerifier`:
     - Add verification branch for `SAVE_FILE` requiring target file presence, write timestamp after step start, and non-empty artifact content.

---

## 6. Test Plan (Proving Each Fix)

| Test ID | Objective | Verification Method |
|---|---|---|
| **TEST 1** | `"Open Edge"` routes to `LAUNCH_APPLICATION` | Unit test in `test_phase2b_routing_and_save.py` |
| **TEST 2** | `"Open Paint"` routes to `LAUNCH_APPLICATION` | Unit test in `test_phase2b_routing_and_save.py` |
| **TEST 3** | `"click the search box"` routes to `CLICK` (UI element) | Unit test verifying target type is `UI_ELEMENT` |
| **TEST 4** | `"Type hello"` routes to `TYPE_TEXT` | Unit test verifying action type is `TYPE_TEXT` |
| **TEST 5** | `"Save as test.png on Desktop"` routes to `SAVE_FILE` with path | Unit test verifying resolved `target_path` and `filename` |
| **TEST 6** | Save action requires post-action physical evidence | Mock test proving keyboard dispatch alone does not mark success |
| **TEST 7** | Artifact verification validates file existence and validity | Test ensuring `ArtifactVerifier` checks validity & non-empty content |
| **TEST 8** | Multi-requirement task (draw verified + save pending) is `INCOMPLETE` | Phase 2A regression test in `test_multi_requirement_verification.py` |
| **TEST 9** | Multi-requirement task (draw verified + save verified) is `COMPLETE` | Unit test verifying full satisfaction transitions to `COMPLETE` |
| **TEST 10** | Existing Phase 2A test suite remains 100% green | `pytest tests/unit/test_multi_requirement_verification.py` |
| **Real E2E** | Live desktop acceptance on Windows with Paint | Real execution creating `Desktop/test.png` autonomously |
