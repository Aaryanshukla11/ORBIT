# ORBIT — Milestone M1.8 Step 1 Architecture Note
## Task Understanding & Structured Intent Extraction

**Document Status:** Approved Architecture Reference  
**Author:** ORBIT Core Architecture Team  
**Scope:** M1.8 Step 1 Subsystem (`src/orbit/runtime/task_understanding/`)

---

### 1. Current Task Input Flow & Forensics

Currently in ORBIT (M1.7 baseline):
1. **Submission Path:** External clients submit tasks via WebSocket (`CommandType.SUBMIT_TASK` handled in `websocket_manager.py`) or programmatic API (`OrbitOrchestrator.submit_task(session_id, prompt, metadata)`).
2. **Execution Boundary:** `OrbitOrchestrator._execute_task_lifecycle` inspects `task.metadata`:
   - If `task.metadata.get("target_intent")` exists: Dispatches through `ClosedLoopExecutionEngine.execute_task_action()`.
   - If `target_intent` is missing:
     - If `is_synthetic_development=True`: Runs isolated placeholder plan `_build_synthetic_plan()` with static coordinates `(500, 300)` (restricted strictly to testing harnesses).
     - Otherwise: Fails closed with error `TARGET_INTENT_REQUIRED`.
3. **Exact Limitations:**
   - ORBIT possesses rich perceptual grounding (UIA, OCR, NCC Visual, Multimodal Fusion) and safe closed-loop action execution, but **cannot interpret natural language prompts** autonomously.
   - Every task currently requires pre-structured `TargetIntent` objects injected into metadata by external callers.
   - Natural language instructions ("Open Notepad and type Hello World") cannot be parsed into structured intents.

---

### 2. Proposed Task Understanding Subsystem Architecture

The new subsystem lives in `src/orbit/runtime/task_understanding/`:

```
src/orbit/runtime/task_understanding/
├── __init__.py
├── models.py          # Strongly typed Pydantic data contracts
├── normalizer.py      # Literal-preserving normalization and tokenization
├── parser.py          # Deterministic clause & intent extractor
├── validator.py       # Epistemic validator (ambiguity & constraint checks)
└── engine.py          # TaskUnderstandingEngine facade
```

#### Processing Pipeline:

$$\text{RawTaskRequest} \longrightarrow \text{Normalizer} \longrightarrow \text{Clause Parser} \longrightarrow \text{Intent / Entity / Negation Extractor} \longrightarrow \text{Validator} \longrightarrow \text{TaskUnderstandingResult}$$

---

### 3. Core Data Contracts

1. **`RawTaskRequest`:**
   - `task_id: str`: Unique identifier.
   - `raw_text: str`: Exact original prompt string (preserved untouched).
   - `source: str`: Ingestion origin ("user", "api", "websocket").
   - `timestamp: datetime`: UTC capture timestamp.
   - `metadata: Dict[str, Any]`: Contextual hints.

2. **`TaskGoal` (Minimal Extensible Taxonomy):**
   - `OPEN_APPLICATION`, `CREATE_DOCUMENT`, `WRITE_TEXT`, `SEARCH`, `NAVIGATE`, `CLICK_TARGET`, `SELECT_OPTION`, `COPY_CONTENT`, `PASTE_CONTENT`, `SAVE_DOCUMENT`, `CLOSE_APPLICATION`, `UNKNOWN`, `UNSUPPORTED`.

3. **`TargetReference` (Abstract Semantic Representation):**
   - `semantic_type: str`: e.g. `"application"`, `"ui_control"`, `"text"`, `"document"`, `"file"`, `"window"`, `"unknown"`.
   - `identifier: Optional[str]`: Target label / name (e.g. `"Notepad"`, `"Save"`, `"Calculator"`).
   - `role: Optional[str]`: Control role if declared (e.g. `"button"`, `"edit"`, `"window"`).
   - `anchor: Optional[str]`: Spatial or hierarchical anchor if specified.
   - `is_ambiguous: bool`: Flagged when target is unresolved or generic pronoun.
   - `unresolved_reason: Optional[str]`: Explicit explanation of ambiguity.
   - **SAFETY INVARIANT:** **Zero screen coordinates** allowed in `TargetReference`.

4. **`TaskConstraints`:**
   - `application_name: Optional[str]`: Target application context.
   - `content: Optional[str]`: Exact literal text payload (case, punctuation, and Unicode preserved).
   - `destination: Optional[str]`: Target destination path or area.
   - `source_reference: Optional[str]`: Source data reference.
   - `is_negated: bool`: Negation flag (e.g. "Do not save", "don't type").
   - `negation_details: Optional[str]`: Captured negative constraint.
   - `confirmation_required: bool`: User confirmation requirement.
   - `custom_parameters: Dict[str, Any]`: Structured extra arguments.

5. **`StructuredTaskIntent`:**
   - `intent_id: str`
   - `sequence_index: int`
   - `goal: TaskGoal`
   - `target: Optional[TargetReference]`
   - `constraints: TaskConstraints`
   - `evidence: List[str]` (Deterministic explanations, no fabricated probabilistic numbers)
   - `is_negated: bool`
   - `is_ambiguous: bool`
   - `unresolved_reason: Optional[str]`

6. **`TaskUnderstandingResult`:**
   - `request_id: str`
   - `raw_request: RawTaskRequest`
   - `status: TaskUnderstandingStatus` (`UNDERSTOOD`, `PARTIALLY_UNDERSTOOD`, `AMBIGUOUS`, `UNSUPPORTED`, `INVALID`, `FAILED`)
   - `intents: List[StructuredTaskIntent]` (Ordered intent sequence)
   - `unresolved_constraints: List[str]`
   - `diagnostic_messages: List[str]`
   - `parsed_at: datetime`

---

### 4. Integration Boundary

1. **Orchestrator Ingestion:**
   - `OrbitOrchestrator` integrates `TaskUnderstandingEngine`.
   - Natural language prompts can be understood via `orch.understand_task(prompt)`.
   - When a natural language task is submitted without explicit `target_intent`, `OrbitOrchestrator` runs task understanding and stores the structured result in `task.metadata["task_understanding"]`.
2. **Safe Holding State (Pre-Step 2 Planner):**
   - Step 1 **DOES NOT** implement the multi-step planner.
   - In the absence of M1.8 Step 2 Planner, execution halts safely at the understanding stage and fails closed without attempting autonomous execution or generating synthetic coordinates.
   - Existing structured task execution paths (`target_intent` metadata) remain 100% backward compatible.

---

### 5. Explicit Non-Goals for M1.8 Step 1

1. **No Action Sequence Planning (M1.8 Step 2):** Does not generate executable action trees or step graphs.
2. **No Autonomous OS Execution:** Does not issue pointer moves, clicks, keystrokes, or process launches.
3. **No External LLM / Cloud Dependencies:** Deterministic, local, rule/pattern-based extraction.
4. **No Coordinate Generation:** Target references remain abstract semantic descriptors.
5. **No Modifications to Frozen Prototypes:** `prototypes/` source code remains immutable.
