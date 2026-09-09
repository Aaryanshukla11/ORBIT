# ORBIT Architecture Rules — FINAL LOCKED ENFORCEMENT

## MANDATORY: READ THIS BEFORE TOUCHING ANY CODE

This project is building ORBIT as a **Primitive-Centric General Computer Agent**.
You MUST follow the locked architecture flow and implementation plan without deviations.

---

## 1. The Locked Architecture Flow

```
                    USER
                      │
                      ▼
              ┌──────────────┐
              │ INTENT ENGINE│
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │ WORLD MODEL  │
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │  DECOMPOSER  │
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │ FEASIBILITY  │
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │   PLANNER    │  ← WHAT
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │   COMPOSER   │  ← HOW
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │  VALIDATOR   │
              └──────┬───────┘
                     ▼
        ┌─────────────────────────┐
        │  EXECUTION CONTROLLER   │
        │                         │
        │  Action → Observe →     │
        │  Verify → Next Action   │
        └───────────┬─────────────┘
                    ▼
          ┌──────────────────┐
          │ TARGET GROUNDING │
          │  infrastructure  │
          └────────┬─────────┘
                   ▼
             SAFETY GATE
                   ▼
              EXECUTOR
                   ▼
             ENVIRONMENT
                   │
                   ▼
              OBSERVATION
                   ▼
          MULTI-EVIDENCE VERIFY
                   │
             ┌─────┴─────┐
             ▼           ▼
          SUCCESS      FAILURE
                         │
                         ▼
                    FAILURE ANALYST
                         │
                         ▼
                       REPLAN
                         │
                         └──────────→ COMPOSER
```

---

## 2. Core Invariants & Rules

1. **PLANNER = WHAT**: `CognitiveDecisionEngine` answers what to accomplish next. Never produces coordinates or low-level primitives.
2. **COMPOSER = HOW**: `PrimitiveComposer` decomposes sub-goals into canonical atomic primitives using `StructuredAgentContext`. Zero hardcoded shapes.
3. **EXECUTOR = DO**: Resolves target grounding through infrastructure, selects environment provider, checks safety gate, and executes.
4. **VERIFIER = DID IT WORK?**: `MultiEvidenceActionVerifier` evaluates each action via UIA delta, OCR text, semantic effects, and VLM confirmation. Pixel delta is only a weak fallback.
5. **ONE Canonical Primitive Vocabulary**: `AbstractActionType` contains ONLY canonical primitives. Aliases exist ONLY at the external boundary in `LegacyActionAdapter`.
6. **Grounding is Infrastructure**: `VISUAL_GROUND` is removed from `AbstractActionType`. Target grounding is strictly internal execution infrastructure.
7. **Environment Provider Registry**: Environment interfaces (`SPREADSHEET_WRITE`, `BROWSER_NAVIGATE`, etc.) resolve dynamically through `EnvironmentProviderRegistry` (e.g. Excel COM, LibreOffice, CSV fallback).
8. **Guarded Decomposer**: Fast-path decomposition is strictly pure linguistic syntax splitting (`and then`, `after that`). Zero domain keyword classifiers.
9. **Structured Agent Context**: The model receives a rich snapshot (`StructuredAgentContext`) containing active window, visible controls, current URL/document, working memory facts, recent actions, and recent failures.
10. **Closed-Loop Execution**: `PrimitiveExecutionController` executes Action N → Observe → Multi-Evidence Verify → Action N+1. On failure: `FAILURE ANALYST → REPLAN → COMPOSER`.
11. **COMPLETE_GOAL is a Signal Only**: Must be confirmed by `GoalVerifier` before task completion is recorded.
12. **Outcome-Driven Benchmarks**: Benchmarks evaluate deliverable correctness, safety compliance, recovery, and efficiency — not a rigid list of primitives.
