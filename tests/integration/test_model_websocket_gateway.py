"""Integration tests for Model WebSocket Gateway commands and routing (Milestone M1.9 Step 5)."""

import json
from datetime import datetime, timezone
import pytest
from starlette.testclient import TestClient

from orbit.adapters.registry import CapabilityRegistry
from orbit.contracts.events import EventType, RuntimeEvent
from orbit.contracts.runtime import SystemState
from orbit.gateway.app import create_app
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.model_runtime.contracts import (
    ModelCapability,
    ModelRuntimeCapability,
    ModelRuntimeKind,
    ModelRuntimeStatus,
)
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models.manager import ModelManager
from orbit.runtime.models.models import (
    ModelDescriptor,
    ModelProviderKind,
    ModelStatus,
)
from orbit.runtime.orchestrator import OrbitOrchestrator


def create_test_orchestrator(is_task_executing: bool = False):
    bus = EventBus()
    reg = CapabilityRegistry()
    mm = ModelManager(event_bus=bus)
    msm = ModelSessionManager(
        registry=mm.registry,
        providers=mm.providers,
        event_bus=bus,
        is_task_executing_fn=lambda: is_task_executing,
    )
    orch = OrbitOrchestrator(
        event_bus=bus,
        registry=reg,
        clock=SystemClock(),
        model_manager=mm,
        model_session_manager=msm,
    )
    return orch, bus, msm, mm


@pytest.fixture
def test_models():
    desc_a = ModelDescriptor(
        model_id="mock:model-a",
        provider_model_name="mock-model-a",
        provider=ModelProviderKind.OLLAMA,
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT},
        context_window=4096,
        status=ModelStatus.INSTALLED,
    )
    desc_b = ModelDescriptor(
        model_id="mock:model-b",
        provider_model_name="mock-model-b",
        provider=ModelProviderKind.OLLAMA,
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.VISION},
        context_window=8192,
        status=ModelStatus.INSTALLED,
    )
    return [desc_a, desc_b]


def test_model_list_returns_safe_metadata(test_models):
    """Test 1: MODEL_LIST returns safe model metadata without secrets."""
    orch, bus, msm, mm = create_test_orchestrator()
    for m in test_models:
        msm._registry._models[m.model_id] = m

    app = create_app(orchestrator=orch, event_bus=bus)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            # Drain initial RUNTIME_STATUS
            ws.receive_text()

            # Send MODEL_LIST command
            ws.send_text(json.dumps({
                "command_id": "cmd_list_1",
                "command_type": "MODEL_LIST",
                "session_id": "sess_test",
                "payload": {"include_all": True},
            }))

            resp_str = ws.receive_text()
            resp = json.loads(resp_str)
            assert resp["event_type"] == "MODEL_LIST_RESPONSE"
            assert resp["correlation_id"] == "cmd_list_1"
            payload = resp["payload"]
            assert payload["total_count"] >= 2

            model_ids = [m["model_id"] for m in payload["models"]]
            assert "mock:model-a" in model_ids
            assert "mock:model-b" in model_ids

            # Verify safe fields and zero secrets
            for m in payload["models"]:
                assert "api_key" not in m
                assert "secret" not in m
                assert "password" not in m
                assert "token" not in m
                assert "display_name" in m
                assert "provider" in m
                assert "capabilities" in m
                assert "runtime_kind" in m


