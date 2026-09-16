"""Pytest fixtures and configuration for ORBIT tests."""

from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator
import pytest
from httpx import ASGITransport, AsyncClient

# Default to enabled in test harness to preserve existing takeover tests
os.environ.setdefault("ORBIT_HUMAN_TAKEOVER_ENABLED", "true")


from orbit.adapters.mocks import (
    MockHumanTakeoverAdapter,
    MockKeyboardAdapter,
    MockObservationAdapter,
    MockPointerAdapter,
    MockSafetyCoordinator,
    MockWorkspaceAdapter,
)
from orbit.contracts.sessions import DisconnectionPolicy
from orbit.gateway.app import create_app
from orbit.gateway.session_manager import SessionManager
from orbit.gateway.websocket_manager import WebSocketManager
from orbit.infrastructure.clock import FrozenClock, SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def mock_observation() -> MockObservationAdapter:
    return MockObservationAdapter()


@pytest.fixture
def mock_pointer() -> MockPointerAdapter:
    return MockPointerAdapter()


@pytest.fixture
def mock_keyboard() -> MockKeyboardAdapter:
    return MockKeyboardAdapter()


@pytest.fixture
def mock_takeover() -> MockHumanTakeoverAdapter:
    return MockHumanTakeoverAdapter()


@pytest.fixture
def mock_workspace() -> MockWorkspaceAdapter:
    return MockWorkspaceAdapter()


@pytest.fixture
def mock_safety() -> MockSafetyCoordinator:
    return MockSafetyCoordinator()


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
def session_manager() -> SessionManager:
    return SessionManager()


@pytest.fixture
def capability_registry(
    mock_observation: MockObservationAdapter,
    mock_pointer: MockPointerAdapter,
    mock_keyboard: MockKeyboardAdapter,
    mock_takeover: MockHumanTakeoverAdapter,
    mock_workspace: MockWorkspaceAdapter,
    mock_safety: MockSafetyCoordinator,
) -> CapabilityRegistry:
    from orbit.adapters.registry import CapabilityRegistry
    from orbit.contracts.capabilities import CapabilityType
    reg = CapabilityRegistry()
    reg.register(CapabilityType.OBSERVATION, mock_observation)
    reg.register(CapabilityType.POINTER, mock_pointer)
    reg.register(CapabilityType.KEYBOARD, mock_keyboard)
    reg.register(CapabilityType.HUMAN_TAKEOVER, mock_takeover)
    reg.register(CapabilityType.WORKSPACE, mock_workspace)
    reg.register(CapabilityType.SAFETY, mock_safety)
    return reg


@pytest.fixture
def orchestrator(
    event_bus: EventBus,
    capability_registry: CapabilityRegistry,
) -> OrbitOrchestrator:
    return OrbitOrchestrator(
        event_bus=event_bus,
        registry=capability_registry,
        clock=SystemClock(),
    )


@pytest.fixture
def app(orchestrator: OrbitOrchestrator, session_manager: SessionManager, event_bus: EventBus):
    return create_app(
        orchestrator=orchestrator,
        session_manager=session_manager,
        event_bus=event_bus,
    )


@pytest.fixture
async def async_client(app) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
