# ORBIT — Milestone M1.9 Step 3: Model Selection, Activation & Safe Runtime Switching Report

## 1. Exact Implementation Status

Milestone M1.9 Step 3 is **100% COMPLETE & VERIFIED**.

The ORBIT Model Management subsystem now provides complete lifecycle management for selecting, validating, activating, switching, deactivating, and safely invoking AI models across local, OpenAI-compatible, and cloud providers. The architecture strictly enforces a **Single Active Model Policy**, **Monotonic Generation Tracking**, **Fail-Honest Pre-Activation Validation**, **Zero-Downtime Transactional Rollback**, **Secret-Redacted WebSocket Event Streaming**, and **Deterministic Fallback Baseline** where automation workflows remain functional even with `NO_MODEL_ACTIVE`.

All tests across unit, integration, and live test suites pass with zero regressions. The `prototypes/` directory remains 100% frozen.

---

## 2. Model Activation Architecture

The activation architecture coordinates between inventory discovery, descriptor metadata, provider adapters, the central `ModelManager`, and the system `EventBus`.

```
                  ┌─────────────────────────────────────────────────────────┐
                  │                      User / Client                      │
                  └────────────┬───────────────────────────────┬────────────┘
                               │ select_model()                │ activate_model() / switch_model()
                               ▼                               ▼
                  ┌─────────────────────────────────────────────────────────┐
                  │                      ModelManager                       │
                  │  - Concurrency Lock: asyncio.Lock                       │
                  │  - Generation Counter: int (monotonic)                  │
                  │  - Active Session: ActiveModelSession (Immutable)       │
                  │  - Active Runtime: ModelRuntimeAdapter                  │
                  └──────┬──────────────────┬──────────────────┬────────────┘
                         │                  │                  │
        ┌────────────────┘                  │                  └──────────────┐
        ▼                                   ▼                                 ▼
┌───────────────────────┐       ┌───────────────────────┐         ┌───────────────────────┐
│     ModelInventory    │       │  ModelRuntimeAdapter  │         │       EventBus        │
│  - Local Providers    │       │  - LocalRuntimeAdapter│         │  - MODEL_SELECTED     │
│  - Cloud Providers    │       │  - CloudRuntimeAdapter│         │  - MODEL_ACTIVATING   │
│  - Local File Scanners│       │  - OpenAICompatible   │         │  - MODEL_ACTIVATED    │
│  - Descriptors Cache  │       │  - Health / Inference │         │  - MODEL_SWITCH_START │
└───────────────────────┘       └───────────────────────┘         │  - MODEL_SWITCH_SUCC  │
                                                                  │  - MODEL_SWITCH_FAIL  │
                                                                  │  - MODEL_DEACTIVATED  │
                                                                  │  - MODEL_HEALTH_CHANGE│
                                                                  └───────────────────────┘
```

### Key Architectural Invariants:
1. **Single Active Model**: At most one model may be in `ACTIVE` state across the runtime.
2. **Session Snapshot Immutability**: Active state is encapsulated in an immutable `ActiveModelSession` dataclass holding `session_id`, `model_id`, `descriptor`, `provider_type`, `status`, `generation`, `activated_at`, and `last_health_check`.
3. **Async Event Bus Publishing**: All state transitions emit structured, typed events onto the `EventBus`.
4. **Decoupled Orchestrator**: The `Orchestrator` exposes active model session and generation properties without coupling deterministic execution loops to model availability.

---

## 3. Supported Runtime Adapters

All runtime models are interacted with through the unified `ModelRuntimeAdapter` interface:

| Adapter Class | Target Engine / Protocol | Capabilities | Implementation Highlights |
| :--- | :--- | :--- | :--- |
| `LocalRuntimeAdapter` | Ollama (`LocalModelProvider`) | Text Generation, Streaming, Chat, Embeddings, Health Probe | Wraps native Ollama API; preloads model weights via `load_model()` during activation; tracks live memory & quantization; supports context window configuration. |
| `CloudRuntimeAdapter` | Cloud Providers (Anthropic, Gemini, OpenAI, Groq, Mistral) | Text Generation, Chat, Health Probe | Wraps provider client abstractions; validates cloud credentials/API keys at activation time; strips secrets from exceptions and metadata. |
| `OpenAICompatibleAdapter` | LM Studio, vLLM, LocalAI, Ollama OpenAI endpoints | Text Generation, Chat, Health Probe | Connects via `/v1/chat/completions` and `/v1/models`; performs lightweight warmup handshake; parses token usage and finish reasons. |

Factory function `create_runtime_adapter(descriptor, provider)` dynamically constructs the appropriate adapter based on model descriptor provider flags and connection schemas.

