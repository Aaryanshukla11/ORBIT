# ORBIT — Milestone M1.9 Step 5: WebSocket Model Manager & Real-Time Backend Control API Report

## 1. Executive Summary & Implementation Status

Milestone M1.9 Step 5 is **100% COMPLETE & VERIFIED**.

The ORBIT Gateway now exposes a clean, strongly typed, and secure real-time WebSocket control API for the AI Model Management subsystem (`ModelSessionManager` & `ModelManager`). Connected frontend clients can query, control, activate, switch, probe health, discover, and monitor AI models in real time with authoritative backend state synchronization and zero risk of secret leakage or unauthorized runtime execution.

---

## 2. WebSocket Commands Implemented

All 7 model control commands have been implemented, strictly validated through Pydantic models in `protocol.py`, and dispatched through `WebSocketManager` with structured error isolation:

| Command Type | Inbound Payload Model | Description & Behavioral Guarantees |
| :--- | :--- | :--- |
| `MODEL_LIST` | `ModelListPayload` | Returns registered and discovered models with safe metadata (`model_id`, `display_name`, `provider`, `runtime_kind`, `availability`, `installed`, `configured`, `capabilities`, `context_window`, `parameter_size`, `family`). Supports filtering by `provider`, `capability`, or `include_all`. Zero secrets exposed. |
| `MODEL_STATUS` | `ModelStatusPayload` | Returns overall model subsystem health, active model context snapshot, runtime status (`ACTIVE`, `STOPPED`, `FAILED`), runtime health assessment, available model count, active monotonic generation counter, and busy flag. |
| `MODEL_ACTIVE` | `ModelActivePayload` | Returns the current immutable `ActiveModelContext`. Returns honest `NO_ACTIVE_MODEL` state (`is_active: false`, `active_model: null`, `generation: 0`) when no model is active; never fabricates a fake active model. |
| `MODEL_DISCOVER` | `ModelDiscoverPayload` | Triggers a non-destructive discovery scan across provider runtimes, cloud endpoints, and local files. Discovered descriptors are registered into the registry and broadcasted via `MODEL_DISCOVERED`. Never automatically downloads, installs, or activates models. |
| `MODEL_ACTIVATE` | `ModelActivatePayload` | Activates target model via `ModelSessionManager.activate_model()`. Validates model presence and capability constraints, initializes lazy weights/warmup, probes health, updates active context, and increments monotonic generation counter. |
| `MODEL_SWITCH` | `ModelSwitchPayload` | Safely switches between models via `ModelSessionManager.switch_model()` with atomic rollback. Enforces safety policies (`REJECT_DURING_ACTIVE_TASK`, `CANCEL_AND_SWITCH`). Rejects switches during active tasks with honest `ACTIVE_TASK_CONFLICT`. |
| `MODEL_HEALTH` | `ModelHealthPayload` | Probes health of active runtime or registered target model. Returns categorized status (`HEALTHY`, `DEGRADED`, `UNAVAILABLE`, `FAILED`, `UNKNOWN`) with ping latency and diagnostic message. Never claims a model is healthy merely because it is registered. |

---

## 3. Real-Time Model Event Types

The WebSocket Gateway forwards all model events from the internal `EventBus` to connected clients:

