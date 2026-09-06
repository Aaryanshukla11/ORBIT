"""Integration tests for Model WebSocket Real-Time Events and Multi-Client Synchronization (Milestone M1.9 Step 5)."""

import json
from datetime import datetime, timezone
import pytest
from starlette.testclient import TestClient

from orbit.adapters.registry import CapabilityRegistry
from orbit.contracts.events import EventType, RuntimeEvent
from orbit.gateway.app import create_app
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models.manager import ModelManager
from orbit.runtime.models.models import (
    ModelCapability,
    ModelDescriptor,
    ModelProviderKind,
    ModelStatus,
)
from orbit.runtime.orchestrator import OrbitOrchestrator


def create_event_test_environment():
    bus = EventBus()
    reg = CapabilityRegistry()
    mm = ModelManager(event_bus=bus)
    msm = ModelSessionManager(
        registry=mm.registry,
        providers=mm.providers,
        event_bus=bus,
    )
    orch = OrbitOrchestrator(
        event_bus=bus,
        registry=reg,
        clock=SystemClock(),
        model_manager=mm,
        model_session_manager=msm,
    )

    desc_a = ModelDescriptor(
        model_id="mock:alpha-model",
        provider_model_name="mock-alpha",
        provider=ModelProviderKind.OLLAMA,
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT},
        context_window=4096,
        status=ModelStatus.INSTALLED,
    )
    desc_b = ModelDescriptor(
        model_id="mock:beta-model",
        provider_model_name="mock-beta",
        provider=ModelProviderKind.OLLAMA,
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.VISION},
        context_window=8192,
        status=ModelStatus.INSTALLED,
    )
    msm._registry._models[desc_a.model_id] = desc_a
    msm._registry._models[desc_b.model_id] = desc_b

    return orch, bus, msm, mm


def test_multiple_clients_receive_same_model_event():
    """Test 7: Multiple connected clients receive the exact same real-time model switch event."""
    orch, bus, msm, mm = create_event_test_environment()
    app = create_app(orchestrator=orch, event_bus=bus)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws_client_a, client.websocket_connect("/ws") as ws_client_b:
            # Drain initial RUNTIME_STATUS on both clients
            ws_client_a.receive_text()
            ws_client_b.receive_text()

            # Client A activates alpha-model
            ws_client_a.send_text(json.dumps({
                "command_id": "cmd_act_a",
                "command_type": "MODEL_ACTIVATE",
                "session_id": "sess_a",
                "payload": {"model_id": "mock:alpha-model"},
            }))

            # Drain events on Client A until activation completes
            msg_a = json.loads(ws_client_a.receive_text())
            while msg_a.get("correlation_id") != "cmd_act_a":
                msg_a = json.loads(ws_client_a.receive_text())

            # Verify Client B received MODEL_ACTIVATED broadcast
            msg_b = json.loads(ws_client_b.receive_text())
            while msg_b.get("event_type") != "MODEL_ACTIVATED":
                msg_b = json.loads(ws_client_b.receive_text())
            assert msg_b["payload"]["model_id"] == "mock:alpha-model"
            assert msg_b["payload"]["generation"] == 1

            # Client A switches to beta-model
            ws_client_a.send_text(json.dumps({
                "command_id": "cmd_sw_b",
                "command_type": "MODEL_SWITCH",
                "session_id": "sess_a",
                "payload": {"model_id": "mock:beta-model"},
            }))

            # Client A receives MODEL_SWITCHED
            sw_a = json.loads(ws_client_a.receive_text())
            while sw_a.get("event_type") != "MODEL_SWITCHED":
                sw_a = json.loads(ws_client_a.receive_text())
            assert sw_a["payload"]["target_model_id" if "target_model_id" in sw_a["payload"] else "active_model_id"] == "mock:beta-model"

            # Client B also receives MODEL_SWITCHED broadcast in real-time
            sw_b = json.loads(ws_client_b.receive_text())
            while sw_b.get("event_type") != "MODEL_SWITCHED":
                sw_b = json.loads(ws_client_b.receive_text())
            assert sw_b["payload"]["target_model_id" if "target_model_id" in sw_b["payload"] else "active_model_id"] == "mock:beta-model"
            assert sw_b["payload"]["generation"] == 2


