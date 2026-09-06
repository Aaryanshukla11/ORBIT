"""Tests for Gateway Diagnostic REST endpoints and WebSocket commands."""

import pytest
from fastapi.testclient import TestClient
from orbit.gateway.app import create_app
from orbit.config import RuntimeConfig
from orbit.contracts.commands import CommandType


def test_gateway_diagnostics_rest():
    cfg = RuntimeConfig()
    app = create_app(config=cfg)

    with TestClient(app) as client:
        # 1. GET /api/diagnostics
        resp = client.get("/api/diagnostics")
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_status" in data
        assert "subsystems" in data
        assert len(data["subsystems"]) >= 6

        # 2. POST /api/diagnostics/run
        resp_run = client.post("/api/diagnostics/run")
        assert resp_run.status_code == 200
        data_run = resp_run.json()
        assert "overall_status" in data_run
        assert "metrics" in data_run
        assert data_run["metrics"]["total_subsystems"] >= 6


def test_gateway_diagnostics_websocket():
    cfg = RuntimeConfig()
    app = create_app(config=cfg)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            # First message is usually RUNTIME_STATUS or SESSION_STATE_CHANGED
            msg1 = ws.receive_json()
            assert "event_type" in msg1

            # Send DIAGNOSTICS_RUN command
            cmd = {
                "command_id": "cmd_diag_001",
                "command_type": CommandType.DIAGNOSTICS_RUN.value,
                "session_id": msg1.get("session_id", "sess_default"),
                "payload": {},
            }
            ws.send_json(cmd)

            # Receive DIAGNOSTICS_RUN_RESPONSE
            resp_event = ws.receive_json()
            assert resp_event["event_type"] == "DIAGNOSTICS_RUN_RESPONSE"
            assert resp_event["correlation_id"] == "cmd_diag_001"
            assert "subsystems" in resp_event["payload"]
            assert len(resp_event["payload"]["subsystems"]) >= 6
