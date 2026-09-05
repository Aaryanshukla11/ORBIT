"""Unit tests for WebSocket protocol parsing, serialization, and binary framing."""

import json
import pytest

from orbit.contracts.commands import CommandType, SubmitTaskPayload
from orbit.contracts.events import EventType, RuntimeEvent
from orbit.gateway.protocol import (
    ProtocolError,
    pack_binary_frame,
    parse_inbound_message,
    serialize_outbound_event,
    unpack_binary_frame,
)


def test_parse_valid_submit_task_json():
    raw_msg = json.dumps({
        "command_id": "cmd_12345",
        "command_type": "SUBMIT_TASK",
        "session_id": "sess_abc",
        "payload": {
            "prompt": "Move cursor to center and click button",
            "context": {"app": "notepad"},
        },
    })
    base_cmd, payload = parse_inbound_message(raw_msg)
    assert base_cmd.command_id == "cmd_12345"
    assert base_cmd.command_type == CommandType.SUBMIT_TASK
    assert base_cmd.session_id == "sess_abc"
    assert isinstance(payload, SubmitTaskPayload)
    assert payload.prompt == "Move cursor to center and click button"
    assert payload.context == {"app": "notepad"}


def test_parse_invalid_json():
    with pytest.raises(ProtocolError) as exc_info:
        parse_inbound_message("{malformed_json: true")
    assert exc_info.value.code == "INVALID_JSON"


def test_parse_missing_command_envelope():
    raw = json.dumps({"only_payload": True})
    with pytest.raises(ProtocolError) as exc_info:
        parse_inbound_message(raw)
    assert exc_info.value.code == "INVALID_ENVELOPE"


def test_parse_unknown_command_type():
    raw = json.dumps({
        "command_id": "cmd_01",
        "command_type": "TOTALLY_UNKNOWN_COMMAND",
        "session_id": "sess_01",
        "payload": {},
    })
    with pytest.raises(ProtocolError) as exc_info:
        parse_inbound_message(raw)
    assert exc_info.value.code in {"INVALID_ENVELOPE", "UNKNOWN_COMMAND"}


def test_serialize_outbound_event():
    event = RuntimeEvent(
        event_id="evt_999",
        event_type=EventType.RUNTIME_STATUS,
        event_seq=42,
        session_id="sess_123",
        payload={"system_state": "IDLE"},
    )
    serialized = serialize_outbound_event(event)
    data = json.loads(serialized)
    assert data["event_id"] == "evt_999"
    assert data["event_type"] == "RUNTIME_STATUS"
    assert data["event_seq"] == 42
    assert data["session_id"] == "sess_123"
    assert data["payload"]["system_state"] == "IDLE"


def test_binary_frame_packing_roundtrip():
    raw_payload = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 64
    packed = pack_binary_frame(
        frame_seq=101,
        width=1920,
        height=1080,
        raw_bytes=raw_payload,
        format_code=1,
    )
    assert len(packed) == 16 + len(raw_payload)

    version, fmt, width, height, unpacked_bytes = unpack_binary_frame(packed)
    assert version == 1
    assert fmt == 1
    assert width == 1920
    assert height == 1080
    assert unpacked_bytes == raw_payload


def test_unpack_invalid_binary_frame():
    with pytest.raises(ProtocolError) as exc_info:
        unpack_binary_frame(b"SHORT")
    assert exc_info.value.code == "INVALID_BINARY_FRAME"

    with pytest.raises(ProtocolError) as exc_info:
        unpack_binary_frame(b"FAIL" + b"\x00" * 12)
    assert exc_info.value.code == "INVALID_MAGIC"
