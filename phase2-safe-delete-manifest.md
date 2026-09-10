# ORBIT → ASTRA-6: Phase 2 Safe-Delete Manifest

**Date:** 2026-09-10
**Status:** VALIDATED FOR PHYSICAL DELETION
**Pre-condition Gate:** 0 Active Production Callers in Canonical ASTRA-6 Runtime

---

## 1. Deletion Manifest Summary

All 14 targets below have been confirmed unreachable from `AgentExecutionLoop`, `OrbitOrchestrator`, `APIGatewayService`, and `PrimitiveExecutionController`.

| # | Target Path / Subsystem | Primary Legacy Classes Removed | Reachability Status | Action |
|---|------------------------|--------------------------------|---------------------|--------|
| 1 | `src/orbit/runtime/task_understanding/` | `TaskUnderstandingEngine`, `IntentClassifier`, `SlotExtractor` | 0 Active Callers | `DELETE DIR` |
| 2 | `src/orbit/runtime/planning/` | `TaskPlanningEngine`, `PlanDecomposer`, `PlanValidator` | 0 Active Callers | `DELETE DIR` |
| 3 | `src/orbit/runtime/execution/` | `ClosedLoopExecutionEngine` | 0 Active Callers | `DELETE DIR` |
| 4 | `src/orbit/runtime/replanning/` | `DynamicReplanner`, `PlanRepairEngine`, `ExecutionFailureAnalyzer` | 0 Active Callers | `DELETE DIR` |
| 5 | `src/orbit/runtime/plan_execution/` | `PlanExecutor`, `PlanExecutionScheduler`, `PlanStepCompiler` | 0 Active Callers | `DELETE DIR` |
| 6 | `src/orbit/runtime/task_completion/completion_engine.py` | `TaskCompletionEngine` | 0 Active Callers | `DELETE FILE` |
| 7 | `src/orbit/runtime/capabilities/execution/` | `StrategyExecutionEngine`, `CapabilityExecutor`, `DrawingExecutor` | 0 Active Callers | `DELETE DIR` |
| 8 | `src/orbit/runtime/capabilities/feasibility.py` | `FeasibilityAnalyzer` | 0 Active Callers | `DELETE FILE` |
| 9 | `src/orbit/runtime/capabilities/environment_discovery.py` | `EnvironmentCapabilityDiscovery` | 0 Active Callers | `DELETE FILE` |
| 10 | `src/orbit/runtime/capabilities/matcher.py` | `CapabilityMatcher` | 0 Active Callers | `DELETE FILE` |
| 11 | `src/orbit/runtime/capabilities/composition.py` | `CapabilityCompositionEngine`, `CompositeCapability` | 0 Active Callers | `DELETE FILE` |
| 12 | `src/orbit/runtime/capabilities/strategy_selector.py` | `StrategySelector` | 0 Active Callers | `DELETE FILE` |
| 13 | `src/orbit/runtime/agent/legacy_adapter.py` | `LegacyActionAdapter` | 0 Active Callers | `DELETE FILE` |
| 14 | `src/orbit/runtime/cognitive/loop.py` | `CognitiveExecutionLoop` | 0 Active Callers | `DELETE FILE` |

---

## 2. Canonical ASTRA-6 Successor Mapping

| Deprecated / Removed Component | Canonical ASTRA-6 Replacement |
|--------------------------------|-------------------------------|
| `TaskUnderstandingEngine` | `LLMIntentInterpreter` + `ClarificationManager` |
| `TaskPlanningEngine` | `HierarchicalGoalDecomposer` + `ProgressGraph` + `AgentPlanner` |
| `FeasibilityAnalyzer` / `StrategySelector` | `SemanticFeasibilityEvaluator` + `RuntimeFeasibilityEvaluator` |
| `ClosedLoopExecutionEngine` / `PlanExecutor` | `AgentExecutionLoop` |
| `DynamicReplanner` / `ExecutionFailureAnalyzer` | `CognitiveFailureAnalyst` + `AgentRecoveryManager` + `AgentPlanner` |
| `TaskCompletionEngine` | `MultiEvidenceActionVerifier` (step) + `GoalVerifier` (task) |
| `DrawingExecutor` | `PrimitiveComposer` (DRAW_STROKES) → `GroundingValidator` → `CanvasDrawingProvider` → `PointerCapability` |
| `LegacyActionAdapter` | Canonical `AbstractAction` + `PrimitiveValidator` |
| `CognitiveExecutionLoop` shim | `AgentExecutionLoop` |

---

## 3. Physical Deletion Safety Guarantee

1. **No Production Execution Bypass**: All UI/OS interactions flow strictly through `PrimitiveExecutionController`.
2. **No Decision Divergence**: Only `AgentPlanner` emits plan directives and `CognitiveDecisionEngine` decides executable actions.
3. **No Legacy Imports**: `src/orbit/runtime/__init__.py`, `capabilities/__init__.py`, `task_completion/__init__.py`, and `cognitive/__init__.py` export clean canonical interfaces.
