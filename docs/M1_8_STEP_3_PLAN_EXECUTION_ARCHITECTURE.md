# ORBIT MILESTONE M1.8 STEP 3: PLAN EXECUTION ARCHITECTURE
## Plan-to-Execution Bridge & Sequential Closed-Loop Plan Dispatch

**Document Version:** 1.0.0  
**Milestone:** M1.8 Step 3  
**Status:** ARCHITECTURE DESIGN & FORENSIC REVIEW  
**Epistemic Baseline:** Deterministic, Fail-Closed, Closed-Loop Grounded Execution  

---

## 1. Executive Summary & Existing Architecture Findings

ORBIT Milestone M1.8 Step 1 established structured task understanding (`TaskUnderstandingEngine`), and Step 2 established dependency-aware DAG task planning (`TaskPlanningEngine`). Step 2 produces validated `ExecutableTaskPlan` objects composed of abstract `PlanStep` nodes connected by an `ActionDependencyGraph`.

However, `PlanStep` instances are intentionally abstract:
- They contain **zero** physical screen coordinates `(x, y)`.
- They contain **no** direct Win32 `SendInput` or OS hardware dispatch commands.
- They contain declared `Precondition`, `Postcondition`, and `DeferredGroundingRequirement` specs.

Milestone M1.8 Step 3 implements the **Plan-to-Execution Bridge**:
```
User Task (Natural Language / Structured)
        ↓
Task Understanding (M1.8 Step 1)
        ↓
Dependency Graph / Plan Generation (M1.8 Step 2)
        ↓
Topological Step Selection & Scheduling (M1.8 Step 3 Scheduler)
        ↓
Plan-to-Runtime Action Compilation (M1.8 Step 3 Compiler)
        ↓
Fresh Observation Capture (Generation-Bound)
        ↓
Target Grounding & Coordinate Localization (M1.7 TargetLocator)
        ↓
Closed-Loop Execution & Safety Gate (M1.6 ClosedLoopExecutionEngine)
        ↓
Post-Action State Verification (M1.6 ActionVerifier)
        ↓
Step Result Recording & Dependency Resolution
        ↓
Next Eligible Plan Step / Fail-Closed Termination
```

---

## 2. Exact Integration Points & Execution Boundaries

### 2.1 Subsystem Boundary Invariants
1. **Planning Subsystem (`src/orbit/runtime/planning/`) Remains Purely Generative & Abstract**:
   - Planning does **not** import runtime adapters, does **not** call Win32 APIs, and does **not** generate coordinates.
2. **Plan Execution Subsystem (`src/orbit/runtime/plan_execution/`) Owns Plan Orchestration**:
   - Translates abstract `PlanStep` models into concrete runtime intents and orchestrates multi-step sequential execution.
3. **Closed-Loop Execution Engine (`src/orbit/runtime/execution/engine.py`) Owns OS Interaction**:
   - `ClosedLoopExecutionEngine` remains the **sole authority** executing the `OBSERVE → RESOLVE → VALIDATE → ACT → RE-OBSERVE → VERIFY → DECIDE` cycle.
4. **Safety & Preemption Authority (`ExecutionContext`, `AutonomousDispatchGate`)**:
   - `AutonomousDispatchGate` guarantees that no pointer or keyboard event reaches hardware without valid desktop generation checks, workspace safety bounds, and human takeover preemption verification.
5. **Frozen Prototype Boundaries**:
   - `prototypes/prototype_a_workspace/`
   - `prototypes/prototype_b_human_takeover/`
   - `prototypes/prototype_c_keyboard/`
   - `prototypes/prototype_d_observation/`
   - `prototypes/prototype_e_pointer/`
   All prototype code remains strictly frozen and untouched.

---

## 3. PlanStep to RuntimeAction Compilation Model

