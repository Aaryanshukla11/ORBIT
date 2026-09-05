# ORBIT Client-Gateway WebSocket Protocol Specification v1.0
**Protocol Version:** 1.0.0  
**Transport:** WebSocket (`ws://127.0.0.1:8765/ws/v1`)  
**Framing:** JSON-RPC 2.0 Extended Envelopes + Optional Binary Frames for Viewport Buffers  
**Status:** APPROVED PROTOCOL SPECIFICATION  

---

## 1. Protocol Architecture & Connection Lifecycle

The ORBIT WebSocket protocol facilitates real-time, low-latency, full-duplex communication between the Desktop Shell / Frontend UI and the ORBIT Core Gateway.

```text
CLIENT (Desktop Shell / Web UI)                       SERVER (ORBIT Gateway)
               │                                                 │
               │────── 1. Connect (ws://127.0.0.1:8765/ws/v1) ──►│
               │◄───── 2. SESSION_INITIALIZED (Handshake) ───────│
               │                                                 │
               │────── 3. SUBMIT_TASK (Task Spec) ──────────────►│
               │◄───── 4. TASK_STATUS_UPDATED (CREATED) ─────────│
               │◄───── 5. OBSERVATION_FRAME (Metadata) ──────────│
               │◄───── 6. Binary Viewport Buffer (JPEG/WebP) ────│
               │◄───── 7. PLAN_GENERATED (Step Sequence) ────────│
               │                                                 │
               │   [ Optional Action Authorization Loop ]        │
               │◄───── 8. ACTION_APPROVAL_REQUIRED ──────────────│
               │────── 9. APPROVE_ACTION / REJECT_ACTION ───────►│
               │                                                 │
               │   [ Execution & Verification Streaming ]        │
               │◄───── 10. ACTION_DISPATCHED ────────────────────│
               │◄───── 11. ACTION_VERIFIED ──────────────────────│
               │◄───── 12. TASK_STATUS_UPDATED (COMPLETED) ──────│
               │                                                 │
               │   [ Emergency / Human Preemption ]              │
               │◄───── 13. TAKEOVER_ALERT (Physical Input) ──────│
               │────── 14. CANCEL_TASK (Emergency Stop) ────────►│
               │                                                 │
               │────── 15. PING / PONG (Heartbeat) ──────────────│
```

### Connection Rules
1. **Loopback Binding**: Server listens strictly on `127.0.0.1`.
2. **Session Authentication**: During connection handshake, client passes session token via query parameter `?token=<session_token>`.
3. **Heartbeat / Keepalive**: Client transmits `PING` every 5,000ms; Server replies with `PONG`. If no heartbeat is received within 15,000ms, connection is terminated and fail-safe safety policies trigger.
4. **Disconnection Safety Policy**: If the UI disconnects while ORBIT has an action in flight:
   * Immediate synthetic pointer/keyboard sanitization is emitted (all synthetic pressed keys/buttons released).
   * Active task transitions to `TASK_PAUSED` awaiting client reconnect.

---

## 2. Standard Message Envelope Schema

