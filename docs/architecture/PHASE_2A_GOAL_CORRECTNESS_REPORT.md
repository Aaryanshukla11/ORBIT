# ORBIT — PHASE 2A ARCHITECTURAL COMPLETION & GOAL CORRECTNESS REPORT
**Milestone:** Phase 2A: Goal State & GoalVerifier Correctness  
**Date:** September 15, 2026  
**Status:** COMPLETE  

---

## 1. Baseline Behavior

In Phase 1.6 real desktop E2E testing, the task:
> *"Open Paint, draw a red circle, and save it as test.png on the Desktop."*

exhibited a critical premature completion failure:
- Paint opened and a stroke/circle was drawn on the canvas.
- At Cycle 2, `GoalVerifier.verify_goal_achievement()` evaluated the goal as satisfied because:
  1. `GoalRequirementExtractor` only parsed the `APP_LIFECYCLE` (Paint running) and `CANVAS_INTERACTION` (drawing strokes) requirements. It completely dropped the `FILE_MANAGEMENT` / save requirement from the requirement set.
  2. `GoalVerifier` only checked `has_app_evidence` and `canvas_modified` (which were both True), marked all extracted requirements satisfied, and returned `TaskCompletionStatus.COMPLETED` (`is_completed=True`).
- `AgentExecutionLoop` received `goal_eval.is_satisfied=True` and immediately terminated execution with `final_status=COMPLETED` and `is_success=True`.
- `Desktop/test.png` did NOT exist on disk.
- The task was falsely declared successful despite 1 of its 3 essential goals being completely unfulfilled.

---

## 2. Root Cause Analysis

Forensic inspection across `src/orbit/runtime/` revealed three compounding defects:

1. **Deficient Goal Decomposition (`GoalRequirementExtractor` in `requirements.py`)**:
   - `GoalRequirementExtractor._extract_explicit_requirements()` had extractors for App Lifecycle, Arithmetic Calculation, and Canvas, but no rule to extract `FILE_MANAGEMENT` requirements across file persistence operations (`save`, `export`, `persist`, target paths/formats).
   - Consequently, the requirement set generated for the multi-step prompt was missing the save requirement entirely.

2. **Missing Grounded File Verification & Provenance Checks (`GoalVerifier` in `goal_verifier.py`)**:
   - `GoalVerifier` lacked filesystem evidence verification. Even if a file management requirement were present, it had no mechanism to inspect the actual target path (`Desktop/test.png`), check file existence, non-zero file size, validate image headers via PIL, or check file modification timestamps against task start time to prove execution provenance.

3. **Weak Goal Invariant & Fragmented Lifecycle State (`models.py` & `goal_verifier.py`)**:
   - `GoalRequirement` lacked structured lifecycle integration with ORBIT's canonical `SubgoalStatus` (`PENDING`, `READY`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `BLOCKED`, `SKIPPED`).
   - `GoalRequirementSet` lacked invariant enforcement to verify that **all** mandatory requirements are independently satisfied and verified before returning task completion.

---

## 3. Files & Functions Changed

### A. Goal & Requirement Models
- **`src/orbit/runtime/capabilities/models.py`**:
  - Unified requirement status with the authoritative `SubgoalStatus` lifecycle from `orbit.runtime.agent.progress_graph`, eliminating duplicate status models.
  - Added `status: SubgoalStatus = SubgoalStatus.PENDING`, `verification_evidence: Optional[str]`, and `failure_reason: Optional[str]` to `GoalRequirement`.
  - Added lifecycle methods `is_satisfied()`, `mark_satisfied()`, and `mark_failed()` to `GoalRequirement`.
  - Added `is_all_mandatory_satisfied()` and `get_unsatisfied_requirements()` to `GoalRequirementSet`.

### B. Multi-Requirement Decomposition
- **`src/orbit/runtime/capabilities/requirements.py`**:
  - Implemented generalized `FILE_MANAGEMENT` requirement extraction across all persistence operations (`save`, `export`, `persist`, `write to file`, `store to file`, explicit formats/paths, `Desktop`/`Documents`/`Downloads`/custom directories) without task-specific hardcoding.
  - Correctly disambiguated editor text input (`write 'foo' into Notepad` $\rightarrow$ `DATA_INPUT`) from disk persistence (`write to test.txt` $\rightarrow$ `FILE_MANAGEMENT`).