def test_model_active_returns_honest_state(test_models):
    """Test 2: MODEL_ACTIVE returns honest inactive state when none active, and active model when active."""
    orch, bus, msm, mm = create_test_orchestrator()
    for m in test_models:
        msm._registry._models[m.model_id] = m

    app = create_app(orchestrator=orch, event_bus=bus)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()  # Drain RUNTIME_STATUS

            # 1. Query when no model active
            ws.send_text(json.dumps({
                "command_id": "cmd_active_1",
                "command_type": "MODEL_ACTIVE",
                "session_id": "sess_test",
                "payload": {},
            }))

            resp_str = ws.receive_text()
            resp = json.loads(resp_str)
            assert resp["event_type"] == "MODEL_ACTIVE_RESPONSE"
            assert resp["correlation_id"] == "cmd_active_1"
            assert resp["payload"]["is_active"] is False
            assert resp["payload"]["active_model"] is None
            assert resp["payload"]["status"] == "NO_ACTIVE_MODEL"

            # 2. Activate model-a
            ws.send_text(json.dumps({
                "command_id": "cmd_act_1",
                "command_type": "MODEL_ACTIVATE",
                "session_id": "sess_test",
                "payload": {"model_id": "mock:model-a"},
            }))
            # Drain activation events until MODEL_ACTIVATED response
            act_resp_str = ws.receive_text()
            act_resp = json.loads(act_resp_str)
            while act_resp.get("correlation_id") != "cmd_act_1" and act_resp.get("event_type") != "MODEL_ACTIVATED":
                act_resp_str = ws.receive_text()
                act_resp = json.loads(act_resp_str)

            assert act_resp["payload"]["model_id"] == "mock:model-a"
            assert act_resp["payload"]["generation"] == 1

            # 3. Query MODEL_ACTIVE again
            ws.send_text(json.dumps({
                "command_id": "cmd_active_2",
                "command_type": "MODEL_ACTIVE",
                "session_id": "sess_test",
                "payload": {},
            }))

            resp2_str = ws.receive_text()
            resp2 = json.loads(resp2_str)
            while resp2.get("correlation_id") != "cmd_active_2":
                resp2_str = ws.receive_text()
                resp2 = json.loads(resp2_str)

            assert resp2["event_type"] == "MODEL_ACTIVE_RESPONSE"
            assert resp2["payload"]["is_active"] is True
            assert resp2["payload"]["active_model"]["model_id"] == "mock:model-a"
            assert resp2["payload"]["generation"] == 1


def test_model_activate_routes_through_session_manager(test_models):
    """Test 3: MODEL_ACTIVATE routes through ModelSessionManager and establishes active model context."""
    orch, bus, msm, mm = create_test_orchestrator()
    for m in test_models:
        msm._registry._models[m.model_id] = m

    app = create_app(orchestrator=orch, event_bus=bus)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()  # Drain RUNTIME_STATUS

            ws.send_text(json.dumps({
                "command_id": "cmd_act_test3",
                "command_type": "MODEL_ACTIVATE",
                "session_id": "sess_test",
                "payload": {"model_id": "mock:model-b"},
            }))

            # Wait for correlated response
            msg_str = ws.receive_text()
            msg = json.loads(msg_str)
            while msg.get("correlation_id") != "cmd_act_test3":
                msg_str = ws.receive_text()
                msg = json.loads(msg_str)

            assert msg["event_type"] == "MODEL_ACTIVATED"
            assert msg["payload"]["model_id"] == "mock:model-b"
            assert msg["payload"]["generation"] == 1

            # Verify orchestrator and session manager state
            assert msm.is_model_active() is True
            assert msm.get_active_context().model_id == "mock:model-b"
            assert msm.get_active_generation() == 1


def test_successful_model_switch(test_models):
    """Test 4: Successful model switch updates active model and emits MODEL_SWITCHED."""
    orch, bus, msm, mm = create_test_orchestrator()
    for m in test_models:
        msm._registry._models[m.model_id] = m

    app = create_app(orchestrator=orch, event_bus=bus)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()  # Drain status

            # Activate model-a first
            ws.send_text(json.dumps({
                "command_id": "cmd_act_4",
                "command_type": "MODEL_ACTIVATE",
                "session_id": "sess_test",
                "payload": {"model_id": "mock:model-a"},
            }))
            msg = json.loads(ws.receive_text())
            while msg.get("correlation_id") != "cmd_act_4":
                msg = json.loads(ws.receive_text())
            assert msg["payload"]["generation"] == 1

            # Switch to model-b
            ws.send_text(json.dumps({
                "command_id": "cmd_sw_4",
                "command_type": "MODEL_SWITCH",
                "session_id": "sess_test",
                "payload": {
                    "model_id": "mock:model-b",
                    "policy": "REJECT_DURING_ACTIVE_TASK",
                },
            }))

            sw_msg = json.loads(ws.receive_text())
            while sw_msg.get("correlation_id") != "cmd_sw_4":
                sw_msg = json.loads(ws.receive_text())

            assert sw_msg["event_type"] == "MODEL_SWITCHED"
            assert sw_msg["payload"]["previous_model_id"] == "mock:model-a"
            assert sw_msg["payload"]["active_model_id"] == "mock:model-b"
            assert sw_msg["payload"]["generation"] == 2
            assert sw_msg["payload"]["switched"] is True

            # Verify central authoritative state
            assert msm.get_active_context().model_id == "mock:model-b"
            assert msm.get_active_generation() == 2