Every JSON message transmitted over the WebSocket protocol conforms to the unified message envelope:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "OrbitMessageEnvelope",
  "type": "object",
  "required": [
    "message_id",
    "message_type",
    "version",
    "timestamp_ns",
    "session_id",
    "payload"
  ],
  "properties": {
    "message_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique identifier for this specific message"
    },
    "message_type": {
      "type": "string",
      "description": "Discriminator identifying the message schema"
    },
    "version": {
      "type": "string",
      "enum": ["1.0"]
    },
    "timestamp_ns": {
      "type": "integer",
      "description": "High-resolution monotonic or UTC nanosecond timestamp"
    },
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active client session identifier"
    },
    "task_id": {
      "type": ["string", "null"],
      "format": "uuid",
      "description": "Associated task identifier if executing within a task context"
    },
    "correlation_id": {
      "type": ["string", "null"],
      "format": "uuid",
      "description": "Pairs RPC requests with their asynchronous replies"
    },
    "causation_id": {
      "type": ["string", "null"],
      "format": "uuid",
      "description": "Identifier of the prior message or event that caused this event"
    },
    "payload": {
      "type": "object",
      "description": "Typed message-specific payload"
    }
  }
}
```

---

## 3. Client $\rightarrow$ Server Message Catalog

### 3.1 `SUBMIT_TASK`
* **Purpose**: Submits a new natural language task or structured goal to the agent.
* **Payload**:
  ```json
  {
    "task_prompt": "Open Notepad and type 'Hello World'",
    "target_app_filter": "notepad.exe",
    "safety_mode": "STANDARD",
    "max_steps": 25,
    "require_step_approval": false,
    "parameters": {}
  }
  ```
* **Expected Response**: `TASK_STATUS_UPDATED` (`status: "CREATED"`).

### 3.2 `CANCEL_TASK`
* **Purpose**: Requests immediate, cooperative cancellation of the active task.
* **Payload**:
  ```json
  {
    "task_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "reason": "USER_EMERGENCY_STOP",
    "force_immediate_release": true
  }
  ```
* **Expected Response**: `TASK_STATUS_UPDATED` (`status: "CANCELLED"`).

### 3.3 `APPROVE_ACTION`
* **Purpose**: Grants explicit user authorization for a sensitive or pending action.
* **Payload**:
  ```json
  {
    "action_id": "a4f8b2c1-6e3d-4c8a-9f12-0e5d4a3b2c1f",
    "approved": true,
    "operator_notes": "Approved by user in UI"
  }
  ```
* **Expected Response**: `ACTION_DISPATCHED`.

### 3.4 `REJECT_ACTION`
* **Purpose**: Denies authorization for a proposed action, directing the planner to re-plan.
* **Payload**:
  ```json
  {
    "action_id": "a4f8b2c1-6e3d-4c8a-9f12-0e5d4a3b2c1f",
    "rejection_reason": "INCORRECT_TARGET_ELEMENT",
    "user_feedback": "Please click the Cancel button instead"
  }
  ```
* **Expected Response**: `PLAN_UPDATED`.

### 3.5 `REQUEST_TAKEOVER` / `RELEASE_TAKEOVER`
* **Purpose**: Manually declares that the human user is taking over the mouse/keyboard or returning control to ORBIT.
* **Payload**:
  ```json
  {
    "takeover_source": "UI_BUTTON_CLICK",
    "reason": "Manual operator adjustment"
  }
  ```
* **Expected Response**: `TAKEOVER_ALERT` with updated `takeover_state`.

### 3.6 `CONFIGURE_WORKSPACE`
* **Purpose**: Commands the AppBar manager to dock, undock, or resize the desktop companion bar.
* **Payload**:
  ```json
  {
    "dock_edge": "ABE_RIGHT",
    "desired_width_px": 440,
    "monitor_index": 0,
    "auto_hide": false
  }
  ```
* **Expected Response**: `RUNTIME_STATUS`.

---

## 4. Server $\rightarrow$ Client Message Catalog

### 4.1 `SESSION_INITIALIZED`
* **Purpose**: Confirms successful connection, capability registration, and initial system state.
* **Payload**:
  ```json
  {
    "runtime_version": "1.0.0",
    "host_platform": "Windows 11 AMD64 (Build 26200)",
    "capabilities": {
      "workspace_docking": true,
      "human_takeover_detection": true,
      "keyboard_injection": true,
      "screen_observation": true,
      "pointer_injection": true
    },
    "virtual_desktop": {
      "origin_x": 0,
      "origin_y": 0,
      "width": 2880,
      "height": 1800,
      "monitor_count": 1
    },
    "current_runtime_state": "IDLE_READY"
  }
  ```

### 4.2 `TASK_STATUS_UPDATED`
* **Purpose**: Broadcasts changes in top-level task state.
* **Payload**:
  ```json
  {
    "task_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "previous_status": "OBSERVING",
    "current_status": "EXECUTING",
    "step_index": 2,
    "total_steps": 5,
    "status_message": "Executing click on 'File' menu item",
    "error_details": null
  }
  ```

### 4.3 `OBSERVATION_FRAME`
* **Purpose**: Delivers structured spatial observation data (and announces accompanying binary frame).
* **Payload**:
  ```json
  {
    "observation_id": "obs-0012",
    "generation_id": 4,
    "timestamp_ns": 1725555600000000000,
    "foreground_window": {
      "hwnd": 131244,
      "title": "Untitled - Notepad",
      "process_name": "Notepad.exe",
      "pid": 12840,
      "bounds": [100, 100, 1100, 900]
    },
    "detected_elements": [
      {
        "element_id": "elem_01",
        "name": "File",
        "control_type": "MenuItem",
        "bounds": [110, 130, 150, 155],
        "confidence": "CONFIRMED",
        "sources": ["UI_AUTOMATION", "OCR"]
      }
    ],
    "has_binary_frame": true,
    "binary_frame_format": "IMAGE_JPEG",
    "binary_frame_size_bytes": 142850
  }
  ```

### 4.4 `PLAN_GENERATED`
* **Purpose**: Streams the multi-step execution plan synthesized by the reasoning engine.
* **Payload**:
  ```json
  {
    "plan_id": "plan-088",
    "goal": "Open Notepad and type 'Hello World'",
    "steps": [
      {
        "step_index": 1,
        "action_type": "POINTER_CLICK",
        "target_description": "File menu",
        "target_element_id": "elem_01",
        "status": "COMPLETED"
      },
      {
        "step_index": 2,
        "action_type": "KEYBOARD_TYPE",
        "target_description": "Text area",
        "text_content": "Hello World",
        "status": "PENDING"
      }
    ]
  }
  ```

### 4.5 `ACTION_APPROVAL_REQUIRED`
* **Purpose**: Prompts the user to authorize or reject a sensitive or high-risk action.
* **Payload**:
  ```json
  {
    "action_id": "a4f8b2c1-6e3d-4c8a-9f12-0e5d4a3b2c1f",
    "action_type": "KEYBOARD_SHORTCUT",
    "shortcut_chord": ["ALT", "F4"],
    "risk_level": "RESTRICTED",
    "warning_message": "Action will close the active window. Confirm to proceed.",
    "timeout_ms": 30000
  }
  ```

### 4.6 `TAKEOVER_ALERT`
* **Purpose**: High-priority alert notifying the UI that physical human input was detected and AI execution has been preempted.
* **Payload**:
  ```json
  {
    "takeover_state": "PAUSED_BY_USER",
    "trigger_event": "MOUSE_VELOCITY_DISPLACEMENT_EXCEEDED",
    "detection_latency_us": 38.5,
    "active_action_cancelled": true,
    "message": "Physical mouse motion detected; AI input execution paused immediately."
  }
  ```

### 4.7 `HARD_LOCKOUT_TRIGGERED`
* **Purpose**: Alerts the UI that the pointer state machine entered `UNRESOLVED_LOCKED` and requires manual operator recovery.
* **Payload**:
  ```json
  {
    "lockout_reason": "SANITIZATION_DISPATCH_FAILED",
    "message": "Pointer sanitization failed. State machine locked fail-closed.",
    "recovery_procedure": "Click 'Manual Recovery' or execute recover_lockout_after_external_verification('CONFIRM_OPERATOR_MANUAL_RESET')."
  }
  ```

---

## 5. Binary Frame Transport Specification

For zero-copy desktop viewport streaming, binary frames are transmitted directly after an `OBSERVATION_FRAME` JSON message.

### Binary Frame Layout
```text
┌───────────────────────────┬───────────────────────────┬─────────────────────────────────┐
│ Magic Header (4 bytes)    │ Frame Sequence (8 bytes)  │ Raw Compressed Image Data       │
│ 0x4F, 0x52, 0x42, 0x54    │ uint64_t Big-Endian       │ (JPEG / WebP binary stream)     │
│ ("ORBT")                  │                           │                                 │
└───────────────────────────┴───────────────────────────┴─────────────────────────────────┘
```
Client decodes the binary buffer directly into an `ImageBitmap` or WebGL texture for GPU-accelerated canvas rendering.
