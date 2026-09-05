"""Gateway protocol serialization, deserialization, and binary framing."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import struct
from typing import Any, Dict, Tuple, Union
from pydantic import ValidationError

from orbit.contracts.commands import (
    AuthorizeActionPayload,
    BaseCommand,
    CancelTaskPayload,
    ClickPointerPayload,
    CommandType,
    HeartbeatPayload,
    KeyboardEmergencyReleasePayload,
    KeyboardKeyPayload,
    MovePointerPayload,
    PauseTaskPayload,
    PointerButtonPayload,
    PointerEmergencyReleasePayload,
    PressShortcutPayload,
    RecoverKeyboardLockoutPayload,
    RecoverLockedPayload,
    RecoverPointerLockoutPayload,
    ReleaseTakeoverPayload,
    RequestFramePayload,
    ResumeTaskPayload,
    SubmitTaskPayload,
    TriggerTakeoverPayload,
    TypeTextPayload,
)
from orbit.contracts.events import RuntimeEvent


class ProtocolError(Exception):
    """Raised when an inbound message fails structural or semantic validation."""

    def __init__(self, message: str, code: str = "MALFORMED_MESSAGE", details: Any = None) -> None:
        self.code = code
        self.details = details
        super().__init__(message)


COMMAND_PAYLOAD_MAP = {
    CommandType.SUBMIT_TASK: SubmitTaskPayload,
    CommandType.CANCEL_TASK: CancelTaskPayload,
    CommandType.PAUSE_TASK: PauseTaskPayload,
    CommandType.RESUME_TASK: ResumeTaskPayload,
    CommandType.AUTHORIZE_ACTION: AuthorizeActionPayload,
    CommandType.REQUEST_FRAME: RequestFramePayload,
    CommandType.TRIGGER_TAKEOVER: TriggerTakeoverPayload,
    CommandType.RELEASE_TAKEOVER: ReleaseTakeoverPayload,
    CommandType.RECOVER_LOCKED: RecoverLockedPayload,
    CommandType.MOVE_POINTER: MovePointerPayload,
    CommandType.CLICK_POINTER: ClickPointerPayload,
    CommandType.POINTER_BUTTON_DOWN: PointerButtonPayload,
    CommandType.POINTER_BUTTON_UP: PointerButtonPayload,
    CommandType.POINTER_EMERGENCY_RELEASE: PointerEmergencyReleasePayload,
    CommandType.RECOVER_POINTER_LOCKOUT: RecoverPointerLockoutPayload,
    CommandType.TYPE_TEXT: TypeTextPayload,
    CommandType.PRESS_SHORTCUT: PressShortcutPayload,
    CommandType.KEYBOARD_KEY_DOWN: KeyboardKeyPayload,
    CommandType.KEYBOARD_KEY_UP: KeyboardKeyPayload,
    CommandType.KEYBOARD_EMERGENCY_RELEASE: KeyboardEmergencyReleasePayload,
    CommandType.RECOVER_KEYBOARD_LOCKOUT: RecoverKeyboardLockoutPayload,
    CommandType.HEARTBEAT: HeartbeatPayload,
}



def parse_inbound_message(raw_data: Union[str, bytes, Dict[str, Any]]) -> Tuple[BaseCommand, Any]:
    """Parse and strictly validate an inbound JSON WebSocket message.

    Returns a tuple of (BaseCommand, ValidatedPayload).
    """
    if isinstance(raw_data, (bytes, bytearray)):
        try:
            raw_str = raw_data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ProtocolError(f"Invalid UTF-8 encoding: {e}", code="INVALID_ENCODING")
        try:
            data = json.loads(raw_str)
        except json.JSONDecodeError as e:
            raise ProtocolError(f"Invalid JSON payload: {e}", code="INVALID_JSON")
    elif isinstance(raw_data, str):
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as e:
            raise ProtocolError(f"Invalid JSON payload: {e}", code="INVALID_JSON")
    elif isinstance(raw_data, dict):
        data = raw_data
    else:
        raise ProtocolError(f"Unsupported message type: {type(raw_data)}", code="UNSUPPORTED_TYPE")

    if not isinstance(data, dict):
        raise ProtocolError("Root WebSocket message must be a JSON object", code="INVALID_ROOT_TYPE")

    # Validate Base Command Header
    try:
        base_cmd = BaseCommand(
            command_id=data.get("command_id", ""),
            command_type=data.get("command_type", ""),
            session_id=data.get("session_id", ""),
            timestamp=data.get("timestamp") or datetime.now(timezone.utc),
            correlation_id=data.get("correlation_id"),
        )
    except ValidationError as e:
        raise ProtocolError(f"Invalid command envelope: {e}", code="INVALID_ENVELOPE", details=e.errors())

    # Validate Specific Payload
    payload_class = COMMAND_PAYLOAD_MAP.get(base_cmd.command_type)
    if not payload_class:
        raise ProtocolError(f"Unknown command type: {base_cmd.command_type}", code="UNKNOWN_COMMAND")

    payload_data = data.get("payload", {})
    try:
        validated_payload = payload_class(**payload_data)
    except ValidationError as e:
        raise ProtocolError(
            f"Invalid payload for {base_cmd.command_type}: {e}",
            code="INVALID_PAYLOAD",
            details=e.errors(),
        )

    return base_cmd, validated_payload


def serialize_outbound_event(event: RuntimeEvent) -> str:
    """Serialize a RuntimeEvent into standard JSON string."""
    return event.model_dump_json()


# Binary Viewport Frame Protocol:
# Header (16 bytes):
# Magic (4B): b'ORBT'
# Version (1B): 0x01
# Format (1B): 0x01 (JPEG), 0x02 (PNG), 0x03 (RAW)
# Width (2B): uint16
# Height (2B): uint16
# Sequence (4B): uint32
# Reserved (2B): uint16 (0x0000)
# Followed by raw frame bytes

BINARY_MAGIC = b"ORBT"
BINARY_VERSION = 0x01


def pack_binary_frame(
    frame_seq: int,
    width: int,
    height: int,
    raw_bytes: bytes,
    format_code: int = 1,  # 1 = JPEG
) -> bytes:
    """Pack raw frame buffer into ORBIT binary frame streaming format."""
    header = struct.pack(
        ">4sBBHHIH",
        BINARY_MAGIC,
        BINARY_VERSION,
        format_code,
        width,
        height,
        frame_seq,
        0,  # reserved
    )
    return header + raw_bytes


def unpack_binary_frame(data: bytes) -> Tuple[int, int, int, int, bytes]:
    """Unpack ORBIT binary frame into (version, format_code, width, height, raw_bytes)."""
    if len(data) < 16:
        raise ProtocolError("Binary frame buffer too short (<16 bytes)", code="INVALID_BINARY_FRAME")

    magic, version, fmt, width, height, seq, _ = struct.unpack(">4sBBHHIH", data[:16])
    if magic != BINARY_MAGIC:
        raise ProtocolError(f"Invalid binary magic: {magic}", code="INVALID_MAGIC")

    return version, fmt, width, height, data[16:]
