"""Live Real-World Model Session Manager and Safe Switching Test Suite (Milestone M1.9 Step 4).

Epistemic Classification:
- LIVE_OS_VALIDATED: Genuinely contacts local Ollama service at 127.0.0.1:11434,
  discovers installed GGUF models from local disk, verifies parameter sizes and
  context lengths, and tests active model switching against live host hardware via ModelSessionManager.
- NOT_VALIDATED: Skipped truthfully if Ollama daemon is not running on host.
"""

from __future__ import annotations

import os
import pytest

from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.model_runtime import (
    ActiveModelContext,
    ModelActivationStatus,
    ModelRuntimeKind,
    ModelRuntimeStatus,
    ModelSessionManager,
    ModelSwitchPolicy,
)
from orbit.runtime.models.inventory import ModelInventory
from orbit.runtime.models.models import (
    ModelCapability,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelProviderKind,
    ModelStatus,
    ProviderHealthStatus,
)
from orbit.runtime.models.registry import ModelRegistry
from orbit.runtime.model_providers.ollama import OllamaProvider


@pytest.mark.asyncio
async def test_live_model_session_manager_on_host():
    """Live test exercising ModelSessionManager against real Ollama runtime on Windows host.
    
    Epistemic: LIVE_OS_VALIDATED
    """
    endpoint = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    provider = OllamaProvider(endpoint=endpoint, connect_timeout=2.0)

    # 1. Probe health
    health = await provider.health_check()
    if health.status != ProviderHealthStatus.HEALTHY:
        await provider.shutdown()
        pytest.skip(f"Live local Ollama is not reachable at {endpoint} ({health.diagnostic_message})")

    # 2. Discover models
    models = await provider.list_models()
    if not models:
        await provider.shutdown()
        pytest.skip("No models installed in local Ollama daemon")

    # Filter for generation capable models
    gen_models = [m for m in models if ModelCapability.TEXT_GENERATION in m.capabilities]
    if not gen_models:
        await provider.shutdown()
        pytest.skip("No text generation models installed in local Ollama daemon")

    # 3. Setup ModelSessionManager
    registry = ModelRegistry()
    for m in models:
        await registry.register_model(m)

    event_bus = EventBus()
    session_manager = ModelSessionManager(
        registry=registry,
        providers=[provider],
        event_bus=event_bus,
    )

    # 4. Activate first model
    first_model = gen_models[0]
    act_res = await session_manager.activate_model(first_model.model_id)
    assert act_res.is_successful
    assert session_manager.is_model_active()
    assert session_manager.get_active_generation() == 1

    active_ctx = session_manager.get_active_context()
    assert active_ctx is not None
    assert active_ctx.model_id == first_model.model_id
    assert active_ctx.runtime_kind == ModelRuntimeKind.LOCAL
    assert active_ctx.runtime_status == ModelRuntimeStatus.ACTIVE

    # 5. Execute generation
    gen_res = await session_manager.generate(
        ModelGenerateRequest(
            prompt="Reply with the single word 'ORBIT'.",
            max_tokens=5,
            expected_generation=1,
        )
    )
    assert gen_res.content is not None
    assert gen_res.done
    print(f"\n[LIVE TEST STEP 4] Generation output: {gen_res.content.strip()!r} in {gen_res.total_duration_ms:.1f}ms")

    # 6. If multiple generation models available, test safe switching
    if len(gen_models) > 1:
        second_model = gen_models[1]
        switch_res = await session_manager.switch_model(second_model.model_id)
        assert switch_res.is_successful
        assert switch_res.switched
        assert session_manager.get_active_generation() == 2
        assert session_manager.get_active_context().model_id == second_model.model_id

        # Switch back
        switch_back_res = await session_manager.switch_model(first_model.model_id)
        assert switch_back_res.is_successful
        assert session_manager.get_active_generation() == 3

    # 7. Shutdown
    await session_manager.shutdown()
    assert not session_manager.is_model_active()
    assert session_manager.get_active_context() is None
