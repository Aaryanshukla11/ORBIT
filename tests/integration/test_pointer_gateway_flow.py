"""Integration tests for MOVE_POINTER WebSocket gateway command pipeline."""

import json
import pytest
from starlette.testclient import TestClient

from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.gateway.app import create_app


def test_websocket_move_pointer_command_pipeline():
    """Test sending MOVE_POINTER over WebSocket and receiving POINTER_MOVED event."""
    config = RuntimeConfig(
        adapter_mode=AdapterMode.MOCK,
        capability_overrides={
            CapabilityType.POINTER: AdapterMode.PRODUCTION,
        },
    )
    app = create_app(config=config)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            # Drain initial RUNTIME_STATUS event
            status_str = websocket.receive_text()
            status_event = json.loads(status_str)
            sid = status_event["session_id"]

            # Send MOVE_POINTER command
            move_cmd = {
                "command_id": "cmd_mov_01",
                "command_type": "MOVE_POINTER",
                "session_id": sid,
                "payload": {
                    "x": 500,
                    "y": 300,
                    "tolerance_px": 2,
                },
            }
            websocket.send_text(json.dumps(move_cmd))

            # Receive POINTER_MOVED event
            resp_str = websocket.receive_text()
            resp_event = json.loads(resp_str)

            assert resp_event["event_type"] == "POINTER_MOVED"
            assert resp_event["correlation_id"] == "cmd_mov_01"
            assert resp_event["payload"]["status"] == "VERIFIED"


def test_websocket_move_pointer_out_of_bounds_error():
    """Test sending an out-of-bounds MOVE_POINTER command returns structured ERROR event."""
    config = RuntimeConfig(
        adapter_mode=AdapterMode.MOCK,
        capability_overrides={
            CapabilityType.POINTER: AdapterMode.PRODUCTION,
        },
    )
    app = create_app(config=config)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            status_str = websocket.receive_text()
            status_event = json.loads(status_str)
            sid = status_event["session_id"]

            move_cmd = {
                "command_id": "cmd_mov_bad",
                "command_type": "MOVE_POINTER",
                "session_id": sid,
                "payload": {
                    "x": -9999,
                    "y": -9999,
                },
            }
            websocket.send_text(json.dumps(move_cmd))

            resp_str = websocket.receive_text()
            resp_event = json.loads(resp_str)

            assert resp_event["event_type"] == "ERROR"
            assert resp_event["correlation_id"] == "cmd_mov_bad"
            assert "REJECTED_OUT_OF_BOUNDS" in resp_event["payload"]["message"]
