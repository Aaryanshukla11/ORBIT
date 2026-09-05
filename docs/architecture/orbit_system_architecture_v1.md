# ORBIT System Architecture Specification v1.0
**Document Version:** 1.0.0  
**Status:** APPROVED ARCHITECTURE BLUEPRINT  
**Target Platform:** Windows 11 AMD64  
**Date:** September 2026  

---

## 1. Executive Summary & Core Architectural Invariants

ORBIT (Operating System Reasoning & Behavioral Interaction Taskforce) is an autonomous, safety-first desktop operating system assistant for Windows 11. ORBIT enables local AI models to observe the desktop, synthesize structural understanding, plan multi-step workflows, and interact precisely with applications through native mouse and keyboard actions while maintaining strict human-in-the-loop safety and instantaneous preemption.

The system transitions from five isolated R&D capability prototypes (Prototypes A through E) into a unified, modular, production-grade desktop application.

```text
┌───────────────────────────────────────────────────────────────────────────┐
│                          ORBIT PRODUCT ARCHITECTURE                       │
│                                                                           │
│   ┌───────────────────────────────────────────────────────────────────┐   │
│   │               FRONTEND / DESKTOP SHELL (UI LAYER)                 │   │
│   │   Task Input • Timeline • Observation Feed • Takeover • Approvals │   │
│   └─────────────────────────────────┬─────────────────────────────────┘   │
│                                     │  WebSocket (JSON RPC + Frames)      │
│                                     ▼                                     │
│   ┌───────────────────────────────────────────────────────────────────┐   │
│   │            GATEWAY & API LAYER (FastAPI + AsyncIO Server)         │   │
│   │   Session Lifecycle • Event Dispatcher • Auth • Binary Streaming  │   │
│   └─────────────────────────────────┬─────────────────────────────────┘   │
│                                     │  Internal Typed Event Bus           │
│                                     ▼                                     │
│   ┌───────────────────────────────────────────────────────────────────┐   │
│   │               ORBIT CORE RUNTIME & ORCHESTRATION                  │   │
│   │   Task Engine • Agent Lifecycle • State Machine • Safety Policy   │   │
│   └───────────────┬───────────────────────────────┬───────────────────┘   │
│                   │                               │                       │
│                   ▼                               ▼                       │
│   ┌───────────────────────────────┐ ┌─────────────────────────────────┐   │
│   │   AI & REASONING LAYER        │ │   CAPABILITY ADAPTER LAYER      │   │
│   │ • Model Provider (Local/API)  │ │ • Workspace Adapter (Proto A)   │   │
│   │ • Model Router & Planner      │ │ • Takeover Adapter  (Proto B)   │   │
│   │ • Vision / OCR Reasoner       │ │ • Keyboard Adapter  (Proto C)   │   │
│   │ • Tool Selection & Parsing    │ │ • Observation Adap. (Proto D)   │   │
│   └───────────────────────────────┘ │ • Pointer Adapter   (Proto E)   │   │
│                                     └─────────────────┬───────────────┘   │
│                                                       │                   │
│                                                       ▼                   │
│   ┌───────────────────────────────────────────────────────────────────┐   │
│   │                WINDOWS 11 OPERATING SYSTEM SUBSYSTEM              │   │
│   │   User32 • GDI/DWM • UI Automation • LowLevelHooks • Win32 AppBar │   │
│   └───────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────────┘
```

### Core Invariants

1. **Zero Direct Injection Bypass**: No subsystem, model, or UI component may ever invoke native Win32 input injection APIs (`user32.SendInput`) directly. All pointer actions route through the single authoritative `NativeDispatchGateway` and `button_controller` / `pointer_controller` validated in Prototype E.
2. **Capability Decoupling via Adapters**: The production product code must never directly import prototype internals. Communication with validated prototype capabilities occurs strictly through abstract, versioned contracts defined in `orbit.contracts`.
3. **Fail-Closed Hard Lockout (`UNRESOLVED_LOCKED`)**: If any pointer sanitization fails or state becomes indeterminate, the runtime enters hard lockout, rejecting all subsequent actions fail-closed until explicit operator reset.
4. **Microsecond Human Takeover Preemption**: Low-level mouse and keyboard hooks continuously monitor physical user input. Any human intervention immediately fires a cooperative cancellation token, stopping AI actions in $<50\,\mu\text{s}$ and halting workers in $<5\,\text{ms}$.
5. **Separate Observable Evidence Layers**: The system never conflates `SendInput` API acceptance with target application UI success. Observation, Planning, Authorization, Dispatch, and Readback Verification remain strictly separated phases.

---

## 2. Layer-by-Layer Architectural Decomposition

### Layer 1: Frontend / Desktop Shell Layer

The frontend provides the user-facing control surface, docked desktop companion bar, and debugging interface.