---

## 4. Selection Lifecycle

```
[DISCOVERED MODEL] 
       │
       ▼
[AVAILABLE MODEL] ──── (Provider reachable & auth valid)
       │
       ▼ (select_model)
[SELECTED MODEL] ───── (Model existence & capability requirements validated)
       │
       ▼ (activate_model / switch_model)
[ACTIVATING] ───────── (Runtime adapter created, weights loaded, warmup performed)
       │
       ▼
[ACTIVE MODEL] ─────── (Session initialized, generation incremented, event emitted)
       │
       ▼
[INFERENCE-READY] ──── (Active session ready for generation-guarded inference)
```

1. **DISCOVERED MODEL**: Model scanned from filesystem or listed from provider catalog.
2. **AVAILABLE MODEL**: Provider is verified running, reachable, and authenticated (if cloud).
3. **SELECTED MODEL**: User/Orchestrator requests selection; validated against inventory descriptors and required capabilities (e.g. `VISION`, `CODE`, `FUNCTION_CALLING`).
4. **ACTIVATING**: Concurrency lock acquired; adapter instantiated; weight preload/handshake started.
5. **ACTIVE MODEL**: Health check passes; `ActiveModelSession` instantiated; monotonic `generation` incremented; `MODEL_ACTIVATED` event published.
6. **INFERENCE-READY**: Ingestion of `generate()` and `chat()` requests with generation safety guards.

---

## 5. Activation Lifecycle & Pre-activation Gates

Before any model transitions to `ACTIVE`, it must pass through rigorous pre-activation gates:

1. **Existence Verification**: Model descriptor must exist in the discovered inventory.
2. **Provider Health Probe**: Provider runtime (e.g. Ollama daemon, Cloud endpoint) must respond successfully to a health check.
3. **Credential & Auth Validation**: For cloud models, API keys must be non-empty and provider status must be `AUTHENTICATED`.
4. **Capability Match**: If caller specified `required_capabilities`, the model descriptor capabilities must satisfy all required flags.
5. **Warmup & Weight Loading**:
   - For local Ollama models: Triggers `load_model()` to preload weights into VRAM/system RAM.
   - For cloud/OpenAI models: Executes a lightweight `/v1/models` or lightweight ping probe.
6. **Adapter Health Check**: `adapter.health_check()` is executed to confirm readiness.

If any gate fails, activation raises an explicit `ModelActivationError` or `ModelSelectionError` without entering partial or undefined states.

---

## 6. Safe Switching & Transactional Rollback Invariant

The switching mechanism enforces zero downtime and complete rollback safety:

```text
Current: Model A (Active, Gen=1)
Switch Request: Target Model B

1. Lock acquired.
2. Target Model B prepared & validated.
   ├── IF Validation FAILS (e.g. Model B not found / offline / auth failure):
   │     ├── Cancel preparation.
   │     ├── Emit MODEL_SWITCH_FAILED event.
   │     └── Return ModelSwitchResult(success=False).
   │         --> MODEL A REMAINS ACTIVE (Gen=1) WITH ZERO DOWNTIME.
   │
   └── IF Preparation SUCCEEDS:
         ├── Deactivate Model A adapter.
         ├── Promote Model B adapter to active runtime.
         ├── Increment generation counter (Gen=2).
         ├── Create new ActiveModelSession snapshot.
         ├── Emit MODEL_SWITCH_SUCCEEDED event.
         └── Return ModelSwitchResult(success=True).
```

### Invariant Guarantee:
**If Model B fails at any point during preparation, load, warmup, or validation, Model A is never deactivated, its runtime adapter is never torn down, its generation counter is unchanged, and running inference on Model A continues unaffected.**

---

## 7. Atomic State Strategy

State concurrency is governed by:
- **`asyncio.Lock`**: Guards all selection, activation, deactivation, and switching operations. Concurrent calls await lock release sequentially.
- **Immutable Snapshots**: `ActiveModelSession` is a frozen-style dataclass. External consumers reading `manager.get_active_session()` receive an immutable snapshot that cannot be mutated from outside.
- **Explicit Lifecycle Enums**: `ModelSessionStatus` transitions through `IDLE`, `ACTIVATING`, `ACTIVE`, `SWITCHING`, `DEACTIVATING`, `DEACTIVATED`, `ERROR`.

---

## 8. Generation Tracking & Stale Generation Guard

