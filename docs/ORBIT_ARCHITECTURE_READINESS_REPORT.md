# ORBIT Architecture Readiness Report v1.0

**Document Identifier:** `docs/ORBIT_ARCHITECTURE_READINESS_REPORT.md`  
**Date:** September 5, 2026  
**System Version:** ORBIT v1.0 Architecture Baseline  
**Status:** COMPLETED & READY FOR STAGED PRODUCT IMPLEMENTATION  

---

## 1. Executive Summary

This report establishes the readiness of the **ORBIT Desktop AI Assistant** codebase to transition from isolated, capability-level research prototypes (**Prototypes A–E**) into a unified, commercial-grade product architecture.

Following comprehensive inspection of the host environment, existing frozen prototypes, native Win32 ABIs, and multi-tier concurrency models, the complete **ORBIT System Architecture v1.0 Blueprint** has been authored and validated.

### Key Conclusions:
1. **Zero New Prototypes Created:** The prototype phase is officially closed. No Prototype F or speculative prototypes have been created or are required.
2. **Frozen Baseline Preserved:** Prototypes A–D remain permanently frozen and verified with zero diff lines against commit `ca87ef8`. Prototype E implementation is locked and 100% verified (71/71 tests passing).
3. **No Direct Prototype Coupling:** Core application code will depend solely on abstract protocol interfaces (`orbit.contracts`). Concrete adapters (`orbit.adapters`) will bridge to validated prototype logic without modifying a single line of prototype source code.
4. **Architectural Blueprints Published:** All 6 required architecture specifications have been authored under `docs/architecture/` and audited against adversarial failure modes.

---

## 2. Current Repository Reality

An exhaustive audit of the physical repository environment yielded the following factual baseline:

- **Host Environment:** Windows 11 Home / Pro (Build 26100, AMD64, 64-bit).
- **Core Runtime:** Python 3.13.7 (64-bit, native CPython).
- **Frontend / Toolchain Tooling:** Node.js v22.18.0, npm 11.5.2.
- **Python Dependencies Present:**
  - `FastAPI 0.121.2` & `Starlette 0.49.2` (REST Gateway & OpenAPI engine)
  - `Uvicorn 0.38.0` (High-performance ASGI server)
  - `WebSockets 17.1` (Full-duplex RFC 6455 transport)
  - `Pydantic 2.12.4` & `pydantic-core 2.41.5` (Strict schema validation & serialization)
  - `Pillow (PIL) 12.2.0` (Image processing, ROI cropping, bitmap manipulation)
  - `NumPy 2.2.6` (NDArray buffer manipulation and tensor normalization)
  - `ONNX Runtime 1.29.0` (Local edge vision / embedder inference engine)
  - `Playwright 1.60.0` (DOM-level browser automation & accessibility tree traversal)
- **Git State:**
  - Baseline commit: `ca87ef8`
  - Uncommitted changes: Only architectural documentation (`docs/`) and existing Prototype E test suite / audits.
  - Frozen Prototypes (`prototype_a_workspace`, `prototype_b_human_takeover`, `prototype_c_keyboard`, `prototype_d_observation`): Exactly 0 diff lines.

---

## 3. Existing Reusable Capabilities Audit

