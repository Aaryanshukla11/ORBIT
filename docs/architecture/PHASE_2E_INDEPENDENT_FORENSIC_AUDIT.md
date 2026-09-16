# PHASE 2E — INDEPENDENT FORENSIC AUDIT REPORT

**Date:** 2026-09-16  
**Auditor:** Antigravity Forensic Audit Engine  
**Environment:** Windows 11 (x86_64), Python 3.12.2  
**Subject:** Phase 2E Authoritative Decision Engine Consolidation  

---

## 1. Static Decision-Authority Audit

Audit of all occurrences across `src/orbit`:

| File | Line / Function | Component | Classification | Reachable from Production? |
|---|---|---|---|---|
| `src/orbit/runtime/cognitive/engine.py` | Line 515 (`class OrbitDecisionEngine`) | `OrbitDecisionEngine` | **PRODUCTION** | **YES** (Canonical sole decision engine) |
| `src/orbit/runtime/cognitive/engine.py` | Line 560 (`decide_next_step`) | `OrbitDecisionEngine` | **PRODUCTION** | **YES** (Invoked by `AgentExecutionLoop`) |
| `src/orbit/runtime/cognitive/engine.py` | Line 75 (`class CognitiveDecisionEngine`) | `CognitiveDecisionEngine` | **LEGACY / BACKWARD-COMPAT** | **NO** (Not instantiated by production loop) |
| `src/orbit/runtime/cognitive/engine.py` | Line 248 (`_decide_deterministic`) | Heuristic Brain | **LEGACY / DEAD CODE** | **NO** (Only inside `CognitiveDecisionEngine`) |
| `src/orbit/runtime/cognitive/agent_decision.py` | Line 94 (`class AgentDecisionEngine`) | `AgentDecisionEngine` | **LEGACY / DEAD CODE** | **NO** (Zero callers in `src/orbit`) |
| `src/orbit/runtime/cognitive/agent_loop.py` | Line 59 (`import OrbitDecisionEngine`) | Production Loop | **PRODUCTION** | **YES** |
| `src/orbit/runtime/cognitive/agent_loop.py` | Line 157 (`self._decision_engine = ...`) | Production Loop | **PRODUCTION** | **YES** (Defaults strictly to `OrbitDecisionEngine`) |
| `src/orbit/runtime/cognitive/primitive_validator.py` | Line 263 (`validate_proposal`) | Proposal Validator | **PRODUCTION** | **YES** (4-stage deterministic gating) |
| `src/orbit/runtime/targeting/locator.py` | Line 27 (`EvidenceBasedTargetLocator`) | MultiPassGrounder | **PRODUCTION** | **YES** (Wired in target locator) |
| `src/orbit/runtime/cognitive/__init__.py` | Lines 1, 4, 51, 61, 62 | Exports | **EXPORT STUBS** | Backward compatibility only |

---

## 2. Production Call Graph

The verified runtime execution path with exact filenames and functions:

```text
User Goal & Prompt
   ↓
AgentExecutionLoop.run()
   [src/orbit/runtime/cognitive/agent_loop.py:648]
   ↓
OrbitDecisionEngine.decide_next_step()
   [src/orbit/runtime/cognitive/engine.py:560]
   ↓
MultimodalPromptBuilder.build_prompt()
   [src/orbit/runtime/cognitive/prompt_builder.py:63]
   ↓
ModelSessionContext.generate_response() / model_client.generate_response()
   [src/orbit/runtime/models/models.py]
   ↓
OrbitDecisionEngine._parse_model_proposal()
   [src/orbit/runtime/cognitive/engine.py:776]
   ↓
ModelProposalValidator.validate_proposal()  [Stages 1–4 Gating]
   [src/orbit/runtime/cognitive/primitive_validator.py:263]
   ↓
MultiPassGrounder.ground_target()
   [src/orbit/runtime/targeting/grounding.py:91]
   ↓
OrbitDecisionEngine._translate_proposal_to_abstract_action()
   [src/orbit/runtime/cognitive/engine.py:811]
   ↓
AgentExecutionStrategySelector.select_strategy()
   [src/orbit/runtime/cognitive/agent_loop.py:1022]
   ↓
EvidenceBasedTargetLocator.locate_target()
   [src/orbit/runtime/targeting/locator.py:339]
   ↓
PrimitiveExecutionController.execute_action() / _execute_action_step()
   [src/orbit/runtime/cognitive/primitive_execution_controller.py:126]
   ↓
Windows Desktop Capability Dispatch (Pointer / Keyboard / ShellExecute / Win32)
   ↓
CurrentStateObserver.capture_current_state()
   [src/orbit/runtime/cognitive/observer.py:80]
   ↓
AgentStateTransitionVerifier.verify_transition() & GoalVerifier.evaluate_goal_progress()
   [src/orbit/runtime/agent/verifier.py:98 & src/orbit/runtime/task_completion/goal_verifier.py:64]
```

---

## 3. Model-Authority Proof

| Question | Verdict | Forensic Evidence |
|---|---|---|
| **A. Can a standard task execute without the model deciding WHAT to do?** | **NO** | `OrbitDecisionEngine.decide_next_step` checks for active model session/client; if missing, returns structured `MODEL_UNAVAILABLE` diagnostic and halts (`ABORT_TASK`). |
| **B. Is there ANY silent heuristic fallback?** | **NO** | Zero fallback hooks exist in `OrbitDecisionEngine`. Silent routing to `_decide_deterministic` has been completely severed. |
| **C. Can CognitiveDecisionEngine still make a production decision?** | **NO** | `AgentExecutionLoop` initializes `OrbitDecisionEngine` by default. `CognitiveDecisionEngine` is unreachable in standard production runs. |
| **D. Can AgentDecisionEngine independently make a production decision?** | **NO** | Zero production callers exist in `src/orbit`. |
| **E. Can another component alter `action_type` after model output?** | **NO** | `_translate_proposal_to_abstract_action` directly preserves the model's requested action type. Deterministic validators can only pass or reject/retry, never mutate `action_type`. |

