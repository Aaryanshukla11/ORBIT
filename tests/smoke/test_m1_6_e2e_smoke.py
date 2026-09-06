"""End-to-End Smoke Test for Milestone M1.6: Closed-Loop Autonomy Pipeline via WebSocket Gateway."""

import json
import time
import pytest
from starlette.testclient import TestClient

from orbit.gateway.app import create_app


def test_m1_6_end_to_end_autonomous_smoke():
    """Verify full end-to-end closed-loop autonomous execution flow via WebSocket Gateway.

    Pipeline verified:
    Client -> WebSocket -> Gateway -> Orchestrator -> ClosedLoopExecutionEngine ->
    Pre-Action Observation -> Target Resolution -> Coordinate Validation Gate ->
    AutonomousDispatchGate -> Post-Action Observation -> ActionVerifier -> COMPLETED Event.
    """
    app = create_app()

    with TestClient(app) as client:
        with client.websocket_connect("/ws/m1_6_smoke_session") as ws:
            # 1. Receive initial RUNTIME_STATUS event
            init_msg = ws.receive_text()
            init_event = json.loads(init_msg)
            assert init_event["event_type"] == "RUNTIME_STATUS"
            assert init_event["session_id"] == "m1_6_smoke_session"

            # 2. Submit Task with TargetIntent payload
            submit_cmd = {
                "command_id": "cmd_m1_6_smoke_01",
                "command_type": "SUBMIT_TASK",
                "session_id": "m1_6_smoke_session",
                "payload": {
                    "prompt": "Locate and interact with target coordinate region autonomously",
                    "context": {
                        "target_intent": {
                            "strategy": "COORDINATE_REGION",
                            "explicit_bounds": {
                                "left": 100,
                                "top": 100,
                                "width": 150,
                                "height": 150,
                            },
                            "desktop_generation_id": 0,
                        },
                        "execution_policy": {
                            "allow_inconclusive_as_success": True,
                            "max_total_attempts": 2,
                        },
                        "action_type": "pointer_click",
                        "action_parameters": {"button": "left", "count": 1},
                    },
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

            assert completed, f"M1.6 Closed-Loop Task did not reach COMPLETED status within timeout. Events: {received_events}"

            # 4. Verify the progression of events received by the client
            event_types = [e["event_type"] for e in received_events]
            assert "TASK_STATE_CHANGED" in event_types
            assert "OBSERVATION_FRAME" in event_types
            assert "PLAN_UPDATED" in event_types

            # Verify monotonic sequence numbering on received events
            seq_numbers = [e["event_seq"] for e in received_events if "event_seq" in e]
            assert seq_numbers == sorted(seq_numbers), "Event sequence numbers must be monotonically increasing"
            assert len(set(seq_numbers)) == len(seq_numbers), "Event sequence numbers must be unique"
