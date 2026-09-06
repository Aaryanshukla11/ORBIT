# ORBIT — Milestone M1.9 Step 4: Model Runtime & Safe Switching Engine Architecture

## 1. Executive Summary

Milestone M1.9 Step 4 establishes the formal, production-grade **Model Runtime & Safe Switching Engine** for ORBIT. This architecture decouples model identity, provider discovery, runtime execution, and task orchestration into clear, isolated architectural boundaries.

At runtime, ORBIT enforces a strict hierarchy:
```text
MODEL (Descriptor & Metadata)
    ↓
MODEL REGISTRY (Catalog of Discovered & Validated Models)
    ↓
MODEL RUNTIME FACTORY (Instantiation & Configuration)
    ↓
PROVIDER ADAPTER (Ollama, OpenAI, Anthropic, Gemini, Local Files, Mock)
    ↓
MODEL RUNTIME INSTANCE (BaseModelRuntime Lifecycle & Inference Engine)
    ↓
MODEL SESSION MANAGER (Single Authority for Active State, Safe Switching & Rollback)
    ↓
ACTIVE MODEL CONTEXT (Sanitized Snapshot for Clients & WebSockets)
    ↓
ORBIT ORCHESTRATOR & TASK EXECUTION PIPELINE
```

---

## 2. Forensic Architecture Analysis: Current vs. Proposed

### 2.1 Current Architecture (M1.9 Steps 1-3 Baseline)
Prior to Step 4, model discovery, descriptor indexing, and direct provider calls were managed across `ModelInventory`, `ModelRegistry`, and `ModelManager`. While Step 3 added atomic rollback and monotonic generation counters, the runtime layer lacked a distinct, unified `BaseModelRuntime` lifecycle interface with lazy instantiation, active-task conflict guards, and a dedicated `ModelSessionManager` that cleanly interfaces with task planning.

```text
ORBIT Orchestrator
   ↓
ModelManager (Unified discovery + direct adapter calls)
   ↓
ModelProviders (OllamaProvider, CloudModelProvider, LMStudioProvider)
   ↓
Ad-hoc Execution Invocations
```

### 2.2 Proposed Architecture (M1.9 Step 4 Engine)
Step 4 introduces an explicit, vendor-agnostic `model_runtime` package with clean separation between provider communication, runtime instance lifecycle, session management, and active task coordination:

```text
ModelRegistry / Inventory
       │ (Discovered Descriptors)
       ▼
ModelRuntimeFactory ─── Instantiates ───► Provider Adapters (Ollama / Remote / Mock)
                                                │
                                                ▼
                                         BaseModelRuntime
                                     (initialize, health, generate)
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              ModelSessionManager                                │
│  - Active Runtime Slot (BaseModelRuntime)                                       │
│  - Concurrency Lock (asyncio.Lock)                                              │
│  - Generation Tracker (int monotonic)                                           │
│  - Active Task Conflict Guard (is_task_executing_fn)                            │
│  - Safe Switching State Machine with Rollback Invariant                         │
│  - Secret-Redacted Event Emitter (EventBus)                                     │
└──────────────────────────────────────┬──────────────────────────────────────────┘
                                       │
                        Exposes ActiveModelContext
                                       │
                                       ▼
                             ORBIT Orchestrator
                   (Coordinates Autonomous Task Execution)
```

---

## 3. Core Architectural Components & Ownership

### 3.1 Model Runtime Contracts (`contracts.py`)
- **`ModelRuntimeStatus`**: Lifecycle states of a runtime instance (`UNINITIALIZED`, `INITIALIZING`, `READY`, `ACTIVE`, `BUSY`, `SWITCHING`, `UNAVAILABLE`, `FAILED`, `STOPPING`, `STOPPED`).
- **`ModelRuntimeKind`**: Origin classification (`LOCAL`, `REMOTE`, `UNKNOWN`).
- **`ModelActivationStatus`**: Fine-grained outcome codes (`ACTIVATED`, `ALREADY_ACTIVE`, `SWITCH_REJECTED`, `MODEL_NOT_FOUND`, `MODEL_UNAVAILABLE`, `INITIALIZATION_FAILED`, `ACTIVE_TASK_CONFLICT`, `CANCELLED`, `FAILED`).
- **`ModelSwitchPolicy`**: Concurrency safety policy (`REJECT_DURING_ACTIVE_TASK` [default], `WAIT_FOR_SAFE_CHECKPOINT`, `CANCEL_AND_SWITCH`).
- **`ModelRuntimeHealth`**: Real-time health diagnostic with measured roundtrip latency and error tracking.
- **`ActiveModelContext`**: Sanitized, secret-free metadata snapshot of the active model and runtime.

### 3.2 Base Runtime Interface (`base.py`)
- `BaseModelRuntime(ABC)` enforces lazy initialization:
  - `initialize() -> RuntimeInitializationResult`: Does not allocate memory, GPU VRAM, or connections until explicitly initialized.
  - `health_check() -> ModelRuntimeHealth`: Genuine health probe without mocked responses in production.
  - `generate(request) -> ModelGenerateResponse`: Text generation.
  - `chat(request) -> ModelGenerateResponse`: Structured conversational turn.
  - `shutdown() -> None`: Gracefully shuts down connection pools, idle contexts, or background threads.