The `PlanStepCompiler` translates each `PlanStep` into a `CompiledRuntimeAction` containing:
- `action_type`: e.g. `"pointer_click"`, `"type_text"`, `"shortcut"`, `"pointer_move"`
- `target_intent`: `TargetIntent` declaring perception strategy (MSAA, OCR, Visual Template, Multimodal), accessible names, OCR text, bounding boxes, or window titles.
- `action_parameters`: Dict containing action arguments (e.g. `text`, `combination`, `button`, `count`).
- `expected_outcome`: `Optional[ExpectedOutcome]` specifying expected post-action state delta for verification.
- `is_supported`: `bool` indicating whether the step can be safely executed by available capabilities.
- `rejection_reason`: Explicit diagnostic string if the step cannot be compiled or is unsupported.

### Compilation Mapping Matrix:

| PlanActionType | Target Intent Strategy | Action Type | Action Parameters | Expected Outcome | Support Classification |
|---|---|---|---|---|---|
| `ENSURE_APPLICATION_OPEN` | `WINDOW_TITLE` / `ACCESSIBILITY_ELEMENT` | `pointer_move` / `observe` | window title / app name | `WINDOW_APPEARED` / `ANY_OBSERVABLE_CHANGE` | SUPPORTED |
| `FOCUS_APPLICATION` | `WINDOW_TITLE` / `ACCESSIBILITY_ELEMENT` | `pointer_click` | `button="left"` | `WINDOW_FOCUSED` | SUPPORTED |
| `LOCATE_TARGET` | From `deferred_grounding.strategy_preferences` | `pointer_move` | None | `TARGET_APPEARED` / `ANY_OBSERVABLE_CHANGE` | SUPPORTED |
| `LOCATE_INPUT_SURFACE` | `ACCESSIBILITY_ELEMENT` / `OCR_TEXT` | `pointer_click` | `button="left"` | `ELEMENT_STATE_CHANGED` | SUPPORTED |
| `ENTER_TEXT` | Target from step / preceding focus | `type_text` | `text=constraints.content` | `ELEMENT_STATE_CHANGED` | SUPPORTED |
| `ACTIVATE_CONTROL` | From `deferred_grounding` (OCR / MSAA / Visual) | `pointer_click` | `button="left"`, `count=1` | `TARGET_DISAPPEARED` / `ANY_OBSERVABLE_CHANGE` | SUPPORTED |
| `SAVE_DOCUMENT` | Target window | `shortcut` | `combination="ctrl+s"` | `ANY_OBSERVABLE_CHANGE` | SUPPORTED |
| `COPY_CONTENT` | Target window | `shortcut` | `combination="ctrl+c"` | `ANY_OBSERVABLE_CHANGE` | SUPPORTED |
| `PASTE_CONTENT` | Target window | `shortcut` | `combination="ctrl+v"` | `ELEMENT_STATE_CHANGED` | SUPPORTED |
| `VERIFY_APPLICATION_AVAILABLE` | `WINDOW_TITLE` | `observe` | None | `WINDOW_APPEARED` | SUPPORTED |
| `VERIFY_TEXT_ENTRY` | `OCR_TEXT` / `ACCESSIBILITY_ELEMENT` | `observe` | None | `ELEMENT_STATE_CHANGED` | SUPPORTED |
| `VERIFY_TARGET_EFFECT` | `ACCESSIBILITY_ELEMENT` / `VISUAL_TEMPLATE` | `observe` | None | `ANY_OBSERVABLE_CHANGE` | SUPPORTED |
| `VERIFY_DOCUMENT_SAVED` | Window title / state | `observe` | None | `ANY_OBSERVABLE_CHANGE` | SUPPORTED |
| `VALIDATE_SELECTION_CONTEXT` | Selection context | `observe` | None | `ANY_OBSERVABLE_CHANGE` | SUPPORTED |
| `VERIFY_CLIPBOARD_STATE` | Clipboard verification | `observe` | None | None | PARTIALLY_SUPPORTED (Observation delta fallback) |
| `SEARCH_QUERY` | Search UI | Abstract | None | None | PARTIALLY_SUPPORTED |
| `UNSUPPORTED_ACTION` | None | None | None | None | UNSUPPORTED (Fails Closed) |

---