| Event Type | Direction | Payload Contract | Description |
| :--- | :--- | :--- | :--- |
| `MODEL_LIST_RESPONSE` | Gateway $\to$ Client | `{"models": [...], "total_count": int, "active_model_id": Optional[str]}` | Response to `MODEL_LIST` query. |
| `MODEL_STATUS_RESPONSE` | Gateway $\to$ Client | `{"active_model": dict, "is_active": bool, "runtime_status": str, "runtime_health": dict, ...}` | Response to `MODEL_STATUS` query. |
| `MODEL_ACTIVE_RESPONSE` | Gateway $\to$ Client | `{"is_active": bool, "generation": int, "active_model": Optional[dict]}` | Response to `MODEL_ACTIVE` query. |
| `MODEL_DISCOVER_RESPONSE` | Gateway $\to$ Client | `{"discovered_count": int, "models": [...], ...}` | Response to `MODEL_DISCOVER` query. |
| `MODEL_HEALTH_RESPONSE` | Gateway $\to$ Client | `{"model_id": str, "status": str, "is_healthy": bool, "latency_ms": float, ...}` | Response to `MODEL_HEALTH` query. |
| `MODEL_DISCOVERED` | Broadcast | `{"model_id": str, "provider": str, "display_name": str, "capabilities": [...]}` | Emitted when a new model is discovered during inventory refresh. |
| `MODEL_ACTIVATING` | Broadcast | `{"model_id": str, "provider": str, "generation": int, "status": "ACTIVATING"}` | Emitted when model runtime initialization begins. |
| `MODEL_ACTIVATED` | Broadcast | `{"model_id": str, "status": "ACTIVE", "generation": int, "duration_ms": float}` | Emitted when a model is successfully activated. |
| `MODEL_SWITCH_REQUESTED` | Broadcast | `{"previous_model_id": str, "target_model_id": str, "generation": int}` | Emitted when model switch workflow starts. |
| `MODEL_SWITCHED` | Broadcast | `{"previous_model_id": str, "target_model_id": str, "generation": int, "switched": true}` | Emitted upon successful atomic model switch. |
| `MODEL_SWITCH_FAILED` | Broadcast | `{"previous_model_id": str, "target_model_id": str, "failure_reason": str, ...}` | Emitted when a switch attempt fails and rolls back. |
| `MODEL_HEALTH_CHANGED` | Broadcast | `{"model_id": str, "provider": str, "status": str, "latency_ms": float, ...}` | Emitted when runtime health diagnostic status changes. |
| `MODEL_RUNTIME_FAILED` | Broadcast | `{"model_id": str, "provider": str, "status": "FAILED", "reason": str}` | Emitted when active runtime encounters a crash or fatal error. |
| `MODEL_SHUTDOWN` | Broadcast | `{"model_id": str, "provider": str, "status": "STOPPED"}` | Emitted when active model runtime is gracefully deallocated. |

---

## 4. Backend Architecture & Event Flow

```text
  ┌────────────────────────────────────────────────────────┐
  │                 WebSocket Client (Frontend)            │
  └─────────────────────────┬──────────────────────────────┘
                            │ JSON WebSocket Message
                            ▼
  ┌────────────────────────────────────────────────────────┐
  │                 FastAPI Gateway (/ws)                  │
  │                  (orbit/gateway/app.py)                │
  └─────────────────────────┬──────────────────────────────┘
                            │
                            ▼
  ┌────────────────────────────────────────────────────────┐
  │                   WebSocketManager                     │
  │             (orbit/gateway/websocket_manager.py)       │
  │  - Protocol Deserialization & Pydantic Validation     │
  │  - Command Dispatch with Structured Error Isolation    │
  └─────────────┬────────────────────────────▲─────────────┘
                │                            │
                │ Invokes Manager            │ EventBus Listener
                ▼                            │
  ┌───────────────────────────┐    ┌─────────┴─────────────┐
  │    ModelSessionManager    │    │       EventBus        │
  │  - Active Model Context   │───▶│  - MODEL_ACTIVATED    │
  │  - Atomic Safe Switching  │    │  - MODEL_SWITCHED     │
  │  - Task Conflict Guards   │    │  - MODEL_HEALTH       │
  └─────────────┬─────────────┘    └───────────────────────┘
                │
                ▼
  ┌───────────────────────────┐
  │    BaseModelRuntime       │
  │  - Local (Ollama)         │
  │  - Remote (OpenAI/Cloud)  │
  │  - Mock Runtime Adapter   │
  └───────────────────────────┘
```

---

## 5. Multi-Client Synchronization & Authoritative Backend State

1. **Single Source of Truth**: Active model state, active generation counter, and descriptor registry are managed exclusively by `ModelSessionManager`. No connected client maintains an independent local state.
2. **Real-Time Broadcast**: When Client A switches a model, `ModelSessionManager` commits the state change and emits `MODEL_SWITCHED` onto the `EventBus`. The `WebSocketManager` automatically broadcasts the event to Client A, Client B, and all other active WebSocket connections.
3. **Late-Joining Synchronization**: When Client C connects fresh to `/ws`, it receives an initial `RUNTIME_STATUS` and can immediately issue `MODEL_STATUS` or `MODEL_ACTIVE` to receive the exact authoritative active model and generation counter.

---

## 6. Security Restrictions & Boundary Protections