* **Primary Roles**:
  * Task submission, conversational interaction, and parameter tuning.
  * Live visual feed of target window observation and spatial element overlays.
  * Hierarchical execution timeline (Step $\rightarrow$ Sub-action $\rightarrow$ Verification).
  * Explicit Human-in-the-Loop (HITL) action authorization dialogs for restricted actions.
  * Prominent Emergency Stop (E-STOP) button and Human Takeover status badge.
  * System health, memory footprint, and latency telemetry dashboard.
* **Recommended Technology**:
  * **Framework**: React 18 / TypeScript with TailwindCSS and Vite.
  * **Desktop Packaging**: Lightweight Windows WebView2 wrapper (via Tauri v2 or PySide6 QWebEngineView).
  * **Transport Client**: Robust WebSocket client with exponential backoff reconnection and binary frame parsing for visual stream rendering on an HTML5 `<canvas>`.
  * **Rationale**: React/TypeScript provides a responsive UI for streaming events, fast timeline rendering, and element bounding-box overlays without incurring high memory overhead.

---

### Layer 2: Gateway & Transport Layer

The Gateway handles client connections, session lifecycles, and event streaming.

* **Primary Roles**:
  * Manages bi-directional WebSocket connections on `ws://127.0.0.1:8765/ws/v1`.
  * Serves REST configuration and health check endpoints on `http://127.0.0.1:8765/api/v1`.
  * Binds strictly to `127.0.0.1` (loopback only) to prevent unauthorized local network access.
  * Multiplexes JSON-RPC commands and binary viewport frames over dedicated channels.
  * Applies token-bucket backpressure to prevent UI event queue flooding.
* **Recommended Technology**:
  * **Engine**: FastAPI 0.121 + Uvicorn 0.38 with `asyncio` native loop.
  * **Serialization**: `pydantic` v2 for JSON schemas; binary frame headers for zero-copy screen buffer transfer.

---

### Layer 3: ORBIT Core Runtime & Orchestration

