# ORBIT Vision & Architecture Roadmap: Gap Remediation & Autonomous Execution

## 1. Executive Summary

This document establishes the official phased execution plan to bridge the gap between ORBIT's current capabilities and the target vision for comprehensive, multi-modal, and generative desktop autonomy.

### Gap Analysis Matrix

| Area | Target Vision | ORBIT Current State | Severity / Gap | Target Phase |
| :--- | :--- | :--- | :--- | :--- |
| **User Intent Understanding** | High-level goal & nuance recognition | StructuredObjective conversion | 🟢 Largely Solved | Foundation |
| **Task Planning** | Dynamic hierarchical sub-goal generation | Cognitive Decision Engine & static rules | 🟡 Needs flexibility | **Phase 1** |
| **Screen Understanding** | Unified semantic visual perception | Fragmented OCR, UIA, Win32 adapters | 🔴 Perception fragmented | **Phase 2** |
| **Unknown UI Understanding** | Visual reasoning over unfamiliar UIs | Heavy reliance on known registered UIA | 🔴 Major gap | **Phase 2** |
| **Next Action Selection** | Goal + visual context + historical reasoning | Rules → Recovery → Constrained LLM | 🟡 Constrained reasoning | **Phase 1 & 4** |
| **Closed-Loop Execution** | Observe → Act → Observe → Adapt | Cognitive execution loop | 🟢 Strong | Maintained |
| **Mouse & Keyboard Control** | Reliable physical execution | Capability adapters & physical executors | 🟢 Strong foundation | Maintained |
| **Coordinate Handling** | Spatial grounding to physical coords | `SemanticTarget` & runtime coordinate resolution | 🟢 Architecturally strong | Maintained |
| **Target Detection** | Identification of visual-only targets | `EvidenceBasedTargetLocator`, UIA, Win32 | 🟡 Limited visual-only | **Phase 2** |
| **After-Action Observation** | Systematic re-evaluation of environment | Live state re-observation | 🟢 Implemented correctly | Maintained |
| **Self-Correction** | Dynamic strategy reformulation | Recovery rules and escalation | 🟡 Needs visual intelligence | **Phase 4** |
| **Action Verification** | Effect verification per primitive action | Dispatch vs. effect vs. goal verification | 🟢 Very strong design | Maintained |
| **Goal Verification** | Multi-modal goal completion verification | Semantic Goal Verifier | 🟡 Needs visual perception | **Phase 4** |
| **Capability Awareness** | Registry, Matcher, Feasibility Analyzer | Registry, Matcher, Feasibility Analyzer | 🟢 Strong recent baseline | Maintained |
| **Capability Selection** | Selection of optimal tool/approach | `StrategySelector` & `CapabilityMatcher` | 🟢 Good foundation | Maintained |
| **Capability Composition** | Multi-tool pipelines & workflows | Single registered capability evaluation | 🔴 Major missing layer | **Phase 3** |
| **Generative Execution** | On-the-fly action/stroke synthesis | Static capability or reject | 🔴 Critical gap | **Phase 3** |
| **Creative Tasks** | Generative visual & spatial actions | Registered basic drawing primitives | 🔴 Major limitation | **Phase 3** |
| **Complex Scene Execution** | Object, spatial & relational decomposition | Reduces complex prompt to 1 primitive | 🔴 Major gap | **Phase 1** |
| **Example: “Draw House, Lake, Sun”** | Decomposes scene into distinct elements | Matches single primitive or drops | 🔴 Incomplete decomposition | **Phase 1 & 3** |
| **Unknown Task Handling** | Visual exploration & trial adaptation | Classifies task as unsupported | 🔴 Major difference | **Phase 4** |
| **Dynamic Tool Usage** | Broad tool ecosystem & runtime plugins | Static capability registry | 🔴 Missing | **Phase 3** |
| **Long-Horizon Tasks** | Multi-step context & state tracking | History and execution budgets | 🟡 Context management | **Phase 1 & 4** |
| **Failure Handling** | Alternative route exploration | Budgeted retries → fail-closed | 🟡 Limited alternatives | **Phase 4** |
| **Generalization** | Reasoning over novel interfaces | Strongest on known capabilities | 🔴 Core limitation | **Phase 2 & 4** |
| **Safety** | Policies, confirmations, containment | Safety locks, fail-closed, takeover | 🟢 Strong | Preserved |
| **Auditability** | Forensic logging & decision tracking | Structured evidence & telemetry | 🟢 Strong foundation | Preserved |