1. **Zero Secret Leakage**: API keys, Bearer tokens, passwords, authorization headers, and environment secrets are excluded by contract and never serialized into any WebSocket payload or event.
2. **No Arbitrary Execution**: Inbound messages are strictly constrained to pre-declared Pydantic schema envelopes. Clients cannot pass arbitrary shell commands, raw provider commands, or unrestricted runtime invocations.
3. **Safe Discovery Invariant**: Model discovery scans inspect endpoints and descriptors; they do NOT automatically trigger weight downloads or model execution.
4. **Autonomous Task Protection**: If an autonomous task is running and a switch is requested with `REJECT_DURING_ACTIVE_TASK`, the backend rejects the switch immediately with `ACTIVE_TASK_CONFLICT`.

---

## 7. Exact Tests Added & Results

### Unit Tests
* File: `tests/unit/test_model_websocket_protocol.py`
* Tests: 12 tests
* Status: **12/12 PASSED (0.36s)**
  - `test_parse_valid_model_list_command` $\to$ PASSED
  - `test_parse_valid_model_status_command` $\to$ PASSED
  - `test_parse_valid_model_active_command` $\to$ PASSED
  - `test_parse_valid_model_discover_command` $\to$ PASSED
  - `test_parse_valid_model_activate_command` $\to$ PASSED
  - `test_parse_model_activate_missing_model_id` $\to$ PASSED
  - `test_parse_valid_model_switch_command` $\to$ PASSED
  - `test_parse_model_switch_missing_model_id` $\to$ PASSED
  - `test_parse_valid_model_health_command` $\to$ PASSED
  - `test_serialize_model_outbound_events` $\to$ PASSED
  - `test_serialize_model_switch_event` $\to$ PASSED
  - `test_serialize_model_error_event` $\to$ PASSED

### Gateway Integration Tests
* File: `tests/integration/test_model_websocket_gateway.py`
* Tests: 10 tests
* Status: **10/10 PASSED (34.18s)**
  - `test_model_list_returns_safe_metadata` $\to$ PASSED (Test 1)
  - `test_model_active_returns_honest_state` $\to$ PASSED (Test 2)
  - `test_model_activate_routes_through_session_manager` $\to$ PASSED (Test 3)
  - `test_successful_model_switch` $\to$ PASSED (Test 4)
  - `test_failed_switch_returns_error_and_preserves_old_model` $\to$ PASSED (Test 5)
  - `test_switch_during_active_task_returns_active_task_conflict` $\to$ PASSED (Test 6)
  - `test_secrets_never_appear_in_any_response` $\to$ PASSED (Test 8)
  - `test_invalid_websocket_messages_fail_safely` $\to$ PASSED (Test 9)
  - `test_unavailable_models_cannot_be_falsely_activated` $\to$ PASSED (Test 10)
  - `test_model_health_command` $\to$ PASSED

### Event & Synchronization Integration Tests
* File: `tests/integration/test_model_websocket_events.py`
* Tests: 4 tests
* Status: **4/4 PASSED (5.80s)**
  - `test_multiple_clients_receive_same_model_event` $\to$ PASSED (Test 7)
  - `test_connection_state_synchronization_late_joining_client` $\to$ PASSED
  - `test_realtime_model_discovery_broadcast` $\to$ PASSED
  - `test_model_shutdown_broadcasts_events` $\to$ PASSED

---

## 8. Broader Tests Executed

To verify that the changes in `protocol.py`, `websocket_manager.py`, and `app.py` did not affect existing gateway capabilities:
* Command: `python -m pytest tests/unit/test_protocol.py tests/integration/test_websocket_lifecycle.py tests/integration/test_pointer_gateway_flow.py tests/integration/test_keyboard_gateway_flow.py tests/integration/test_gateway_capability_status.py -v`
* Status: **15/15 PASSED (16.86s)**

---

## 9. Known Limitations

1. **Frontend UI Pending**: This milestone focused exclusively on the backend WebSocket control layer. The frontend UI remains to be built in subsequent milestones.
2. **Streaming Token Generation over WebSocket**: Real-time token streaming during active model inference will be hooked up to interactive chat endpoints in milestone M2.0.

---

## 10. Prototype Boundary Verification

* `prototypes/` directory verified: **100% frozen, 0 modified files, 0 untracked files**.

---

## 11. Completion Verdict

**MILESTONE M1.9 STEP 5 IS COMPLETE, VERIFIED, AND READY FOR SYSTEM INTEGRATION.**
