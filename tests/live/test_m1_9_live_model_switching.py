"""Live Host Environment Tests for Model Selection, Activation, and Switching (Milestone M1.9 Step 3).

Executes genuine host validation against active local runtimes (Ollama daemon on localhost:11434).
Performs live model selection, activation, runtime health verification, and real model switching.
"""

from __future__ import annotations

import logging
import pytest

from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.models.adapters import LocalRuntimeAdapter
from orbit.runtime.models.manager import ModelManager
from orbit.runtime.models.models import (
    CloudAuthStatus,
    CloudProviderKind,
    ModelSelectionStatus,
    ModelSessionStatus,
    ModelStatus,
    ProviderHealthStatus,
)
from orbit.runtime.model_providers.cloud import CloudModelProvider
from orbit.runtime.model_providers.ollama import OllamaProvider

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_live_host_ollama_selection_activation_and_switching():
    """Live host validation against genuine Ollama runtime on localhost:11434."""
    ollama = OllamaProvider(endpoint="http://127.0.0.1:11434", connect_timeout=2.0)
    health = await ollama.health_check()

    if health.status != ProviderHealthStatus.HEALTHY:
        pytest.skip(f"Live Ollama runtime is not healthy/running on host ({health.status.value}): {health.diagnostic_message}")

    event_bus = EventBus()
    manager = ModelManager(providers=[ollama], event_bus=event_bus)

    # Step 1: Discover genuinely installed host models
    disc_result = await manager.discover_models()
    if not disc_result.discovered_models:
        pytest.skip("Ollama is running on host but has zero installed models.")

    installed_models = [m for m in disc_result.discovered_models if m.status in (ModelStatus.READY, ModelStatus.AVAILABLE, ModelStatus.INSTALLED, ModelStatus.DISCOVERED)]
    logger.info("Live host discovered %d Ollama models: %s", len(installed_models), [m.model_id for m in installed_models])

    # Step 2: Select first live model
    model_a_id = installed_models[0].model_id
    sel_res_a = await manager.select_model(model_a_id)
    assert sel_res_a.is_successful is True
    assert sel_res_a.status == ModelSelectionStatus.SELECTED

    # Step 3: Activate first live model (Generation 1)
    act_res_a = await manager.activate_model(model_a_id)
    assert act_res_a.is_successful is True
    assert act_res_a.generation >= 1
    assert manager.is_model_active() is True
    assert manager.get_active_model_id() == model_a_id

    runtime_a = manager.get_active_runtime()
    assert runtime_a is not None
    assert isinstance(runtime_a, LocalRuntimeAdapter)

    # Step 4: If at least 2 models are installed on host, perform genuine model switch
    if len(installed_models) >= 2:
        model_b_id = installed_models[1].model_id
        gen_before = manager.get_active_generation()

        switch_res = await manager.switch_model(model_b_id)
        assert switch_res.is_successful is True
        assert switch_res.switched is True
        assert switch_res.previous_model_id == model_a_id
        assert switch_res.active_model_id == model_b_id
        assert switch_res.generation == gen_before + 1
        assert manager.get_active_model_id() == model_b_id

        # Verify active runtime updated
        runtime_b = manager.get_active_runtime()
        assert runtime_b is not None
        assert runtime_b.model_id == model_b_id
        logger.info("Successfully performed live host switch from %s to %s (Gen %d -> %d)", model_a_id, model_b_id, gen_before, switch_res.generation)
    else:
        logger.info("Only 1 model installed on host (%s); skipping 2nd model switch (INSUFFICIENT_LIVE_MODELS_FOR_SWITCH_VALIDATION)", model_a_id)

    # Cleanup
    await manager.deactivate_active_model()
    await manager.shutdown()


@pytest.mark.asyncio
async def test_live_cloud_provider_unconfigured_honest_status():
    """Verify live cloud providers honestly report NOT_CONFIGURED without crashing or leaking secrets."""
    cloud_openai = CloudModelProvider(cloud_kind=CloudProviderKind.OPENAI, api_key=None)
    cloud_anthropic = CloudModelProvider(cloud_kind=CloudProviderKind.ANTHROPIC, api_key=None)
    cloud_gemini = CloudModelProvider(cloud_kind=CloudProviderKind.GEMINI, api_key=None)

    assert cloud_openai.auth_status == CloudAuthStatus.NOT_CONFIGURED
    assert cloud_anthropic.auth_status == CloudAuthStatus.NOT_CONFIGURED
    assert cloud_gemini.auth_status == CloudAuthStatus.NOT_CONFIGURED

    health = await cloud_openai.health_check()
    assert health.status == ProviderHealthStatus.UNAVAILABLE
    assert "not configured" in (health.diagnostic_message or "").lower()
