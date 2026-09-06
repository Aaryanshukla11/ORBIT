"""Unit tests for Model WebSocket protocol parsing, validation, and serialization (Milestone M1.9 Step 5)."""

import json
from datetime import datetime, timezone
import pytest

from orbit.contracts.commands import (
    CommandType,
    ModelActivatePayload,
    ModelActivePayload,
    ModelDiscoverPayload,
    ModelHealthPayload,
    ModelListPayload,
    ModelStatusPayload,
    ModelSwitchPayload,
)
from orbit.contracts.events import (
    ErrorEventPayload,
    EventType,
    ModelEventPayload,
    ModelHealthEventPayload,
    ModelSwitchEventPayload,
    RuntimeEvent,
)
from orbit.gateway.protocol import (
    ProtocolError,
    parse_inbound_message,
    serialize_outbound_event,
)


def test_parse_valid_model_list_command():
    raw_msg = json.dumps({
        "command_id": "cmd_list_01",
        "command_type": "MODEL_LIST",
        "session_id": "sess_001",
        "payload": {
            "provider": "OLLAMA",
            "capability": "TEXT_GENERATION",
            "include_all": True,
        },
    })
    base_cmd, payload = parse_inbound_message(raw_msg)
    assert base_cmd.command_id == "cmd_list_01"
    assert base_cmd.command_type == CommandType.MODEL_LIST
    assert isinstance(payload, ModelListPayload)
    assert payload.provider == "OLLAMA"
    assert payload.capability == "TEXT_GENERATION"
    assert payload.include_all is True


def test_parse_valid_model_status_command():
    raw_msg = json.dumps({
        "command_id": "cmd_status_01",
        "command_type": "MODEL_STATUS",
        "session_id": "sess_001",
        "payload": {},
    })
    base_cmd, payload = parse_inbound_message(raw_msg)
    assert base_cmd.command_type == CommandType.MODEL_STATUS
    assert isinstance(payload, ModelStatusPayload)


def test_parse_valid_model_active_command():
    raw_msg = json.dumps({
        "command_id": "cmd_active_01",
        "command_type": "MODEL_ACTIVE",
        "session_id": "sess_001",
        "payload": {},
    })
    base_cmd, payload = parse_inbound_message(raw_msg)
    assert base_cmd.command_type == CommandType.MODEL_ACTIVE
    assert isinstance(payload, ModelActivePayload)


def test_parse_valid_model_discover_command():
    raw_msg = json.dumps({
        "command_id": "cmd_disc_01",
        "command_type": "MODEL_DISCOVER",
        "session_id": "sess_001",
        "payload": {
            "include_runtimes": True,
            "include_cloud": False,
            "include_files": True,
        },
    })
    base_cmd, payload = parse_inbound_message(raw_msg)
    assert base_cmd.command_type == CommandType.MODEL_DISCOVER
    assert isinstance(payload, ModelDiscoverPayload)
    assert payload.include_runtimes is True
    assert payload.include_cloud is False
    assert payload.include_files is True


def test_parse_valid_model_activate_command():
    raw_msg = json.dumps({
        "command_id": "cmd_act_01",
        "command_type": "MODEL_ACTIVATE",
        "session_id": "sess_001",
        "payload": {
            "model_id": "ollama:qwen2.5:latest",
            "timeout_seconds": 15.0,
            "preload_weights": True,
            "required_capabilities": ["TEXT_GENERATION", "CHAT"],
            "policy": "REJECT_DURING_ACTIVE_TASK",
        },
    })
    base_cmd, payload = parse_inbound_message(raw_msg)
    assert base_cmd.command_type == CommandType.MODEL_ACTIVATE
    assert isinstance(payload, ModelActivatePayload)
    assert payload.model_id == "ollama:qwen2.5:latest"
    assert payload.timeout_seconds == 15.0
    assert payload.required_capabilities == ["TEXT_GENERATION", "CHAT"]
    assert payload.policy == "REJECT_DURING_ACTIVE_TASK"


def test_parse_model_activate_missing_model_id():
    raw_msg = json.dumps({
        "command_id": "cmd_act_fail",
        "command_type": "MODEL_ACTIVATE",
        "session_id": "sess_001",
        "payload": {},
    })
    with pytest.raises(ProtocolError) as exc_info:
        parse_inbound_message(raw_msg)
    assert exc_info.value.code == "INVALID_PAYLOAD"


