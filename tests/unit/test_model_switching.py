"""Unit tests for Model Switching state machine and Safe Rollback (Milestone M1.9 Step 4)."""

import pytest
import pytest_asyncio

from orbit.contracts.events import EventType, RuntimeEvent
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.model_runtime.contracts import (
    ActiveModelContext,
    ModelActivationStatus,
    ModelRuntimeKind,
    ModelRuntimeStatus,
    ModelSwitchPolicy,
    ModelSwitchResult,
)
from orbit.runtime.model_runtime.providers.mock import MockModelRuntimeAdapter
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models.models import (
    ModelCapability,
    ModelDescriptor,
    ModelProviderKind,
)
from orbit.runtime.models.registry import ModelRegistry


@pytest.fixture
def test_registry() -> ModelRegistry:
    reg = ModelRegistry()
    desc_a = ModelDescriptor(
        model_id="mock:model-a",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="mock-model-a",
        display_name="Mock Model A",
        capabilities={ModelCapability.TEXT_GENERATION},
    )
    desc_b = ModelDescriptor(
        model_id="mock:model-b",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="mock-model-b",
        display_name="Mock Model B",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.VISION},
    )
    desc_failing = ModelDescriptor(
        model_id="mock:model-failing",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="mock-failing",
        display_name="Failing Model",
    )
    reg._models[desc_a.model_id] = desc_a
    reg._models[desc_b.model_id] = desc_b
    reg._models[desc_failing.model_id] = desc_failing
    return reg


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.mark.asyncio
async def test_successful_model_switch(test_registry: ModelRegistry, event_bus: EventBus):
    manager = ModelSessionManager(registry=test_registry, event_bus=event_bus)
    emitted_events = []

    async def listener(evt: RuntimeEvent):
        emitted_events.append(evt)

    event_bus.subscribe(None, listener)

    # 1. Activate Model A
    act_res = await manager.activate_model("mock:model-a")
    assert act_res.is_successful
    assert manager.get_active_generation() == 1
    assert manager.get_active_model().model_id == "mock:model-a"

    # 2. Switch to Model B
    switch_res = await manager.switch_model("mock:model-b")
    assert switch_res.is_successful
    assert switch_res.switched
    assert switch_res.previous_model_id == "mock:model-a"
    assert switch_res.active_model_id == "mock:model-b"
    assert switch_res.generation == 2
    assert manager.get_active_generation() == 2
    assert manager.get_active_model().model_id == "mock:model-b"

    # Check events
    types = [e.event_type for e in emitted_events]
    assert EventType.MODEL_SWITCH_REQUESTED in types
    assert EventType.MODEL_SWITCH_STARTED in types
    assert EventType.MODEL_SWITCH_SUCCEEDED in types
    assert EventType.MODEL_SWITCHED in types


@pytest.mark.asyncio
async def test_safe_rollback_on_switch_init_failure(test_registry: ModelRegistry, event_bus: EventBus):
    manager = ModelSessionManager(registry=test_registry, event_bus=event_bus)
    emitted_events = []

    async def listener(evt: RuntimeEvent):
        emitted_events.append(evt)

    event_bus.subscribe(None, listener)

    # 1. Activate Model A
    await manager.activate_model("mock:model-a")
    assert manager.get_active_generation() == 1
    assert manager.get_active_model().model_id == "mock:model-a"

    # 2. Create custom runtime factory that fails on failing model
    orig_create = manager._factory.create_runtime

    def failing_factory(descriptor, **kwargs):
        if descriptor.model_id == "mock:model-failing":
            return MockModelRuntimeAdapter(descriptor=descriptor, simulate_init_failure=True)
        return orig_create(descriptor, **kwargs)

    manager._factory.create_runtime = failing_factory

    # 3. Switch to failing model
    switch_res = await manager.switch_model("mock:model-failing")
    assert not switch_res.is_successful
    assert not switch_res.switched
    assert switch_res.status == ModelActivationStatus.INITIALIZATION_FAILED

    # INVARIANT VERIFICATION: Model A remains intact, generation remains 1
    assert manager.is_model_active()
    assert manager.get_active_model().model_id == "mock:model-a"
    assert manager.get_active_generation() == 1

    # Check failure event emitted
    types = [e.event_type for e in emitted_events]
    assert EventType.MODEL_SWITCH_FAILED in types


@pytest.mark.asyncio
async def test_active_task_conflict_rejection(test_registry: ModelRegistry, event_bus: EventBus):
    is_task_running = True
    manager = ModelSessionManager(
        registry=test_registry,
        event_bus=event_bus,
        is_task_executing_fn=lambda: is_task_running,
    )

    # Initially activate with task running = False
    is_task_running = False
    await manager.activate_model("mock:model-a")
    assert manager.get_active_generation() == 1

    # Now task starts running
    is_task_running = True

    # Attempt switch with default policy REJECT_DURING_ACTIVE_TASK
    switch_res = await manager.switch_model(
        "mock:model-b",
        policy=ModelSwitchPolicy.REJECT_DURING_ACTIVE_TASK,
    )
    assert not switch_res.is_successful
    assert switch_res.status == ModelActivationStatus.ACTIVE_TASK_CONFLICT
    assert switch_res.failure_reason == "ACTIVE_TASK_CONFLICT"

    # Invariant: Model A remains active
    assert manager.get_active_model().model_id == "mock:model-a"
    assert manager.get_active_generation() == 1


@pytest.mark.asyncio
async def test_cancel_and_switch_policy(test_registry: ModelRegistry, event_bus: EventBus):
    is_task_running = True
    cancelled = False

    def cancel_task():
        nonlocal is_task_running, cancelled
        cancelled = True
        is_task_running = False

    manager = ModelSessionManager(
        registry=test_registry,
        event_bus=event_bus,
        is_task_executing_fn=lambda: is_task_running,
        task_cancel_fn=cancel_task,
    )

    # Activate Model A initially
    is_task_running = False
    await manager.activate_model("mock:model-a")
    assert manager.get_active_generation() == 1

    # Task runs
    is_task_running = True

    # Switch with CANCEL_AND_SWITCH policy
    switch_res = await manager.switch_model(
        "mock:model-b",
        policy=ModelSwitchPolicy.CANCEL_AND_SWITCH,
    )
    assert switch_res.is_successful
    assert cancelled
    assert manager.get_active_model().model_id == "mock:model-b"
    assert manager.get_active_generation() == 2