## 4. Dependency-Aware Scheduling & Execution Lifecycle

### 4.1 Step Execution State Transitions
Each step transitions through the following discrete lifecycle:
```
               ┌─────────────┐
               │   PENDING   │
               └──────┬──────┘
                      │ All predecessors SUCCEEDED
                      ▼
               ┌─────────────┐
        ┌─────►│    READY    │
        │      └──────┬──────┘
        │             │ Execution begins
        │             ▼
        │      ┌─────────────┐
        │      │   RUNNING   │
        │      └──────┬──────┘
        │             │
        ├─────────────┼─────────────────────────┐
        ▼             ▼                         ▼
  ┌───────────┐ ┌───────────┐             ┌───────────┐
  │ SUCCEEDED │ │  FAILED   │             │ CANCELLED │
  └───────────┘ └─────┬─────┘             └───────────┘
                      │
                      ▼ Downstream steps
                ┌───────────┐
                │  BLOCKED  │
                └───────────┘
```

### 4.2 Dependency Enforcement Rules:
1. **Rule 1 (Predecessor Success Invariant)**: A step cannot transition to `READY` or `RUNNING` unless **100%** of its immediate dependency `step_ids` have reached `SUCCEEDED`.
2. **Rule 2 (Failure Propagation Invariant)**: If a step reaches `FAILED`, all transitive downstream dependent steps immediately transition to `BLOCKED`. They are **never executed**.
3. **Rule 3 (Topological Ordering)**: Steps are scheduled strictly according to Kahn's algorithm topological order.
4. **Rule 4 (Cancellation & Preemption Invariant)**: If `ExecutionContext.is_cancelled` is True or `is_human_takeover_active()` is True, the scheduler immediately stops issuing steps, cancels any in-flight step, and marks remaining steps `CANCELLED`.

---

## 5. Evidence Freshness & Generation Safety Model

1. **Per-Step Fresh Observation**:
   - The plan executor **never reuses coordinates** across steps.
   - For every executable step, `ClosedLoopExecutionEngine` captures a fresh `ObservationSnapshot`.
   - Target localization runs against the current snapshot and validates against the active `desktop_generation_id`.
2. **Desktop Generation Parity**:
   - If the desktop generation increments between perception and dispatch (e.g. window move, resize, or AppBar reservation change), `AutonomousDispatchGate` blocks dispatch with `GENERATION_MISMATCH`.
   - `ClosedLoopExecutionEngine` either triggers bounded recovery with a re-observed frame or terminates fail-closed.

---

## 6. Failure Recovery & Error Diagnostics

Each step execution produces an audit record containing:
- `step_id`, `step_index`, `action_type`
- `status`: `SUCCEEDED`, `FAILED`, `BLOCKED`, `CANCELLED`, `UNSUPPORTED`
- `compiled_action`: `CompiledRuntimeAction`
- `execution_result`: Full `ClosedLoopExecutionResult` from the engine
- `failure_reason`: Human- and machine-readable failure reason
- `failure_code`: Canonical failure code (`TARGET_NOT_FOUND`, `VERIFICATION_FAILED`, `CAPABILITY_UNAVAILABLE`, `PREDECESSOR_FAILED`, etc.)
- `generation_id`: Desktop generation evaluated during execution
- `is_dispatched`: Whether physical OS action was actually dispatched

---

## 7. Next Authorized Step: Implementation Plan

Following approval of this architecture:
1. Implement `src/orbit/runtime/plan_execution/models.py`.
2. Implement `src/orbit/runtime/plan_execution/compiler.py`.
3. Implement `src/orbit/runtime/plan_execution/scheduler.py`.
4. Implement `src/orbit/runtime/plan_execution/validator.py`.
5. Implement `src/orbit/runtime/plan_execution/executor.py`.
6. Implement `src/orbit/runtime/plan_execution/__init__.py`.
7. Integrate into `OrbitOrchestrator`.
8. Write comprehensive unit, integration, and live test suites.
9. Execute full test suite and confirm zero modifications in `prototypes/`.
10. Generate completion report.
