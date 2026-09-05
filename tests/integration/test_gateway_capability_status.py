"""Integration tests for Gateway capability health and status exposure."""

import pytest
from starlette.testclient import TestClient

from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.gateway.app import create_app


def test_gateway_status_exposes_mock_capability_health():
    config = RuntimeConfig(adapter_mode=AdapterMode.MOCK)
    app = create_app(config=config)

    with TestClient(app) as client:
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()

        assert data["adapter_mode"] == "MOCK"
        assert "capabilities" in data

        caps = data["capabilities"]
        for cap_name in ["OBSERVATION", "POINTER", "KEYBOARD", "HUMAN_TAKEOVER", "WORKSPACE", "SAFETY"]:
            assert cap_name in caps
            assert caps[cap_name]["adapter_mode"] == "MOCK"
            assert caps[cap_name]["lifecycle_state"] == "READY"
            assert caps[cap_name]["status"] == "HEALTHY"


def test_gateway_status_exposes_production_capability_health_honestly():
    config = RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION)
    app = create_app(config=config)

    with TestClient(app) as client:
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()

        assert data["adapter_mode"] == "PRODUCTION"
        caps = data["capabilities"]

        # Observation is active in M1.1 production mode
        assert caps["OBSERVATION"]["adapter_mode"] == "PRODUCTION"
        assert caps["OBSERVATION"]["lifecycle_state"] == "READY"
        assert caps["OBSERVATION"]["status"] in {"HEALTHY", "DEGRADED"}

        # Pointer is active in M1.2A production mode
        assert caps["POINTER"]["adapter_mode"] == "PRODUCTION"
        assert caps["POINTER"]["lifecycle_state"] == "READY"
        assert caps["POINTER"]["status"] in {"HEALTHY", "DEGRADED"}

        # Keyboard is active in M1.3 production mode
        assert caps["KEYBOARD"]["adapter_mode"] == "PRODUCTION"
        assert caps["KEYBOARD"]["lifecycle_state"] == "READY"
        assert caps["KEYBOARD"]["status"] in {"HEALTHY", "DEGRADED"}

        # Human takeover is active in M1.4 production mode
        assert caps["HUMAN_TAKEOVER"]["adapter_mode"] == "PRODUCTION"
        assert caps["HUMAN_TAKEOVER"]["lifecycle_state"] == "READY"
        assert caps["HUMAN_TAKEOVER"]["status"] in {"HEALTHY", "DEGRADED"}

        # Workspace remains deferred and fails honestly
        assert caps["WORKSPACE"]["adapter_mode"] == "PRODUCTION"
        assert caps["WORKSPACE"]["lifecycle_state"] == "FAILED"
        assert caps["WORKSPACE"]["status"] == "FAILED"

        # Safety coordinator is active
        assert caps["SAFETY"]["adapter_mode"] == "PRODUCTION"
        assert caps["SAFETY"]["lifecycle_state"] == "READY"
        assert caps["SAFETY"]["status"] == "HEALTHY"
