"""End-to-End Smoke Test for Milestone M0: Full WebSocket to Runtime Loop."""

import json
import time
import pytest
from starlette.testclient import TestClient

from orbit.gateway.app import create_app


def test_m0_end_to_end_smoke():
    """Verify full end-to-end flow:

    Client -> WebSocket -> Gateway -> Orchestrator -> Mock Observation ->
    Synthetic Execution Plan -> Mock Actions -> Verification -> COMPLETED Event -> WebSocket.
    """
    app = create_app()

    with TestClient(app) as client:
        with client.websocket_connect("/ws/smoke_test_session") as ws:
            # 1. Receive initial RUNTIME_STATUS event
            init_msg = ws.receive_text()
            init_event = json.loads(init_msg)
            assert init_event["event_type"] == "RUNTIME_STATUS"
            assert init_event["session_id"] == "smoke_test_session"

            # 2. Submit Task via WebSocket command
            submit_cmd = {
                "command_id": "cmd_smoke_01",
                "command_type": "SUBMIT_TASK",
                "session_id": "smoke_test_session",
                "payload": {
                    "prompt": "Synthetically execute test interaction",
                    "context": {"env": "smoke_test"},
                },
            }
            ws.send_text(json.dumps(submit_cmd))

            # 3. Collect events until task completion
            received_events = []
            completed = False
            start_time = time.time()

            while not completed and (time.time() - start_time < 5.0):
                msg = ws.receive_text()
                evt = json.loads(msg)
                received_events.append(evt)

                if (
                    evt.get("event_type") == "TASK_STATE_CHANGED"
                    and evt.get("payload", {}).get("status") == "COMPLETED"
                ):
                    completed = True

            assert completed, f"Task did not reach COMPLETED status within timeout. Events: {received_events}"

            # 4. Verify the progression of events received by the client
            event_types = [e["event_type"] for e in received_events]
            assert "TASK_STATE_CHANGED" in event_types
            assert "OBSERVATION_FRAME" in event_types
            assert "PLAN_UPDATED" in event_types
            assert "ACTION_STAGE_CHANGED" in event_types

            # Verify monotonic sequence numbering on received events
            seq_numbers = [e["event_seq"] for e in received_events if "event_seq" in e]
            assert seq_numbers == sorted(seq_numbers), "Event sequence numbers must be monotonically increasing"
            assert len(set(seq_numbers)) == len(seq_numbers), "Event sequence numbers must be unique"