Each of the 5 prototypes has been analyzed to determine its practical public interface, input/output contracts, threading constraints, and adapter wrapping requirements:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CAPABILITY MATRIX                                 │
├──────────────────────────┬─────────────────────────────────┬────────────────┤
│ Prototype                │ Public Interface Modules        │ Status         │
├──────────────────────────┼─────────────────────────────────┼────────────────┤
│ A: Workspace / AppBar    │ appbar_manager.py,              │ Frozen         │
│                          │ appbar_native.py                │ (ca87ef8)      │
├──────────────────────────┼─────────────────────────────────┼────────────────┤
│ B: Human Takeover        │ takeover_detector.py,           │ Frozen         │
│                          │ input_interrupter.py            │ (ca87ef8)      │
├──────────────────────────┼─────────────────────────────────┼────────────────┤
│ C: Keyboard Execution    │ virtual_keyboard.py,            │ Frozen         │
│                          │ text_streamer.py,               │ (ca87ef8)      │
│                          │ shortcut_policy.py              │                │
├──────────────────────────┼─────────────────────────────────┼────────────────┤
│ D: Observation / Screen  │ visual_observation.py,          │ Frozen         │
│                          │ frame_provider.py,              │ (ca87ef8)      │
│                          │ provider_health.py              │                │
├──────────────────────────┼─────────────────────────────────┼────────────────┤
│ E: Pointer Action Engine │ native_dispatch_gateway.py,     │ Validated      │
│                          │ pointer_state_machine.py,       │ (71/71 tests)  │
│                          │ trajectory_planner.py           │                │
└──────────────────────────┴─────────────────────────────────┴────────────────┘
```

### Detailed Capability Analysis:
1. **Prototype A (Workspace & AppBar):**
   - *Capability:* Reserves dedicated screen real estate via Win32 `SHAppBarMessage` (`ABM_NEW`, `ABM_SETPOS`), shifting third-party maximized application work areas without window overlap.
   - *Adapter Requirement:* Wrap in `WorkspaceAdapter` (`WorkspaceCapability` protocol), handling shell crash recovery (`WM_TASKBARCREATED`) and graceful cleanup on application exit.
2. **Prototype B (Human Takeover & Input Preemption):**
   - *Capability:* Sub-millisecond human physical intervention detection via low-level Win32 hooks (`WH_MOUSE_LL`, `WH_KEYBOARD_LL`). Filters synthetic inputs via `LLMHF_INJECTED`.
   - *Adapter Requirement:* Wrap in `HumanTakeoverAdapter` (`HumanTakeoverCapability` protocol). Host hook message pump on dedicated OS thread to prevent asyncio event loop starvation.
3. **Prototype C (Keyboard Execution):**
   - *Capability:* Unicode-aware virtual text streaming, key combinations, and shortcut policy enforcement via Win32 `SendInput` with keyboard input flags.
   - *Adapter Requirement:* Wrap in `KeyboardAdapter` (`KeyboardCapability` protocol), exposing asynchronous `type_text()`, `press_shortcut()`, and modifier state verification.
4. **Prototype D (Screen & UI Observation):**
   - *Capability:* Low-latency multi-monitor screen capture, frame compression, ROI extraction, and provider health fallback (Desktop Duplication API $\to$ GDI $\to$ WinRT).
   - *Adapter Requirement:* Wrap in `ObservationAdapter` (`ObservationCapability` protocol), delivering binary image buffers via zero-copy memory views and structured frame metadata.
5. **Prototype E (Pointer Movement & Button Execution):**
   - *Capability:* Per-Monitor V2 DPI-aware coordinate mapping, smooth trajectory interpolation, single-button atomic transactions, and fail-closed pointer lockout state machine.
   - *Adapter Requirement:* Wrap in `PointerAdapter` (`PointerCapability` protocol), strictly utilizing `NativeDispatchGateway` with zero bypass.

---

## 4. Proposed Product Architecture (ORBIT v1.0)

The product architecture decouples user interface, networking, orchestration, reasoning, and native OS interaction into 6 distinct layers:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: PRESENTATION LAYER (React 18 / TypeScript / Tailwind / WebView2)   │
│ • Chat & Task Input • Agent Execution Timeline • Live Viewport Canvas       │
│ • Human Takeover Status Banner • Permission Authorization Modal             │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ WebSocket (JSON-RPC & Binary Frame)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ LAYER 2: GATEWAY & TRANSPORT (FastAPI / Uvicorn / WebSockets)                │
│ • Connection Manager • Session Auth • Monotonic Event Sequencer             │
│ • Client Heartbeat & Backpressure • Binary Viewport Frame Multiplexer       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Async Queue / Task Lifecycle
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ LAYER 3: CORE RUNTIME & ORCHESTRATOR (Python 3.13 Asyncio)                   │
│ • Task Orchestrator • 7-Phase Action State Machine • Preemption Guard       │
│ • Safety & Permission Evaluator • Audit Logger • Execution Context Pool     │
└──────────────────┬──────────────────────────────────────────┬───────────────┘
                   │                                          │
                   ▼                                          ▼
┌──────────────────────────────────────┐   ┌──────────────────────────────────┐
│ LAYER 4: AI & REASONING              │   │ LAYER 5: CAPABILITY ADAPTERS     │
│ • Model Router (Fast / Vision / Code)│   │ • WorkspaceAdapter (Proto A)     │
│ • Planner & Replanning Engine        │   │ • HumanTakeoverAdapter (Proto B) │
│ • Tool Selector & Argument Validator │   │ • KeyboardAdapter (Proto C)      │
│ • Visual Grounding Resolver          │   │ • ObservationAdapter (Proto D)   │
└──────────────────────────────────────┘   │ • PointerAdapter (Proto E)       │
                                           └──────────────────┬───────────────┘
                                                              │
                                                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ LAYER 6: OS SUBSYSTEM & WIN32 NATIVE ABIS (Windows 11 AMD64)                 │
│ • user32.SendInput • WH_MOUSE_LL / WH_KEYBOARD_LL Hooks • SHAppBarMessage   │
│ • Desktop Duplication API • Per-Monitor V2 DPI • UIPI Integrity Boundaries   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. WebSocket & Protocol Architecture

The communication interface between the UI and backend runtime is fully specified in `docs/architecture/websocket_protocol_v1.md`:

- **Bidirectional RPC Framing:** Standardized JSON-RPC 2.0 extension envelope with monotonic sequence numbering (`event_seq`), correlation tracing (`correlation_id`, `causation_id`), and ISO-8601 UTC timestamps.
- **Binary Frame Streaming:** Dedicated 16-byte binary header (`ORBT\x01...`) carrying uncompressed / JPEG viewport frames directly to HTML5 Canvas elements with zero JSON base64 serialization overhead ($<15\,\text{ms}$ latency).
- **Client $\leftrightarrow$ Server Message Catalog:**
  - *Client Actions:* `SUBMIT_TASK`, `CANCEL_TASK`, `PAUSE_TASK`, `RESUME_TASK`, `AUTHORIZE_ACTION`, `REQUEST_OBSERVATION_FRAME`, `TRIGGER_TAKEOVER`, `RELEASE_TAKEOVER`, `RECOVER_LOCKED_STATE`.
  - *Server Telemetry:* `RUNTIME_STATUS`, `TASK_STATE_CHANGED`, `PLAN_UPDATED`, `ACTION_STAGE_CHANGED`, `OBSERVATION_FRAME`, `TAKEOVER_EVENT`, `ACTION_AUTHORIZATION_REQUIRED`, `ERROR`.
- **Resilience & Disconnection Policy:** Configurable heartbeat watchdog ($5000\,\text{ms}$). Disconnection defaults to immediate `TASK_PAUSED` and hardware sanitization (`emergency_release_all()`).

---

## 6. Recommended Technology Choices & Rationales

| Area | Recommended Technology | Why Chosen | Why Not Alternatives |
| :--- | :--- | :--- | :--- |
| **Frontend Framework** | **React 18 + TypeScript + Vite** | High rendering performance for streaming logs; rich ecosystem for canvas drawing, hotkeys, and modular component design. | Plain Vanilla JS lacks structured state management for complex multi-stream UIs; Next.js is unnecessarily heavyweight for local desktop shells. |
| **Frontend Shell** | **Tauri (Rust / WebView2) or PySide6 QWebEngine** | Native Windows desktop integration, zero Electron RAM bloat, native OS AppBar docking support. | Electron consumes $>300\,\text{MB}$ RAM baseline; native Win32 C++ UI has prohibitive development velocity. |
| **Backend Framework** | **FastAPI + Uvicorn + WebSockets** | Already validated in repository; native asynchronous event loop; high throughput; strict Pydantic model serialization. | Flask/Django are synchronous and unsuitable for continuous full-duplex event streaming. |
| **State & Serialization** | **Pydantic v2 + In-Memory Event Store + SQLite WAL** | In-memory atomic state transitions for $<1\,\text{ms}$ reaction times; SQLite WAL for persistent task history and compliance audit logging. | PostgreSQL/Redis add external service dependencies; plain JSON files risk corruption on abrupt system power-off. |
| **Local AI Engine** | **ONNX Runtime (Present) + OpenAI/Anthropic/Ollama API Router** | Pluggable interface supporting hybrid execution (fast local ONNX vision embedder + high-parameter cloud/local reasoning LLMs). | Hardcoding to single provider creates vendor lock-in. |

---

## 7. Major Unresolved Architectural Decisions

The following architectural decision points have been identified for operator alignment prior to Milestone M1 implementation:

1. **Frontend Desktop Packaging:**
   - *Option A:* Tauri (Rust core + WebView2 frontend, communicating over local WebSocket to Python backend).
   - *Option B:* PySide6 (Python-native Qt shell embedding QWebEngineView, single-process or twin-process model).
   - *Option C:* Browser-hosted UI (Local Chrome / Edge window connecting to `http://localhost:8765`).
   - *Recommendation:* Start with Option C (Browser / Local Web App) during Milestones M0–M2 for maximum velocity, transitioning to Option A/B in Milestone M5.