def test_parse_valid_model_switch_command():
    raw_msg = json.dumps({
        "command_id": "cmd_sw_01",
        "command_type": "MODEL_SWITCH",
        "session_id": "sess_001",
        "payload": {
            "model_id": "ollama:llama3.2:latest",
            "policy": "CANCEL_AND_SWITCH",
            "timeout_seconds": 45.0,
        },
    })
    base_cmd, payload = parse_inbound_message(raw_msg)
    assert base_cmd.command_type == CommandType.MODEL_SWITCH
    assert isinstance(payload, ModelSwitchPayload)
    assert payload.model_id == "ollama:llama3.2:latest"
    assert payload.policy == "CANCEL_AND_SWITCH"
    assert payload.timeout_seconds == 45.0


def test_parse_model_switch_missing_model_id():
    raw_msg = json.dumps({
        "command_id": "cmd_sw_fail",
        "command_type": "MODEL_SWITCH",
        "session_id": "sess_001",
        "payload": {
            "policy": "FORCE_IMMEDIATE",
        },
    })
    with pytest.raises(ProtocolError) as exc_info:
        parse_inbound_message(raw_msg)
    assert exc_info.value.code == "INVALID_PAYLOAD"


def test_parse_valid_model_health_command():
    raw_msg = json.dumps({
        "command_id": "cmd_hlth_01",
        "command_type": "MODEL_HEALTH",
        "session_id": "sess_001",
        "payload": {
            "model_id": "ollama:qwen2.5:latest",
        },
    })
    base_cmd, payload = parse_inbound_message(raw_msg)
    assert base_cmd.command_type == CommandType.MODEL_HEALTH
    assert isinstance(payload, ModelHealthPayload)
    assert payload.model_id == "ollama:qwen2.5:latest"


def test_serialize_model_outbound_events():
    event = RuntimeEvent(
        event_id="evt_mod_01",
        event_type=EventType.MODEL_ACTIVATED,
        event_seq=1,
        session_id="sess_001",
        correlation_id="cmd_act_01",
        payload={
            "model_id": "ollama:qwen2.5:latest",
            "status": "ACTIVE",
            "generation": 1,
            "duration_ms": 12.5,
        },
    )
    serialized = serialize_outbound_event(event)
    data = json.loads(serialized)
    assert data["event_type"] == "MODEL_ACTIVATED"
    assert data["correlation_id"] == "cmd_act_01"
    assert data["payload"]["model_id"] == "ollama:qwen2.5:latest"
    assert data["payload"]["generation"] == 1


def test_serialize_model_switch_event():
    event = RuntimeEvent(
        event_id="evt_sw_01",
        event_type=EventType.MODEL_SWITCHED,
        event_seq=2,
        session_id="broadcast",
        payload=ModelSwitchEventPayload(
            previous_model_id="ollama:qwen2.5:latest",
            target_model_id="ollama:llama3.2:latest",
            generation=2,
            is_successful=True,
            duration_ms=45.2,
        ).model_dump(),
    )
    serialized = serialize_outbound_event(event)
    data = json.loads(serialized)
    assert data["event_type"] == "MODEL_SWITCHED"
    assert data["payload"]["previous_model_id"] == "ollama:qwen2.5:latest"
    assert data["payload"]["target_model_id"] == "ollama:llama3.2:latest"
    assert data["payload"]["generation"] == 2
    assert data["payload"]["is_successful"] is True


def test_serialize_model_error_event():
    event = RuntimeEvent(
        event_id="evt_err_01",
        event_type=EventType.ERROR,
        event_seq=3,
        session_id="sess_001",
        correlation_id="cmd_sw_01",
        payload=ErrorEventPayload(
            code="ACTIVE_TASK_CONFLICT",
            message="Model switch rejected: an autonomous task is currently executing",
            recoverable=True,
            details={"target_model_id": "ollama:llama3.2:latest"},
        ).model_dump(),
    )
    serialized = serialize_outbound_event(event)
    data = json.loads(serialized)
    assert data["event_type"] == "ERROR"
    assert data["payload"]["code"] == "ACTIVE_TASK_CONFLICT"
    assert data["correlation_id"] == "cmd_sw_01"