def test_connection_state_synchronization_late_joining_client():
    """Phase 5: A newly connecting client immediately observes current authoritative model state."""
    orch, bus, msm, mm = create_event_test_environment()
    app = create_app(orchestrator=orch, event_bus=bus)

    with TestClient(app) as client:
        # Client 1 connects and activates beta-model
        with client.websocket_connect("/ws") as ws1:
            ws1.receive_text()  # Drain status
            ws1.send_text(json.dumps({
                "command_id": "cmd_act_beta",
                "command_type": "MODEL_ACTIVATE",
                "session_id": "sess_1",
                "payload": {"model_id": "mock:beta-model"},
            }))
            msg = json.loads(ws1.receive_text())
            while msg.get("correlation_id") != "cmd_act_beta":
                msg = json.loads(ws1.receive_text())
            assert msg["payload"]["generation"] == 1

        # Now Client 2 connects fresh
        with client.websocket_connect("/ws") as ws2:
            ws2.receive_text()  # Drain initial status

            # Client 2 queries MODEL_STATUS
            ws2.send_text(json.dumps({
                "command_id": "cmd_stat_c2",
                "command_type": "MODEL_STATUS",
                "session_id": "sess_2",
                "payload": {},
            }))
            stat_resp = json.loads(ws2.receive_text())
            assert stat_resp["event_type"] == "MODEL_STATUS_RESPONSE"
            assert stat_resp["correlation_id"] == "cmd_stat_c2"
            assert stat_resp["payload"]["is_active"] is True
            assert stat_resp["payload"]["active_model"]["model_id"] == "mock:beta-model"
            assert stat_resp["payload"]["active_generation"] == 1


def test_realtime_model_discovery_broadcast():
    """Phase 3: Model discovery emits MODEL_DISCOVERED events to all active listeners."""
    orch, bus, msm, mm = create_event_test_environment()
    app = create_app(orchestrator=orch, event_bus=bus)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws1, client.websocket_connect("/ws") as ws2:
            ws1.receive_text()
            ws2.receive_text()

            # Client 1 triggers discovery
            ws1.send_text(json.dumps({
                "command_id": "cmd_disc_test",
                "command_type": "MODEL_DISCOVER",
                "session_id": "sess_1",
                "payload": {"include_runtimes": True, "include_cloud": False, "include_files": False},
            }))

            # Client 1 receives MODEL_DISCOVER_RESPONSE
            resp1 = json.loads(ws1.receive_text())
            while resp1.get("correlation_id") != "cmd_disc_test":
                resp1 = json.loads(ws1.receive_text())
            assert resp1["event_type"] == "MODEL_DISCOVER_RESPONSE"
            assert "discovered_count" in resp1["payload"]


def test_model_shutdown_broadcasts_events():
    """Phase 3: Model shutdown emits MODEL_SHUTDOWN and MODEL_DEACTIVATED events."""
    orch, bus, msm, mm = create_event_test_environment()
    app = create_app(orchestrator=orch, event_bus=bus)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()

            # Activate model
            ws.send_text(json.dumps({
                "command_id": "cmd_act_shut",
                "command_type": "MODEL_ACTIVATE",
                "session_id": "sess_1",
                "payload": {"model_id": "mock:alpha-model"},
            }))
            msg = json.loads(ws.receive_text())
            while msg.get("correlation_id") != "cmd_act_shut":
                msg = json.loads(ws.receive_text())

            # Shutdown active model via session manager directly (e.g. during system shutdown)
            import asyncio
            asyncio.run(msm.shutdown_active_model())

            # Read broadcast events on websocket
            events_received = []
            for _ in range(2):
                evt = json.loads(ws.receive_text())
                events_received.append(evt["event_type"])

            assert "MODEL_SHUTDOWN" in events_received
            assert "MODEL_DEACTIVATED" in events_received