### C. Grounded Multi-Requirement Verification & Artifact Provenance
- **`src/orbit/runtime/task_completion/goal_verifier.py`**:
  - Implemented requirement-by-requirement evaluation in `GoalVerifier.verify_goal_achievement()`.
  - Added physical filesystem verification for `FILE_MANAGEMENT` requirements: checks `os.path.exists()`, verifies non-empty file size (`os.path.getsize() > 0`), and validates file header integrity via `PIL.Image.open()`.
  - **Artifact Provenance Verification**: Verified that filesystem artifacts were modified during the current task execution window (`mtime >= task_start_time`), strictly rejecting pre-existing disk files that lack task provenance.
  - Enforces the strict completion invariant: **all mandatory requirements must be `COMPLETED` / `SATISFIED`**. If any required condition is `PENDING`, `FAILED`, `BLOCKED`, or unverified, `GoalVerifier` returns `status=TaskCompletionStatus.FAILED` / `is_completed=False`.

### D. Regression Test Suite
- **`tests/unit/test_multi_requirement_verification.py`**:
  - Created complete test suite with 15 unit tests covering all 8 mandatory regression scenarios from the Phase 2A specification plus explicit artifact provenance rejection tests.

---

## 4. Goal Completion Invariant

The authoritative completion invariant is now strictly enforced across ORBIT:

$$\text{FINAL\_GOAL\_COMPLETE} \iff \forall r \in \text{MandatoryRequirements}(G): \text{status}(r) \in \{\text{COMPLETED}, \text{SKIPPED}\} \land \text{provenance\_verified}(r) = \text{True}$$

If any mandatory requirement has status $\in \{\text{PENDING}, \text{READY}, \text{IN\_PROGRESS}, \text{FAILED}, \text{BLOCKED}\}$, the final completion status **MUST** remain incomplete / failed.

---

## 5. Requirement State Semantics

Every requirement transitions through the canonical `SubgoalStatus` lifecycle:
- **`PENDING`**: Requirement identified in decomposition but execution has not yet started or verified.
- **`READY`**: Prerequisite dependencies met, eligible for verification/execution.
- **`IN_PROGRESS`**: Actions targeting this requirement are active.
- **`COMPLETED`**: Independent, grounded evidence confirms all acceptance criteria for this specific requirement are met with verified task provenance.
- **`FAILED`**: Explicit failure detected or terminal execution error for this requirement.
- **`BLOCKED`**: Preceding dependency requirement failed or unmet.
- **`SKIPPED`**: Requirement bypassed because condition was already satisfied.

---

## 6. Verification & Evidence Behavior

| Requirement Type | Evidence Source | Verification Criteria |
| :--- | :--- | :--- |
| **`APP_LIFECYCLE`** | Window hierarchy / Desktop observation | Active window title or process matches target application (e.g. `mspaint.exe` / `Paint`). |
| **`CANVAS_INTERACTION`** | Multimodal canvas state / stroke registry | Canvas diff indicates non-trivial pixel/stroke delta (`stroke_count > 0` or bounding box altered). |
| **`FILE_MANAGEMENT`** | Host filesystem & file validation | Target file exists at canonical path (e.g. `Desktop/test.png`), `size > 0`, valid format header, and `mtime >= task_start_time` (provenance check). |

---

## 7. SUCCESS Propagation Audit

We audited all potential execution and termination paths across the runtime:
1. **`AgentExecutionLoop.run()`**:
   - Evaluates `goal_verifier.verify_goal_achievement()`.
   - If `is_satisfied` is False, execution continues to subsequent cycles.
   - If max actions/budget is exhausted without full goal satisfaction, returns `final_status=FAILED` or `INCOMPLETE`, never `COMPLETED`.
2. **`GoalVerifier.verify_goal_achievement()`**:
   - Iterates through all requirements in `GoalRequirementSet`.
   - Updates requirement statuses with concrete evidence.
   - Requires `req_set.is_all_mandatory_satisfied() == True` before setting `status = TaskCompletionStatus.COMPLETED`.
