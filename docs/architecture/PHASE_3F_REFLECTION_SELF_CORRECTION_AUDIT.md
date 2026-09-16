# Phase 3F — Advanced Self-Correction & Reflection Subagent Audit

## 1. Executive Summary & Objective

Phase 3F implements the autonomous failure reflection and self-correction subagent (`SelfCorrectionReflectionEngine`) for ORBIT.

When executing complex, multi-step desktop tasks, basic retry loops fail if the environment enters an unexpected state. The reflection subagent delivers:
1. **Multi-Class Root Cause Attribution**: Diagnoses failures into `UNEXPECTED_MODAL`, `TARGET_NOT_LOCATED`, `UNRESPONSIVE_UI`, `STATE_STALENESS`, and `INCORRECT_STRATEGY`.
2. **Backtrack Plan Synthesis**: Formulates cleanup steps (e.g. `SEND_HOTKEY Escape` to dismiss modals, refocusing windows, or rolling back to a known healthy checkpoint).
3. **Alternate Hypothesis Generation**: Produces ranked alternative execution primitives (e.g. replacing a failed GUI Click with a canonical keyboard shortcut `Ctrl+S`, `Ctrl+C`, `Ctrl+V`, or dynamic UI settle wait).

---

## 2. Architecture & Components

### 2.1 Reflection Engine (`SelfCorrectionReflectionEngine`)
- **File**: `src/orbit/runtime/cognitive/reflection.py`
- Implements `diagnose_and_reflect()` emitting structured `CorrectionPlan`.
- Maps failure signatures to checkpoint restoration targets.
- Synthesizes clean alternate actions to resume forward progress without getting trapped in infinite loops.

---

## 3. Verification & Gate Evidence

### 3.1 Unit Test Coverage
- `tests/unit/test_reflection.py`:
  - `test_reflection_engine_diagnoses_unexpected_modal` (PASS)
  - `test_reflection_engine_diagnoses_target_not_located` (PASS)
  - `test_reflection_engine_diagnoses_unresponsive_ui_and_synthesizes_alternates` (PASS)
  - `test_reflection_engine_tracks_checkpoint_backtrack` (PASS)

### 3.2 Closed-Loop Integration Test
- `tests/integration/test_reflection_self_correction.py`:
  - `test_reflection_self_correction_closed_loop` (PASS)
  - Validates full closed-loop self-correction: GUI Click fails $\to$ Reflection diagnoses `UNRESPONSIVE_UI` $\to$ Synthesizes `Ctrl+S` hotkey alternate $\to$ Dispatches alternate and achieves goal verification.

---

## 4. Exit Gate Certification
- [x] Autonomous failure diagnosis operational.
- [x] Checkpoint backtracking support verified.
- [x] Alternate hypothesis generation verified.
- [x] Closed-loop self-correction integration test passing.