The central deterministic runtime managing task lifecycles, re-entrant state transitions, and coordination.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        ORBIT CORE RUNTIME                              │
│                                                                        │
│   ┌──────────────────┐    ┌──────────────────┐    ┌────────────────┐   │
│   │   Task Manager   │───►│  Agent Executive │───►│ Plan Engine    │   │
│   │ (State Machine)  │    │  (Perception Loop│    │ (Step Tree)    │   │
│   └─────────┬────────┘    └────────┬─────────┘    └────────────────┘   │
│             │                      │                                   │
│             ▼                      ▼                                   │
│   ┌──────────────────┐    ┌──────────────────┐    ┌────────────────┐   │
│   │ Safety & Policy  │    │  Event Bus       │    │ Cancellation   │   │
│   │ Coordinator      │    │  (In-Process)    │    │ Manager (Tokens│   │
│   └──────────────────┘    └──────────────────┘    └────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

* **Core Components**:
  1. **Task Manager**: Enforces the top-level task lifecycle (`CREATED` $\rightarrow$ `RUNNING` $\rightarrow$ `PAUSED` $\rightarrow$ `COMPLETED` / `CANCELLED` / `FAILED`).
  2. **Agent Executive**: Executes the perception-planning-action loop:
     $$\text{Observe Desktop} \longrightarrow \text{Fuse Evidence} \longrightarrow \text{Plan Next Step} \longrightarrow \text{Authorize} \longrightarrow \text{Execute} \longrightarrow \text{Verify}$$
  3. **Safety & Policy Coordinator**: Evaluates proposed actions against system safety policies (e.g., destructive shortcut blocklist, sensitive target HWND protection).
  4. **Cancellation Manager**: Coordinates thread-safe `CancellationToken` hierarchies across active async tasks, worker threads, and native dispatch pipelines.
  5. **In-Process Async Event Bus**: Decoupled publish-subscribe bus routing structured domain events across runtime subsystems.

---

### Layer 4: AI Reasoning & Model Layer

The model abstraction layer decoupling high-level planning from specific model providers.

* **Architecture**:
  * **Model Router**: Routes requests dynamically based on task requirements:
    * *Fast Intent Router*: Low-latency lightweight LLM (e.g., local 3B/7B via ONNX Runtime / llama.cpp or fast cloud API).
    * *Multimodal Vision Reasoner*: Vision-Language Model (VLM) for interpreting dense UI screenshots and grounding natural language requests to UI element bounding boxes.
    * *Complex Workflow Planner*: High-capacity reasoning model for multi-step task decomposition and error recovery.
  * **Tool Execution Engine**: Translates high-level model tool calls (`click_button(id)`, `type_text(string)`, `scroll_view(delta)`) into strict typed capability requests.
  * **Structured JSON Extraction**: Enforces Pydantic schema validation on all model outputs with fail-safe retry on schema syntax violations.

---

### Layer 5: Capability Adapter Layer

The authoritative boundary isolating production ORBIT from the standalone prototype implementations.

```text
                        ┌──────────────────────────────┐
                        │   ORBIT Core Capabilities    │
                        │     (Abstract Contracts)     │
                        └──────────────┬───────────────┘
                                       │
     ┌──────────────────┬──────────────┼──────────────┬──────────────────┐
     ▼                  ▼              ▼              ▼                  ▼
┌──────────────┐ ┌──────────────┐ ┌──────────┐ ┌──────────────┐ ┌──────────────┐
│  Workspace   │ │   Takeover   │ │ Keyboard │ │ Observation  │ │   Pointer    │
│   Adapter    │ │   Adapter    │ │ Adapter  │ │   Adapter    │ │   Adapter    │
└──────┬───────┘ └──────┬───────┘ └────┬─────┘ └──────┬───────┘ └──────┬───────┘
       │                │              │              │                │
       ▼                ▼              ▼              ▼                ▼
[Prototype A]    [Prototype B]  [Prototype C]  [Prototype D]    [Prototype E]
(AppBar Win32)   (LowLevelHook) (SendInput KB) (Fusion Engine)  (SendInput Ptr)
```

Each adapter wraps a frozen/validated prototype, providing:
1. Standardized Async API conforming to `orbit.contracts`.
2. Automatic conversion between prototype data structures and unified domain types.
3. Thread boundaries isolating native Win32 message pumps from async event loops.
4. Comprehensive health monitoring and error containment.

---

## 3. Concurrency & Threading Architecture

To guarantee both UI responsiveness and sub-millisecond safety preemption, ORBIT employs a multi-threaded process topology:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                        MAIN ORBIT PROCESS                               │
│                                                                         │
│  [ Thread 1: AsyncIO Main Loop ]                                        │
│  ├── FastAPI / WebSocket Server                                         │
│  ├── ORBIT Core Runtime State Machine                                   │
│  ├── Agent Perception-Planning-Execution Orchestrator                   │
│  └── In-Process Async Event Bus                                         │
│                                                                         │
│  [ Thread 2: Human Takeover Hook Listener (Dedicated Win32 Pump) ]      │
│  ├── SetWindowsHookExW(WH_MOUSE_LL)                                     │
│  ├── SetWindowsHookExW(WH_KEYBOARD_LL)                                  │
│  └── Velocity / Displacement Takeover Detector (Sub-50µs detection)     │
│                                                                         │
│  [ Thread Pool 1: Background UI Automation / COM Workers ]              │
│  ├── STA/MTA COM Workers for Windows UIA / MSAA Tree Traversal          │
│  └── Circuit-Breaker Isolated Process Worker Pool                       │
│                                                                         │
│  [ Thread Pool 2: Heavy Vision / OCR Workers ]                          │
│  └── Windows Media OCR / Image Processing Operations                    │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │ Process Supervision
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              DETACHED WATCHDOG PROCESS (watchdog.py)                    │
│  • Monitors ORBIT Main PID                                              │
│  • Restores Desktop WorkArea (SPI_SETWORKAREA) on unclean termination   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Security & Privilege Boundaries

1. **User-Mode Non-Elevated Execution**: ORBIT executes as a standard non-elevated user-mode process.
2. **UIPI (User Interface Privilege Isolation) Boundary**: ORBIT will not attempt to control elevated (Administrator) windows without explicit operator elevation, preventing silent input drops.
3. **Loopback-Only Network Binding**: The Gateway strictly binds to `127.0.0.1` and authenticates WebSocket sessions via local per-session tokens.
4. **Action Authorization Policies**:
   * *Normal Actions* (Mouse move, left-click within target bounds, typing text): Auto-authorized if confidence is `CONFIRMED`.
   * *Sensitive Actions* (System shortcuts, file deletions, sensitive dialogs): Require explicit HITL authorization from the user interface.

---

## 5. Epistemic Safety & Verification Model

ORBIT distinguishes seven sequential layers of operational verification:

$$\text{L1: Target Validated} \longrightarrow \text{L2: Pre-Dispatch Re-Checked} \longrightarrow \text{L3: Gate Verified} \longrightarrow \text{L4: Packet Accepted (SendInput)}$$
$$\longrightarrow \text{L5: Cursor / Key Observed} \longrightarrow \text{L6: Message Processed} \longrightarrow \text{L7: Target State Verified (UIA/OCR)}$$

* $L_4$ proves only that User32 accepted the input packet into the OS input queue.
* $L_5$ proves point-in-time observation via `GetCursorPos` or keystroke readback.
* $L_7$ proves high-level application state change through post-action accessibility snapshot comparison.
* ORBIT never reports task success until $L_7$ is confirmed.