3. **Alternate paths checked**:
   - `TaskResult`, `GoalProgressTracker`, `ActionVerifier`: No alternate path can bypass `GoalRequirementSet.is_all_mandatory_satisfied()`.

---

## 8. Test Matrix & Results

### Mandatory Regression Tests (`tests/unit/test_multi_requirement_verification.py`)
| Test ID | Scenario | Status |
| :--- | :--- | :--- |
| **Test 1** | Single requirement ("Open Notepad") → satisfied → COMPLETE | **PASS** |
| **Test 2** | Multiple requirements (Paint open satisfied, Save pending) → NOT COMPLETE | **PASS** |
| **Test 3** | Multiple requirements (Paint open satisfied, Circle satisfied, Save satisfied with file on disk) → COMPLETE | **PASS** |
| **Test 4** | Multiple requirements with one requirement FAILED → NOT COMPLETE | **PASS** |
| **Test 5** | Reproduce Phase 1.6 bug (DRAW_STROKES verified, SAVE_FILE pending) → NOT COMPLETE | **PASS** |
| **Test 6** | Requirement progression (Draw satisfied + Save pending = False $\rightarrow$ Save satisfied = True) | **PASS** |
| **Test 7** | Requirement exists but physical evidence missing → NOT COMPLETE | **PASS** |
| **Test 8** | Multi-stage requirement dependency ordering & verification | **PASS** |
| **Test 9** | Artifact provenance verification: pre-existing file without task provenance rejected | **PASS** |
| **Tests 10-15** | Compound calculation/notepad decomposition, zero-byte file rejection, corrupt file rejection | **PASS** |

### Test Suite Execution Summary
- **Multi-Requirement Unit Suite**: `15 passed in 0.54s` (100% pass)
- **Full Unit Test Suite (`pytest tests/unit/`)**: `641 passed, 3 failed` (Identical to pre-existing baseline; 0 regressions)
- **Full Integration Suite (`pytest tests/integration/`)**: `94 passed, 26 failed` (Identical to pre-existing baseline; 0 regressions)

---

## 9. Real Desktop Paint E2E Execution Result

**Prompt:** *"Open Paint, draw a red circle, and save it as test.png on the Desktop."*

- **Pre-execution `Desktop/test.png` exists:** `False`
- **Execution behavior:**
  - Paint opened and circle drawing was executed.
  - Intermediate visual milestone was reached.
  - `GoalVerifier` evaluated requirements:
    - Requirement 1 (`APP_LIFECYCLE`): `COMPLETED`
    - Requirement 2 (`CANVAS_INTERACTION`): `COMPLETED`
    - Requirement 3 (`FILE_MANAGEMENT`): `PENDING` (File does not exist on disk)
  - `GoalVerifier` returned: `is_completed=False`, `status=FAILED/INCOMPLETE`, `unsatisfied_requirements=['req_file_management']`.
- **Final ORBIT Task Status:** Did **NOT** declare premature success (`is_success=False`).
- **Post-execution `Desktop/test.png` exists:** `False`
- **Audit Verdict:**
  > **VERIFIED:** GoalVerifier no longer permits premature success; downstream save execution remains a separate blocker.

---

## 10. Remaining Blockers Outside Phase 2A

1. **Downstream Action Execution for Save Dialogs (Phase 2B Scope)**:
   - When the agent attempts to save a file in a native Windows application (Paint), it must synthesize key combinations (e.g. `Ctrl+S`), navigate the native Win32/UIA File Save Dialog, type the destination path, and confirm save.
   - This requires multi-step action planning and dialog handling, which resides in the downstream decision engine / action synthesis layers outside Phase 2A scope.

---

## 11. Exact Next Recommended Phase

**Phase 2B — Multi-Step Action Synthesis & File Dialog Automation**:
- Implement file dialog targeting and keyboard save sequences in `AgentDecisionEngine` / `AgentPlanner`.
- Connect save dialog UI grounding to ensure the file save action executes to completion on disk.
