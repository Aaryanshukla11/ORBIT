# ORBIT Product Integration Roadmap — Phase M0 through M5
**Document Version:** 1.0.0  
**Status:** APPROVED INTEGRATION ROADMAP  

---

## 1. Guiding Integration Principles

1. **Vertical Slices Over Monolithic Assembly**: Each milestone delivers a working, verifiable end-to-end capability slice.
2. **Zero Regression on Frozen Prototypes**: Prototypes A through D remain 100% frozen; Prototype E serves as the validated pointer engine.
3. **Empirical Gate Verification**: No milestone is declared complete without automated end-to-end test execution passing at 100%.
4. **Safety-First Integration**: Preemption, cancellation, and fail-closed hard lockout are integrated and tested before autonomous multi-step planning is enabled.

---

## 2. Milestone Breakdown & Delivery Plan

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                           INTEGRATION ROADMAP                           │
│                                                                         │
│  [M0: Foundation & Contracts] ──► [M1: Workspace & Observation Loop]    │
│                                                   │                     │
│                                                   ▼                     │
│  [M3: Safety & Human Takeover] ◄── [M2: Pointer & Keyboard Execution]   │
│                 │                                                       │
│                 ▼                                                       │
│  [M4: AI Reasoning & Router]  ──► [M5: Product Hardening & Release]     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### Milestone M0: Core Contracts, Gateway Foundation & Event Bus
* **Objective**: Establish the core product package structure, abstract capability contracts, FastAPI + WebSocket gateway, and in-process async event bus.
* **Deliverables**:
  * Root Python package layout `src/orbit/` with subpackages: `contracts`, `adapters`, `runtime`, `gateway`, `safety`.
  * `orbit.contracts`: Pydantic / Protocol definitions for all 5 capabilities.
  * `orbit.gateway`: FastAPI server, WebSocket endpoint (`/ws/v1`), session manager, and JSON-RPC message dispatcher.
  * `orbit.runtime.event_bus`: Async in-process event bus with typed publish-subscribe channels.
  * Initial test harness verifying loopback WebSocket connection, message envelope validation, and event routing.
* **Acceptance Criteria**:
  * Automated tests verify WebSocket connect, PING/PONG, session initialization, and typed event dispatching.
  * 0 lines modified in `prototypes/`.

---

### Milestone M1: Workspace Docking & Screen Observation Pipeline
* **Objective**: Connect the Desktop Shell / Workspace Manager (Prototype A) and Multi-Source Observation Engine (Prototype D) to the Gateway.
* **Deliverables**:
  * `orbit.adapters.workspace`: Adapter wrapping `appbar_native.py` and watchdog supervision.
  * `orbit.adapters.observation`: Adapter wrapping `accessibility_coordinator.py`, `fusion_engine.py`, and `capture_engine.py`.
  * Frontend prototype/shell demonstrating docked AppBar window on Windows 11 with live visual frame stream and accessibility element overlay.
* **Acceptance Criteria**:
  * Docking reserves work area without visual artifacts; watchdog recovers work area on simulated crash.
  * Observation captures fused snapshot and streams JPEG/WebP frames over WebSocket in $<150\,\text{ms}$.

---

### Milestone M2: Safe Pointer & Keyboard Execution Pipeline
* **Objective**: Connect Pointer Movement/Click (Prototype E) and Keyboard Typing/Shortcuts (Prototype C) to the Task Engine.
* **Deliverables**:
  * `orbit.adapters.pointer`: Adapter wrapping `pointer_controller.py`, `button_controller.py`, and `pointer_state_manager.py`.
  * `orbit.adapters.keyboard`: Adapter wrapping `keyboard_controller.py`, `shortcut_engine.py`, and `clipboard_preserver.py`.
  * `orbit.runtime.action_executor`: Sequential action dispatcher enforcing pre-dispatch validation, ABI gating, and post-action readback.
* **Acceptance Criteria**:
  * Executes targeted clicks on observed UI elements with $\pm 1\,\text{px}$ accuracy.
  * Executes Unicode text typing and safe shortcuts with focus-loss protection.
  * Fail-closed lockout and emergency sanitization verified under simulated failure injection.

---

### Milestone M3: Human Takeover & Safety Policy Coordinator
* **Objective**: Integrate low-level hook monitoring (Prototype B), real-time preemption, and action approval policies.
* **Deliverables**:
  * `orbit.adapters.takeover`: Adapter managing dedicated background hook thread and trajectory corridor monitoring.
  * `orbit.safety.policy_coordinator`: Action approval rules engine (auto-approved vs HITL confirmation).
  * Emergency Stop (E-Stop) handler immediately interrupting active dispatches and cancelling tokens.
* **Acceptance Criteria**:
  * Physical human mouse movement during AI execution halts action within $<5\,\text{ms}$ and transitions system state to `PAUSED_BY_USER`.
  * Restricted shortcuts (e.g. `Alt+F4`, `Win+L`) trigger `ACTION_APPROVAL_REQUIRED` prompt in UI.

---

### Milestone M4: AI Reasoning, Model Router & Autonomous Planning
* **Objective**: Connect local and remote AI models, multimodal perception reasoning, and dynamic multi-step task planning.
* **Deliverables**:
  * `orbit.ai.model_provider`: Pluggable interfaces for local models (ONNX/llama.cpp) and cloud APIs (OpenAI/Anthropic/Gemini).
  * `orbit.ai.planner`: Multi-step workflow planner with structured JSON schema output parsing.
  * `orbit.ai.vision_reasoner`: Multimodal visual grounding translating natural language requests to UI element bounding boxes.
  * Autonomous task recovery loop with verification feedback.
* **Acceptance Criteria**:
  * End-to-end autonomous execution of multi-step desktop tasks (e.g., "Create a text file, write notes, and save in Documents").
  * Step verification verifies UI change before proceeding to subsequent step.

---

### Milestone M5: Product Hardening, Packaging & Autonomous Workflows
* **Objective**: Production packaging, installer configuration, performance optimization, and comprehensive documentation.
* **Deliverables**:
  * Production Desktop Shell build (Tauri/WebView2) with refined glassmorphism UI and system tray integration.
  * Single-command desktop launcher / Windows installer (`.msi` / `.exe`).
  * End-to-end stress testing across multi-monitor, high-DPI (150%, 200%), and game/fullscreen environments.
* **Acceptance Criteria**:
  * 100% automated regression passing across all subsystems.
  * Zero memory leaks during 24-hour continuous standby.