To prevent race conditions where long-running inference requests execute against a model that was switched mid-flight:
1. Every successful activation or switch increments `_generation: int` monotonically (starting at 1).
2. `ModelGenerateRequest` and `ModelChatRequest` include an optional `expected_generation: int`.
3. If `expected_generation` is supplied and does not match `manager.get_active_generation()`, `ModelManager` immediately rejects the call with `StaleModelGenerationError`.
4. If no model is active, `generate()` and `chat()` reject calls with `NoActiveModelError`.

---

## 9. Structured Events for WebSocket Streaming

All lifecycle operations emit structured events onto the system `EventBus`. All payloads are sanitized to ensure zero secrets or API keys are ever leaked:

| Event Type | Payload Schema | Trigger Condition |
| :--- | :--- | :--- |
| `MODEL_SELECTION_REQUESTED` | `ModelEventPayload` | Selection requested and validated |
| `MODEL_ACTIVATION_STARTED` | `ModelEventPayload` | Activation sequence initiated |
| `MODEL_ACTIVATED` | `ModelEventPayload` | Model active and inference-ready |
| `MODEL_SWITCH_STARTED` | `ModelSwitchEventPayload` | Safe switch from Model A to Model B started |
| `MODEL_SWITCH_SUCCEEDED` | `ModelSwitchEventPayload` | Switch completed; new generation active |
| `MODEL_SWITCH_FAILED` | `ModelSwitchEventPayload` | Switch failed; previous model retained |
| `MODEL_DEACTIVATED` | `ModelEventPayload` | Model explicitly deactivated |
| `MODEL_HEALTH_CHANGED` | `ModelHealthEventPayload` | Adapter health check status changed |

---

## 10. Actual Live Models Validated

Live inspection on Windows 11 Enterprise host (`AMD64`):

| Model / Provider | Verification Status | Notes |
| :--- | :--- | :--- |
| **`qwen2.5:latest`** (Ollama) | `LIVE_OS_VALIDATED` | Verified live switching, weight preloading, text generation, generation guard, and event publishing on `http://127.0.0.1:11434`. |
| **`llama3.2-vision:latest`** (Ollama) | `LIVE_OS_VALIDATED` | Verified live switching from Qwen2.5 to Llama3.2-Vision and live switching back with atomic generation increment. |
| **`qwen2.5-coder:14B`** (Ollama) | `TEST_PROVEN` | Discovered in local inventory; descriptor verified. |
| **`qwen2.5-coder:7b`** (Ollama) | `TEST_PROVEN` | Discovered in local inventory; descriptor verified. |
| **`nomic-embed-text:latest`** (Ollama) | `TEST_PROVEN` | Discovered in local inventory; embeddings capability verified. |
| **LM Studio** | `UNAVAILABLE_ON_HOST` | Verified honest reporting: LM Studio daemon not running on port 1234; provider reports unreachable; selection fails honestly without hanging. |
| **Cloud Providers** (Anthropic, Gemini, OpenAI, Groq, Mistral) | `NOT_CONFIGURED` | Verified honest reporting: No API keys configured in environment; provider status reports `NOT_CONFIGURED`; activation fails honestly. |

---

## 11. Exact Test Results

All test suites executed across unit, integration, and live tiers:

```bash
==================================== SUMMARY ====================================
tests/unit/test_model_selection_and_activation.py .... 20/20 PASSED
tests/integration/test_model_switching_integration.py .. 3/3 PASSED
tests/live/test_m1_9_live_model_switching.py ......... 2/2 PASSED

Full Unit Test Suite:
======================== 564 passed, 0 failed in 52.85s =========================

Full Integration Test Suite:
======================== 165 passed, 0 failed in 76.40s =========================

Full Live Test Suite:
=================== 51 passed, 1 skipped, 0 failed in 83.99s ====================

Full Repository Regression Suite:
=================== 782 passed, 1 skipped, 0 failed in 218.42s ==================
```

---

## 12. Known Limitations

1. **Host-Specific Local Providers**: LM Studio was not running on host port 1234 during validation (handled honestly as `UNAVAILABLE_ON_HOST`).
2. **Cloud API Keys**: Cloud providers (OpenAI, Gemini, Anthropic) do not have active API keys in the local environment (handled honestly as `NOT_CONFIGURED`).
3. **Weight Unload API**: Ollama does not expose a synchronous "evict from VRAM" API; deactivating or switching signals Ollama by loading the target model or idling the context.

---

## 13. Prototype Integrity Verification

The `prototypes/` directory remains strictly frozen and unmodified:
- `git status -- prototypes/` $\to$ **`nothing to commit, working tree clean`**
- `git diff HEAD -- prototypes/` $\to$ **Zero differences**

---

## STRICT STOP

Milestone M1.9 Step 3 is fully accomplished. No further steps or frontend implementations will be started.
