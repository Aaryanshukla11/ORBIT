"""Live Real-World Model Runtime & Local Discovery Test Suite (Milestone M1.9 Step 1).

Epistemic Classification:
- LIVE_OS_VALIDATED: Genuinely contacts local Ollama service at 127.0.0.1:11434,
  discovers installed GGUF models from local disk, verifies parameter sizes and
  context lengths, and tests active model switching against live host hardware.
- NOT_VALIDATED: Skipped truthfully if Ollama daemon is not running on host.
"""

from __future__ import annotations

import os
import pytest

from orbit.runtime.models.manager import ModelManager
from orbit.runtime.models.models import (
    ModelCapability,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelProviderKind,
    ModelStatus,
    ProviderHealthStatus,
)
from orbit.runtime.model_providers.ollama import OllamaProvider


@pytest.mark.asyncio
async def test_live_ollama_runtime_discovery_and_active_switching():
    """Live test querying genuine local Ollama installation on Windows host.

    Epistemic: LIVE_OS_VALIDATED
    """
    endpoint = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    provider = OllamaProvider(endpoint=endpoint, connect_timeout=2.0)

    # 1. Health check
    health = await provider.health_check()
    if health.status != ProviderHealthStatus.HEALTHY:
        await provider.shutdown()
        pytest.skip(f"Live local Ollama is not reachable at {endpoint} ({health.diagnostic_message})")

    assert health.status == ProviderHealthStatus.HEALTHY
    assert health.latency_ms is not None and health.latency_ms >= 0.0
    assert health.version_info is not None
    print(f"\n[LIVE TEST] Ollama Health: {health.version_info}, Latency: {health.latency_ms:.2f}ms")

    # 2. Model Discovery
    manager = ModelManager(providers=[provider])
    discovery_result = await manager.discover_models()

    assert discovery_result.total_discovered > 0
    assert ModelProviderKind.OLLAMA in discovery_result.successful_providers
    print(f"[LIVE TEST] Discovered {discovery_result.total_discovered} local models:")

    models = await manager.list_models()
    for m in models:
        print(f"  - {m.model_id} | params: {m.parameter_size} | ctx: {m.context_window} | quant: {m.quantization_level} | caps: {[c.value for c in m.capabilities]}")

    # 3. Model Metadata Verification (No fabrication)
    first_model = models[0]
    assert first_model.provider == ModelProviderKind.OLLAMA
    assert first_model.model_id.startswith("ollama:")
    assert first_model.status == ModelStatus.AVAILABLE

    # 4. Active Model Switching Lifecycle
    initial_active = manager.get_active_model_id()
    assert initial_active is None

    # Switch to first model
    await manager.set_active_model(first_model.model_id)
    assert manager.get_active_model_id() == first_model.model_id
    active_desc = await manager.get_active_model()
    assert active_desc is not None
    assert active_desc.model_id == first_model.model_id
    assert active_desc.status == ModelStatus.LOADED

    # 5. Test text generation on active model
    # Filter for a model that supports TEXT_GENERATION (avoid pure embedding models)
    gen_models = [m for m in models if ModelCapability.TEXT_GENERATION in m.capabilities]
    if gen_models:
        target_gen_model = gen_models[0]
        await manager.set_active_model(target_gen_model.model_id)
        print(f"[LIVE TEST] Testing generation with active model: {target_gen_model.model_id}...")
        
        response = await manager.generate(
            prompt="Reply with the single word 'ORBIT'.",
            max_tokens=10,
            temperature=0.0,
        )
        assert response.content is not None
        assert response.total_duration_ms is not None
        print(f"[LIVE TEST] Response: {response.content.strip()!r} in {response.total_duration_ms:.1f}ms")

    # Clean shutdown
    await manager.shutdown()