def test_failed_switch_returns_error_and_preserves_old_model(test_models):
    """Test 5: Failed switch to unknown model returns MODEL_NOT_FOUND error and preserves Model A."""
    orch, bus, msm, mm = create_test_orchestrator()
    for m in test_models:
        msm._registry._models[m.model_id] = m

    app = create_app(orchestrator=orch, event_bus=bus)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()

            # Activate Model A
            ws.send_text(json.dumps({
                "command_id": "cmd_act_5",
                "command_type": "MODEL_ACTIVATE",
                "session_id": "sess_test",
                "payload": {"model_id": "mock:model-a"},
            }))
            msg = json.loads(ws.receive_text())
            while msg.get("correlation_id") != "cmd_act_5":
                msg = json.loads(ws.receive_text())
            assert msg["payload"]["generation"] == 1

            # Attempt switch to non-existent model
            ws.send_text(json.dumps({
                "command_id": "cmd_sw_fail_5",
                "command_type": "MODEL_SWITCH",
                "session_id": "sess_test",
                "payload": {"model_id": "nonexistent:model-xyz"},
            }))

            err_msg = json.loads(ws.receive_text())
            while err_msg.get("correlation_id") != "cmd_sw_fail_5":
                err_msg = json.loads(ws.receive_text())

            assert err_msg["event_type"] == "ERROR"
            assert err_msg["payload"]["code"] == "MODEL_NOT_FOUND"

            # Verify Model A is retained
            assert msm.get_active_context().model_id == "mock:model-a"
            assert msm.get_active_generation() == 1


def test_switch_during_active_task_returns_active_task_conflict(test_models):
    """Test 6: Switch during active autonomous task execution returns ACTIVE_TASK_CONFLICT."""
    orch, bus, msm, mm = create_test_orchestrator()
    for m in test_models:
        msm._registry._models[m.model_id] = m

    app = create_app(orchestrator=orch, event_bus=bus)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()  # Drain initial status

            # Transition system state to BUSY after lifespan initialization
            orch._system_sm.transition_to(SystemState.BUSY)

            # Attempt model switch while task is executing
            ws.send_text(json.dumps({
                "command_id": "cmd_sw_busy",
                "command_type": "MODEL_SWITCH",
                "session_id": "sess_test",
                "payload": {
                    "model_id": "mock:model-b",
                    "policy": "REJECT_DURING_ACTIVE_TASK",
                },
            }))

            err_msg = json.loads(ws.receive_text())
            while err_msg.get("correlation_id") != "cmd_sw_busy":
                err_msg = json.loads(ws.receive_text())

            assert err_msg["event_type"] == "ERROR"
            assert err_msg["payload"]["code"] == "ACTIVE_TASK_CONFLICT"
            assert "actively executing" in err_msg["payload"]["message"]


def test_secrets_never_appear_in_any_response(test_models):
    """Test 8: API keys, authorization tokens, and credentials never appear in any response."""
    orch, bus, msm, mm = create_test_orchestrator()
    desc_secret = ModelDescriptor(
        model_id="cloud:secret-model",
        provider_model_name="gpt-4o",
        provider=ModelProviderKind.CLOUD_OPENAI,
        status=ModelStatus.INSTALLED,
        metadata={"internal_note": "safe_metadata"},
    )
    msm._registry._models[desc_secret.model_id] = desc_secret

    app = create_app(orchestrator=orch, event_bus=bus)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()

            ws.send_text(json.dumps({
                "command_id": "cmd_list_sec",
                "command_type": "MODEL_LIST",
                "session_id": "sess_test",
                "payload": {"include_all": True},
            }))

            raw_resp = ws.receive_text()
            assert "sk-" not in raw_resp
            assert "bearer" not in raw_resp.lower()
            assert "api_key" not in raw_resp.lower()
            assert "password" not in raw_resp.lower()