---

## 2. Phased Architecture Roadmap

```
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                               PHASED EXECUTION ROADMAP                                │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                       │
│  PHASE 1: Hierarchical Goal & Scene Decomposition                                     │
│  ├── DecomposedObjectivePlan & SubObjective Schema                                    │
│  ├── HierarchicalGoalDecomposer (LLM Spatial & Logical Decomposer)                    │
│  └── Sub-Goal Sequential / DAG Execution Orchestrator                                 │
│                                                                                       │
│  PHASE 2: Unified Hybrid Perception & Visual Grounding                                │
│  ├── VLM-Powered Visual Grounding Adapter (Set-of-Marks / Normalized Coordinates)     │
│  ├── Tier-3 Escalation in EvidenceBasedTargetLocator                                  │
│  └── Screen Understanding for Unknown UIs & Canvas Applications                       │
│                                                                                       │
│  PHASE 3: Capability Composition & Generative Execution                               │
│  ├── Multi-Capability Pipeline & Chaining Engine (CapabilityComposer)                │
│  ├── Generative Action Synthesizer (Parametric Geometry & Stroke Engine)              │
│  └── Dynamic Tool / Provider Ecosystem Integration                                   │
│                                                                                       │
│  PHASE 4: Autonomous Exploration, Adaptive Recovery & Visual Verification             │
│  ├── Screenshot Delta & Visual Effect Verifier                                        │
│  ├── Active UI Exploration Engine (Menus, Hotkeys, Ribbons)                           │
│  └── Contextual Replanning & Long-Horizon State Management                            │
│                                                                                       │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Phase Breakdown

### Phase 1: Hierarchical Goal & Scene Decomposition
* **Target Objective:** Ensure multi-step, relational, or multi-object goals (e.g., *"Draw a house, lake, and sun in Paint"*) are never reduced to a single primitive action or rejected as unsupported.
* **Key Deliverables:**
  1. **Data Contracts (`src/orbit/runtime/models/decomposition.py`):**
     - `SubObjective`: Target entity, spatial region, expected visual outcome, prerequisites.
     - `DecomposedPlan`: Ordered sequence or Directed Acyclic Graph (DAG) of `SubObjective` nodes.
  2. **Decomposer Module (`src/orbit/runtime/cognition/goal_decomposer.py`):**
     - Analyzes high-level `StructuredObjective`.
     - Deconstructs creative scenes into spatial and chronological elements (Background -> Main Subjects -> Details).
  3. **Multi-Goal Plan Compiler Integration (`src/orbit/runtime/plan_execution/compiler.py`):**
     - Compiles each `SubObjective` into executable runtime plans.
     - Tracks sub-goal completion status and prerequisites.
* **Success Criteria:**
  - *"Draw a house, lake, and sun"* generates at least 3 distinct sub-objectives with individual targets and execution orders.
  - Sub-goals execute in logical sequence with separate state checkpoints.

---

### Phase 2: Unified Hybrid Perception & Visual Grounding
* **Target Objective:** Enable ORBIT to understand and click any element on screen—including unfamiliar applications, custom web widgets, and non-accessible canvases (Paint, Figma, games)—where Win32/UIA accessibility returns empty trees.
* **Key Deliverables:**
  1. **Visual Grounding Adapter (`src/orbit/runtime/perception/visual_grounder.py`):**
     - Consumes screen captures.
     - Employs Vision-Language Model (VLM) grounding (Set-of-Marks / normalized coordinate prediction `[ymin, xmin, ymax, xmax]`).
  2. **Locator Tier Escalation (`src/orbit/runtime/targeting/locator.py`):**
     - **Tier 1:** Native Win32/UIA Accessibility (Fastest, 0-cost, exact bounding boxes).
     - **Tier 2:** OCR Lexical Matching (Text on buttons, menus, dialogs).
     - **Tier 3 (New):** Visual Grounding Engine (Visual icons, color swatches, canvas surfaces, custom controls).
  3. **Coordinate Bridge:** Converts visual coordinates directly into ORBIT's `SemanticTarget` and `ResolvedCoordinate` without altering downstream executor contracts.
* **Success Criteria:**
  - Successfully locates and clicks UI elements in applications with 0 accessibility elements.
  - Resolves non-textual targets such as "the blue paint brush icon" or "top-center of the drawing canvas".

---

### Phase 3: Capability Composition & Generative Execution
* **Target Objective:** Allow ORBIT to synthesize creative actions (drawing shapes, generating assets) and chain multiple tools together when no single pre-packaged capability satisfies the prompt.
* **Key Deliverables:**
  1. **Capability Composer (`src/orbit/runtime/capabilities/composer.py`):**
     - Chains outputs of one capability into inputs of another.
     - Example: `ImageGenProvider` -> Temp Asset -> File Importer -> Canvas Placement.
  2. **Generative Stroke Synthesizer (`src/orbit/runtime/capabilities/execution/generative_stroke.py`):**
     - Parametric shape generator (rectangles, triangles, circles, bezier curves, landscape contours).
     - Generates sequential mouse down -> move trajectory -> mouse up physical command batches.
  3. **Dynamic Capability Registry Support:**
     - Allows runtime registration of external scripts, CLI providers, or dynamic skills without restarting the runtime.
* **Success Criteria:**
  - Capable of drawing geometric figures and freehand contours on a canvas by generating multi-point trajectories.
  - Can execute chained pipelines without manual user orchestration.

---

### Phase 4: Autonomous Exploration, Adaptive Recovery & Visual Verification
* **Target Objective:** Prevent premature fail-closed aborts by enabling active UI exploration, screenshot-delta verification, and dynamic replanning when actions do not yield the intended screen state.
* **Key Deliverables:**
  1. **Visual Delta Verifier (`src/orbit/runtime/verification/visual_delta.py`):**
     - Compares pre-action and post-action screenshots around the target region.
     - Confirms pixel changes or UI mutations occurred.
  2. **Exploratory Recovery Engine (`src/orbit/runtime/cognition/adaptive_recovery.py`):**
     - If a button or menu is not visible: searches ribbon tabs, attempts standard keyboard accelerators (`Alt`, `Ctrl+Key`), or hovers to inspect tooltips.
     - Employs contextual error feedback to replan rather than repeating the identical failed action.
  3. **Visual Goal Verifier (`src/orbit/runtime/verification/visual_goal.py`):**
     - Evaluates the final screen state against the high-level intent using VLM semantic verification.
* **Success Criteria:**
  - When a primary click fails to achieve the visual effect, the agent tries an alternate path (hotkey or menu) before exhausting budget.
  - Evaluates task success using actual visual screen evidence rather than assuming completion upon action dispatch.

---

## 4. Architectural Invariants (Non-Negotiables)

Throughout all 4 phases, the following ORBIT core invariants must remain intact:
1. **Fail-Closed Safety:** Exploratory actions remain bounded by execution budgets, restricted coordinate zones, and human takeover overrides.
2. **Deterministic Auditability:** Every decomposition decision, VLM coordinate resolution, and capability composition must be logged with structured evidence.
3. **Backward Compatibility:** All existing unit and integration tests (Win32, UIA, Pointer, Keyboard, Model Manager) must continue to pass without regressions.
