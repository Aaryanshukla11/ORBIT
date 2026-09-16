# Phase 3B — Dynamic Subgoal Graph & Hierarchical Planner Audit

## 1. Executive Summary & Objective

Phase 3B implements a dynamic Directed Acyclic Graph (DAG) Subgoal Planner (`DynamicSubgoalPlanner`) for ORBIT's cognitive layer.

Complex real-world tasks require non-linear execution capabilities:
1. **Pre-condition & Post-condition Validation**: Subgoals evaluate live desktop conditions (`WINDOW_ACTIVE`, `PROCESS_RUNNING`, `TEXT_OBSERVED`, `CANVAS_NON_BLANK`) before scheduling and completing milestones.
2. **Dependency-Aware Scheduling**: Subgoal milestones are scheduled strictly when all ancestor dependencies achieve `COMPLETED` status.
3. **Dead-End Rollback & Pruning**: Exhausting retries on a node automatically cascades `BLOCKED` status to all downstream dependent nodes.
4. **Multi-Branch Fallback Strategies**: Seamlessly switches execution branches (e.g. GUI Button $\to$ Keyboard Shortcut $\to$ CLI Shell) upon unrecoverable primary path failures.

---

## 2. Architecture & Components

### 2.1 Dynamic Subgoal Planner (`DynamicSubgoalPlanner`)
- **File**: `src/orbit/runtime/cognitive/subgoal_planner.py`
- Manages DAG nodes (`DynamicSubgoalNode`), tracking status (`PENDING`, `READY`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `BLOCKED`).
- Implements `ConditionPredicate` for declarative environment state evaluation against `CurrentStateObservation`.
- Implements `mark_failed_and_rollback()` with automatic fallback branch switching.

### 2.2 Integration Guarantees
- Plugs directly into `ProgressGraph` and `AgentExecutionLoop`.
- Provides structured DAG markdown serialization (`to_summary_text()`) for injection into `MultimodalContextBuilder`.

---

## 3. Verification & Gate Evidence

### 3.1 Unit Test Coverage
- `tests/unit/test_dynamic_subgoal_planner.py`:
  - `test_subgoal_dag_creation_and_dependencies` (PASS)
  - `test_subgoal_precondition_evaluation` (PASS)
  - `test_subgoal_postcondition_verification` (PASS)
  - `test_subgoal_failure_and_downstream_rollback` (PASS)
  - `test_subgoal_fallback_branch_activation` (PASS)

### 3.2 Closed-Loop Integration Test
- `tests/integration/test_hierarchical_subgoal_execution.py`:
  - `test_dynamic_subgoal_branching_and_execution` (PASS)
  - Validates dynamic branch switching from failed primary GUI action to fallback hotkey action with goal verification.

---

## 4. Exit Gate Certification
- [x] Subgoal DAG dependency scheduling operational.
- [x] Pre/post-condition predicate evaluation verified.
- [x] Dependent node rollback on retry exhaustion passing.
- [x] Multi-branch fallback execution verified in closed-loop test.
