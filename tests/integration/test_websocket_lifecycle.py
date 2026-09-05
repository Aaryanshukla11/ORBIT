"""Integration tests for WebSocket connection lifecycle and message transport."""

import json
import pytest
from starlette.testclient import TestClient

from orbit.gateway.app import create_app


def test_websocket_connect_and_status_event():
    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            # First message received on connect should be RUNTIME_STATUS
            data_str = websocket.receive_text()
            event = json.loads(data_str)
            assert event["event_type"] == "RUNTIME_STATUS"
            assert event["payload"]["system_state"] in {"IDLE", "BOOTING"}
            assert "session_id" in event["payload"]


def test_websocket_heartbeat_roundtrip():
    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            # Drain status event
            websocket.receive_text()

            # Send heartbeat command
            cmd = {
                "command_id": "hb_001",
                "command_type": "HEARTBEAT",
                "session_id": "test_sess",
                "payload": {},
            }
            websocket.send_text(json.dumps(cmd))

            # Receive ack event
            response_str = websocket.receive_text()
            ack = json.loads(response_str)
            assert ack["event_type"] == "HEARTBEAT_ACK"
            assert ack["correlation_id"] == "hb_001"


def test_websocket_malformed_command_resilience():
    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            # Drain status event
            websocket.receive_text()

            # Send bad JSON
            websocket.send_text("{not_a_valid_json")

            # Expect ERROR event without socket disconnection
            error_str = websocket.receive_text()
            err_event = json.loads(error_str)
            assert err_event["event_type"] == "ERROR"
            assert err_event["payload"]["code"] == "INVALID_JSON"

            # Verify socket is still alive and responsive
            cmd = {
                "command_id": "hb_002",
                "command_type": "HEARTBEAT",
                "session_id": "test_sess",
                "payload": {},
            }
            websocket.send_text(json.dumps(cmd))
            ack_str = websocket.receive_text()
            ack = json.loads(ack_str)
            assert ack["event_type"] == "HEARTBEAT_ACK"
