"""Integration test for WebSocket Pointer Button and Click command pipelines in ORBIT M1.2B."""

import json
import pytest
from starlette.testclient import TestClient

from orbit.config import AdapterMode, RuntimeConfig
from orbit.contracts.capabilities import CapabilityType
from orbit.gateway.app import create_app


def test_websocket_click_and_button_command_flow():
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

            # 1. Send CLICK_POINTER command
            click_cmd = {
                "command_id": "cmd_clk_01",
                "command_type": "CLICK_POINTER",
                "session_id": sid,
                "payload": {
                    "button": "left",
                    "count": 1,
                    "dwell_ms": 10.0,
                },
            }
            websocket.send_text(json.dumps(click_cmd))

            resp_str = websocket.receive_text()
            resp_event = json.loads(resp_str)
            assert resp_event["event_type"] == "POINTER_CLICKED"
            assert resp_event["payload"]["status"] == "CLICK_VERIFIED"
            assert resp_event["payload"]["button"] == "left"

            # 2. Send POINTER_BUTTON_DOWN command
            down_cmd = {
                "command_id": "cmd_btn_down_01",
                "command_type": "POINTER_BUTTON_DOWN",
                "session_id": sid,
                "payload": {
                    "button": "right",
                },
            }
            websocket.send_text(json.dumps(down_cmd))

            resp_down_str = websocket.receive_text()
            resp_down = json.loads(resp_down_str)
            assert resp_down["event_type"] == "POINTER_BUTTON_STATE_CHANGED"
            assert resp_down["payload"]["state"] == "DOWN"
            assert resp_down["payload"]["button"] == "right"

            # 3. Send POINTER_BUTTON_UP command
            up_cmd = {
                "command_id": "cmd_btn_up_01",
                "command_type": "POINTER_BUTTON_UP",
                "session_id": sid,
                "payload": {
                    "button": "right",
                },
            }
            websocket.send_text(json.dumps(up_cmd))

            resp_up_str = websocket.receive_text()
            resp_up = json.loads(resp_up_str)
            assert resp_up["event_type"] == "POINTER_BUTTON_STATE_CHANGED"
            assert resp_up["payload"]["state"] == "UP"
            assert resp_up["payload"]["button"] == "right"

            # 4. Send POINTER_EMERGENCY_RELEASE command
            release_cmd = {
                "command_id": "cmd_emg_01",
                "command_type": "POINTER_EMERGENCY_RELEASE",
                "session_id": sid,
                "payload": {},
            }
            websocket.send_text(json.dumps(release_cmd))

            resp_rel_str = websocket.receive_text()
            resp_rel = json.loads(resp_rel_str)
            assert resp_rel["event_type"] == "POINTER_BUTTON_STATE_CHANGED"
            assert resp_rel["payload"]["state"] == "ALL_RELEASED"
            assert resp_rel["payload"]["success"] is True
