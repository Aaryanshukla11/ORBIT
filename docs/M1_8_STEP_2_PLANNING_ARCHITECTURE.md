# ORBIT — Milestone M1.8 Step 2 Architecture Note
## Dependency-Aware Task Planning & Action Graph Generation

**Document Status:** Approved Architecture Reference  
**Author:** ORBIT Core Architecture Team  
**Scope:** M1.8 Step 2 Subsystem (`src/orbit/runtime/planning/`)

---

### 1. Architectural Role & Execution Boundary

Milestone M1.8 Step 2 introduces deterministic task planning and dependency-aware action graph construction to ORBIT.

#### Pipeline Flow:
$$\text{Natural Language Task} \xrightarrow{\text{M1.8 Step 1}} \text{TaskUnderstandingResult} \xrightarrow{\text{M1.8 Step 2}} \text{TaskPlanningEngine} \xrightarrow{\text{DAG Construction}} \text{ExecutableTaskPlan} \xrightarrow{\text{Safe Hold}} \text{STOP}$$

#### Key Invariants:
1. **Abstract Action Objectives:** Plans are composed of high-level semantic objectives (`PlanActionType` such as `ENSURE_APPLICATION_OPEN`, `LOCATE_INPUT_SURFACE`, `ENTER_TEXT`, `ACTIVATE_CONTROL`, `SAVE_DOCUMENT`).
2. **Zero Coordinate Invariant:** A `PlanStep` **never** contains screen coordinates (`x`, `y`). Physical screen resolution is deferred exclusively to runtime M1.7 perception layers.
3. **Deterministic Planning:** Operates completely locally via rule-based goal decomposition with zero external cloud LLM dependencies.
4. **Zero OS Side Effects:** Planning is purely epistemic and generative; it never executes pointer events, keystrokes, application launches, or file modifications.

---

### 2. Subsystem Structure

The planning subsystem is implemented in `src/orbit/runtime/planning/`:

```
src/orbit/runtime/planning/
├── __init__.py          # Public package exports
├── models.py            # Strongly typed contracts (PlanStep, ExecutableTaskPlan, Precondition, Postcondition)
├── graph.py             # ActionDependencyGraph (DAG, cycle detection, topological sort)
├── policies.py          # PlanningRuleRegistry (goal decomposition rules)
├── validator.py         # PlanValidator (invariant checks, negative constraint enforcement)
├── explainability.py    # PlanExplainer (deterministic provenance and dependency breakdown)
└── planner.py           # TaskPlanningEngine facade
```

---

### 3. Data Contracts

1. **`PlanActionType` (Enum):**
   - Application lifecycle: `ENSURE_APPLICATION_OPEN`, `FOCUS_APPLICATION`, `CLOSE_APPLICATION`, `VERIFY_APPLICATION_AVAILABLE`
   - Input & Surface: `LOCATE_INPUT_SURFACE`, `ENTER_TEXT`, `VERIFY_TEXT_ENTRY`, `PASTE_CONTENT`
   - UI Control: `LOCATE_TARGET`, `ACTIVATE_CONTROL`, `VERIFY_TARGET_EFFECT`, `SELECT_OPTION`
   - Document & Clipboard: `SAVE_DOCUMENT`, `VERIFY_DOCUMENT_SAVED`, `COPY_CONTENT`, `VERIFY_CLIPBOARD_STATE`, `VALIDATE_SELECTION_CONTEXT`
   - Search & Navigation: `SEARCH_QUERY`, `NAVIGATE_VIEW`
   - Fail-closed fallback: `UNSUPPORTED_ACTION`

2. **`Precondition` & `Postcondition`:**
   - Machine-readable condition contracts declaring required pre-states (e.g., `application_running`, `window_focused`, `input_surface_located`) and verifiable outcomes (`text_rendered_verified`, `document_saved`, `control_invoked`).

3. **`DeferredGroundingRequirement`:**
   - Explicitly records required perception strategies (`ACCESSIBILITY_ELEMENT`, `OCR_TEXT`, `VISUAL_TEMPLATE`) and target references to be resolved by M1.7 perception against fresh runtime observation frames.

4. **`ActionDependencyGraph`:**
   - Enforces strict DAG semantics: cycle detection via DFS coloring, non-existent dependency detection, and Kahn's algorithm topological sequencing.

5. **`PlanExplainer`:**
   - Provides deterministic explainability dictionaries answering *why* each step was created, what preceding steps it depends on, what constraints govern it, and what perception strategies are deferred.

---

### 4. Supported Task Flows

- **Flow 1 (Open Application):** `ENSURE_APPLICATION_OPEN` $\to$ `VERIFY_APPLICATION_AVAILABLE`
- **Flow 2 (Open & Write Text):** `ENSURE_APPLICATION_OPEN` $\to$ `VERIFY_APPLICATION_AVAILABLE` $\to$ `FOCUS_APPLICATION` $\to$ `LOCATE_INPUT_SURFACE` $\to$ `ENTER_TEXT` $\to$ `VERIFY_TEXT_ENTRY`
- **Flow 3 (Click Control):** `LOCATE_TARGET` $\to$ `ACTIVATE_CONTROL` $\to$ `VERIFY_TARGET_EFFECT`
- **Flow 4 (Save Document):** `LOCATE_TARGET` $\to$ `SAVE_DOCUMENT` $\to$ `VERIFY_DOCUMENT_SAVED` (Respects negative constraint `do not save`)
- **Flow 5 (Search):** `LOCATE_TARGET` $\to$ `ENTER_TEXT` $\to$ `ACTIVATE_CONTROL` $\to$ `VERIFY_TARGET_EFFECT`
- **Flow 6 (Copy & Paste):** `VALIDATE_SELECTION_CONTEXT` $\to$ `COPY_CONTENT` $\to$ `VERIFY_CLIPBOARD_STATE`

---

### 5. Orchestrator Integration & Safe Holding Boundary

- `OrbitOrchestrator` exposes:
  - `orch.understand_task(prompt)` $\to$ `TaskUnderstandingResult`
  - `orch.plan_task(understanding)` $\to$ `ExecutableTaskPlan`
- Natural-language tasks submitted to `orch.submit_task()` automatically execute task understanding and planning, attaching `task.metadata["task_understanding"]` and `task.metadata["task_plan"]`.
- Execution stops safely prior to multi-step dispatch (reserved for M1.8 Step 3).
