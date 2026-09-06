"""Integration tests for Gateway WebSocket history commands."""

import asyncio
import pytest
from starlette.testclient import TestClient

from orbit.gateway.app import create_app
from orbit.infrastructure.event_bus import EventBus
from orbit.infrastructure.clock import SystemClock
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.history.models import ExecutionRecord, ExecutionStatus
from orbit.runtime.history.store import ExecutionHistoryStore
import tempfile
from pathlib import Path


@pytest.mark.asyncio
async def test_gateway_history_rest_and_ws():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "test_gw_history.json"
        history_store = ExecutionHistoryStore(storage_path=storage_file)

        # Seed 1 record
        rec = ExecutionRecord(
            task_id="task_seed_1",
            goal="Test Gateway History Query",
            status=ExecutionStatus.COMPLETED,
            duration_ms=1200.0,
        )
        await history_store.save_record(rec)

        bus = EventBus()
        orch = OrbitOrchestrator(
            event_bus=bus,
            clock=SystemClock(),
            history_store=history_store,
        )
        app = create_app(orchestrator=orch, event_bus=bus)

        with TestClient(app) as client:
            # 1. Test REST endpoint
            resp = client.get("/api/history")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_count"] == 1
            assert data["records"][0]["task_id"] == "task_seed_1"

            # 2. Test WS protocol command
            with client.websocket_connect("/ws") as ws:
                # Read initial runtime status
                init_msg = ws.receive_json()
                assert init_msg["event_type"] == "RUNTIME_STATUS"

                # Send TASK_HISTORY_LIST command
                ws.send_json({
                    "command_id": "cmd_hist_1",
                    "command_type": "TASK_HISTORY_LIST",
                    "session_id": "sess_test",
                    "payload": {"limit": 10},
                })

                # Read response
                resp_msg = ws.receive_json()
                assert resp_msg["event_type"] == "TASK_HISTORY_LIST_RESPONSE"
                assert resp_msg["payload"]["total_count"] == 1
                assert resp_msg["payload"]["records"][0]["task_id"] == "task_seed_1"