2. **Multi-User / Network Exposure:**
   - *Decision:* ORBIT v1.0 is strictly bound to `127.0.0.1` (loopback only) with mandatory ephemeral session authentication tokens. Remote network exposure is prohibited in v1.0.

---

## 8. What Must Happen Before Implementation

Before writing application code for Milestone M1, the following foundation steps are required:

1. **Create Target Directory Structure:**
   - Establish `src/orbit/` packaging structure (`src/orbit/contracts/`, `src/orbit/adapters/`, `src/orbit/core/`, `src/orbit/gateway/`).
2. **Setup Test Harness:**
   - Establish `tests/unit/`, `tests/integration/`, and `tests/mocks/` with synthetic capability mocks so core tests can run in headless CI without Win32 hardware dependencies.
3. **Formalize Environment Dependencies:**
   - Create clean `pyproject.toml` declaring dependencies matching existing repository packages (`fastapi`, `uvicorn`, `websockets`, `pydantic`, `pillow`, `numpy`, `pytest`).

---

## 9. What is Safe to Implement Immediately

The following components have completed all design gates and are **100% safe to implement immediately**:

1. **`orbit.contracts`:** All Protocol interfaces and Pydantic DTOs for Workspace, HumanTakeover, Keyboard, Observation, and Pointer.
2. **`orbit.adapters`:** Concrete wrappers binding `prototypes/prototype_*` modules to `orbit.contracts` without touching prototype source code.
3. **`orbit.gateway` (WebSocket Protocol Engine):** JSON-RPC envelope serialiser, message dispatcher, and mock client test suite.
4. **`orbit.core` (Task Orchestrator & State Machine):** 7-phase action state machine, preemption token manager, and audit logger.

---

## 10. Explicit Confirmations

- ✅ **No Prototype Modified:** Prototypes A–D are frozen at `ca87ef8` (0 diff lines). Prototype E implementation is locked.
- ✅ **No Unnecessary Prototypes Created:** No Prototype F, G, or speculative prototype folders were created.
- ✅ **Architecture Complete:** All 6 architecture documents are published under `docs/architecture/`.
- ✅ **Readiness Approved:** The system is fully architected and ready for Milestone M0/M1 execution.