---

## 4. MultiPassGrounder Runtime Proof

`MultiPassGrounder` is integrated on the active production path via two independent connections:
1. **Target Locator Integration:** `EvidenceBasedTargetLocator.__init__` instantiates `self._multipass_grounder = MultiPassGrounder(...)` and invokes it during `locate_target` (`src/orbit/runtime/targeting/locator.py:361`).
2. **Decision Engine Grounding Integration:** `OrbitDecisionEngine.decide_next_step` directly calls `self._grounder.ground_target(tgt_name, tgt_role, ws, candidate_bounds)` (`src/orbit/runtime/cognitive/engine.py:742`).

---

## 5. Invalid Proposal Attack

Forensic execution results from `scratch/run_forensic_attacks.py`:

```
Model Proposal Rejected at [SCHEMA]: Missing 'expected_outcome' in proposal.
Model Proposal Rejected at [SAFETY]: Prohibited security-sensitive keyword detected: 'powershell -e'
Model Proposal Rejected at [GROUNDING]: STALE_GROUNDING_REJECTED: Proposal was grounded against observation 'obs_old', but current active observation is 'obs_fresh'.
Model Proposal Rejected at [GROUNDING]: Normalized bounding box [1200, 500, 1500, 800] violates range [0, 1000]
=== STEP 5: INVALID PROPOSAL ATTACK ===
  [PASS] Stage 1 (SCHEMA) rejection verified: Missing 'expected_outcome' in proposal.
  [PASS] Stage 3 (SAFETY) rejection verified: Prohibited security-sensitive keyword detected: 'powershell -e'
  [PASS] Stage 4 (GROUNDING - STALE OBS) rejection verified: STALE_GROUNDING_REJECTED
  [PASS] Stage 4 (GROUNDING - OUT OF BOUNDS) rejection verified: Normalized bounding box [1200, 500, 1500, 800] violates range [0, 1000]
  [PASS] Physical Coordinate Policy strictly enforced: CoordinatePolicyViolation blocked in AbstractAction
```
**Conclusion:** Gating is strictly deterministic and authoritative. Executor receives 0 physical actions for invalid proposals.

---

## 6. Legacy Engine Attack

Forensic execution results:
- Monkeypatched `CognitiveDecisionEngine._decide_deterministic`, `CognitiveDecisionEngine.decide_next_step`, and `AgentDecisionEngine.decide_next_action` to raise `RuntimeError("FATAL: Legacy deterministic engine was illegally called!")`.
- Dispatched task via `OrbitDecisionEngine`.
- **Result:** Task executed smoothly through `OrbitDecisionEngine`. Zero legacy exceptions were triggered.

---

## 7. Live E2E Trace Forensics

Audit of `scratch/phase2e_live_e2e_results.json`:

- **Decision Engine Used:** `OrbitDecisionEngine` logged across all steps.
- **Model Proposals:** Declarative JSON proposals logged for all actions.
- **Coordinate Isolation Gate:** Proved live blocking of raw physical coordinates (`CoordinatePolicyViolation`).
- **Goal Verification Gate:** `GoalVerifier` successfully detected missing artifact on disk and rejected goal completion claims.
- **Live Save Execution:** Paint save dialog interaction did not complete file creation on disk during unattended run.
- **Evidence Quality:** **PARTIAL** (Real Windows execution traces captured, but physical Paint save dialog was unverified on disk).

---

## 8. Test Integrity Audit

Audit of `tests/unit/test_phase2e_decision_engine_consolidation.py`:
- **Structure:** Contains 9 focused unit/architecture tests verifying production wiring, fail-closed semantics, distinctive proposal propagation, invalid proposal blocking, safety policy gating, model-driven recovery, and WorldState grounding.
- **Mocking Policy:** Mocks LLM text output while executing real production classes (`OrbitDecisionEngine`, `ModelProposalValidator`, `MultiPassGrounder`, `EvidenceBasedTargetLocator`, `AgentExecutionLoop`).
- **Regression Suite:** All 48 targeted tests pass cleanly (`48 passed in 8.46s`).

---

## 9. Phase 2B Status

**Status:** `PARTIAL` (Unchanged)

**Exact Root Cause for Paint Save Gap:**
- **Category:** Save Dialog Detection & UI Path Entry Confirmation.
- **Details:** When `SAVE_FILE` was dispatched during live unattended desktop execution, the Save As modal dialog interaction failed at the adapter level to complete file path entry and confirmation, leaving `test.png` absent from the desktop.

---

## 10. Final Verdict Table

| Component / Requirement | Final Verdict |
|---|---|
| **2D Production Integration** | **PASS** |
| **2C Model Authority** | **PASS** |
| **2E Single Decision Authority** | **PASS** |
| **Hidden Second Brain** | **PASS** (Zero hidden brains) |
| **MultiPassGrounder Production Path** | **PASS** |
| **Live E2E Evidence Quality** | **PARTIAL** |
| **Phase 2B Real Save** | **PARTIAL** |

---

*Phase 2E consolidation is verified. No further code modifications made. Ready for user guidance on Phase 2B resolution or subsequent phases.*