### 3.3 Provider Adapters (`providers/`)
- **`OllamaRuntimeAdapter`**: Local runtime adapter interfacing with Ollama daemon (`http://127.0.0.1:11434`), preloading model weights via `/api/generate` with `keep_alive`, verifying installed tags, and streaming completions.
- **`OpenAICompatibleRuntimeAdapter`**: Universal adapter for remote APIs (OpenAI, Anthropic, Gemini, Groq, Mistral, LM Studio, vLLM) with connection verification and credential status tracking (`NOT_CONFIGURED`, `CONFIGURED`, `AVAILABLE`, `UNAVAILABLE`, `AUTHENTICATION_FAILED`).
- **`MockModelRuntimeAdapter`**: Fully controllable mock runtime for testing complex failure modes, latency spikes, active task conflicts, and rollback scenarios.

### 3.4 Model Session Manager (`session_manager.py`)
The `ModelSessionManager` is the **single authority** for active model state in ORBIT.
- Enforces the **Single Active Model Invariant**.
- Implements the **Deterministic Switching State Machine**.
- Coordinates with the Orchestrator via `is_task_executing_fn()` to reject unsafe switches during active execution (`ACTIVE_TASK_CONFLICT`).
- Executes atomic rollback if replacement initialization or warmup fails.
- Increments monotonic `generation: int` on every committed switch.

---

## 4. Model Switching State Machine & Rollback Lifecycle

```text
               ┌──────────────────────┐
               │   NO_ACTIVE_MODEL    │
               └──────────┬───────────┘
                          │ activate_model(M1)
                          ▼
               ┌──────────────────────┐
               │     INITIALIZING     │
               └──────────┬───────────┘
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
    [Init Succeeded]            [Init Failed]
            │                           │
            ▼                           ▼
   ┌─────────────────┐         ┌─────────────────┐
   │  ACTIVE MODEL   │         │     FAILED      │
   │  (M1, Gen = 1)  │         │ (No active mdl) │
   └────────┬────────┘         └─────────────────┘
            │
            │ switch_model(M2)
            ▼
   ┌─────────────────┐
   │ Is Task Running?│ ── YES & Policy=REJECT ──► Return ACTIVE_TASK_CONFLICT
   └────────┬────────┘                            (M1 remains ACTIVE, Gen=1)
            │ NO
            ▼
   ┌─────────────────┐
   │    SWITCHING    │
   │ (Prepare M2)    │
   └────────┬────────┘
            │
            ├───────────────────────────────────────────┐
            ▼                                           ▼
   [M2 Init/Warmup Succeeded]                  [M2 Init/Warmup Failed]
            │                                           │
            │                                           ▼
            │                                  ┌─────────────────┐
            │                                  │    ROLLBACK     │
            │                                  │ (Restore M1)    │
            │                                  └────────┬────────┘
            │                                           │
            │                                           ▼
            ▼                                  ┌─────────────────┐
   ┌─────────────────┐                         │  ACTIVE MODEL   │
   │  ACTIVE MODEL   │                         │  (M1, Gen = 1)  │
   │  (M2, Gen = 2)  │                         └─────────────────┘
   └─────────────────┘
```

### Invariant Guarantees:
1. **Zero-Destruction Precondition**: Model $M_1$ is never shut down or discarded until Model $M_2$ has fully initialized, completed warm-up, and passed its health check.
2. **Atomic Rollback**: If $M_2$ fails at any step, $M_1$ remains active with generation counter unchanged, zero disruption to active contexts, and an event `MODEL_SWITCH_FAILED` is published.
3. **Active Task Guard**: If an autonomous task is currently running and the policy is `REJECT_DURING_ACTIVE_TASK`, the switch is rejected immediately without entering `SWITCHING` state.

---

## 5. Event System & Future WebSocket Integration

All state transitions emit typed events onto the ORBIT `EventBus`:

| Event Type | Trigger | Payload Contents |
| :--- | :--- | :--- |
| `MODEL_ACTIVATING` | Model activation or switch initiated | `model_id`, `provider`, `generation`, `timestamp` |
| `MODEL_ACTIVATED` | Model active and ready | `model_id`, `provider`, `generation`, `capabilities`, `context_window` |
| `MODEL_SWITCH_REQUESTED` | Switch requested | `from_model_id`, `to_model_id`, `policy` |
| `MODEL_SWITCHED` | Switch committed successfully | `previous_model_id`, `active_model_id`, `new_generation` |
| `MODEL_SWITCH_FAILED` | Switch failed / rolled back | `from_model_id`, `target_model_id`, `reason`, `error` |
| `MODEL_HEALTH_CHANGED` | Health probe status changed | `model_id`, `health_status`, `latency_ms` |
| `MODEL_RUNTIME_FAILED` | Active runtime crashed/unresponsive | `model_id`, `error_detail` |
| `MODEL_SHUTDOWN` | Active model shut down | `model_id`, `timestamp` |

### Security Invariant:
**Zero Credential Leakage**: Event payloads, log statements, descriptors, and exceptions are strictly sanitized to strip API keys, Bearer tokens, passwords, and authorization headers.

---

## 6. Orchestrator Integration & Deterministic Baseline

The `OrbitOrchestrator` integrates with `ModelSessionManager` as follows:
- Deterministic planning and tool execution (M1.7/M1.8) operate without degradation when `NO_MODEL_ACTIVE`.
- Model-dependent workflows query `orchestrator.active_model_context` and fail closed honestly with `NO_ACTIVE_MODEL` if no runtime is active.
- `orchestrator.is_task_executing` provides the live predicate for `ModelSessionManager` to enforce active task switching policies.