def test_invalid_websocket_messages_fail_safely():
    """Test 9: Invalid JSON, unknown command types, and missing payload fields fail safely."""
    orch, bus, msm, mm = create_test_orchestrator()
    app = create_app(orchestrator=orch, event_bus=bus)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()  # Drain status

            # 1. Malformed JSON
            ws.send_text("{bad_json")
            err1 = json.loads(ws.receive_text())
            assert err1["event_type"] == "ERROR"
            assert err1["payload"]["code"] == "INVALID_JSON"

            # 2. Unknown command
            ws.send_text(json.dumps({
                "command_id": "c_unk",
                "command_type": "MODEL_NONEXISTENT_COMMAND",
                "session_id": "s1",
                "payload": {},
            }))
            err2 = json.loads(ws.receive_text())
            assert err2["event_type"] == "ERROR"
            assert err2["payload"]["code"] in {"UNKNOWN_COMMAND", "INVALID_ENVELOPE"}

            # 3. Socket still alive and operational
            ws.send_text(json.dumps({
                "command_id": "c_status",
                "command_type": "MODEL_STATUS",
                "session_id": "s1",
                "payload": {},
            }))
            stat_resp = json.loads(ws.receive_text())
            assert stat_resp["event_type"] == "MODEL_STATUS_RESPONSE"
            assert stat_resp["correlation_id"] == "c_status"


def test_unavailable_models_cannot_be_falsely_activated(test_models):
    """Test 10: Unavailable or non-existent models cannot be falsely activated."""
    orch, bus, msm, mm = create_test_orchestrator()
    app = create_app(orchestrator=orch, event_bus=bus)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()

            # Attempt activating unknown model
            ws.send_text(json.dumps({
                "command_id": "cmd_act_unavail",
                "command_type": "MODEL_ACTIVATE",
                "session_id": "sess_test",
                "payload": {"model_id": "ghost:does-not-exist"},
            }))

            err = json.loads(ws.receive_text())
            while err.get("correlation_id") != "cmd_act_unavail":
                err = json.loads(ws.receive_text())

            assert err["event_type"] == "ERROR"
            assert err["payload"]["code"] in {"MODEL_NOT_FOUND", "MODEL_UNAVAILABLE"}
            assert msm.is_model_active() is False


def test_model_health_command(test_models):
    """Test MODEL_HEALTH command returns accurate runtime health status."""
    orch, bus, msm, mm = create_test_orchestrator()
    for m in test_models:
        msm._registry._models[m.model_id] = m

    app = create_app(orchestrator=orch, event_bus=bus)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()

            # 1. Health when no model active
            ws.send_text(json.dumps({
                "command_id": "cmd_hlth_1",
                "command_type": "MODEL_HEALTH",
                "session_id": "sess_test",
                "payload": {},
            }))
            resp1 = json.loads(ws.receive_text())
            assert resp1["event_type"] == "MODEL_HEALTH_RESPONSE"
            assert resp1["payload"]["status"] == "UNKNOWN"

            # 2. Activate model-a
            ws.send_text(json.dumps({
                "command_id": "cmd_act_hlth",
                "command_type": "MODEL_ACTIVATE",
                "session_id": "sess_test",
                "payload": {"model_id": "mock:model-a"},
            }))
            msg = json.loads(ws.receive_text())
            while msg.get("correlation_id") != "cmd_act_hlth":
                msg = json.loads(ws.receive_text())

            # 3. Health when model-a active
            ws.send_text(json.dumps({
                "command_id": "cmd_hlth_2",
                "command_type": "MODEL_HEALTH",
                "session_id": "sess_test",
                "payload": {},
            }))
            resp2 = json.loads(ws.receive_text())
            while resp2.get("correlation_id") != "cmd_hlth_2":
                resp2 = json.loads(ws.receive_text())
            assert resp2["event_type"] == "MODEL_HEALTH_RESPONSE"
            assert resp2["payload"]["status"] == "HEALTHY"
            assert resp2["payload"]["is_healthy"] is True
            assert resp2["payload"]["model_id"] == "mock:model-a"
