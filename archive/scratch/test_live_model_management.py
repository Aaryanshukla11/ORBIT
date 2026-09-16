"""Live Verification for Model Provider Architecture and Model Switching in ORBIT V1 MVP."""

import asyncio
import sys
import logging

sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\src")

from orbit.infrastructure.event_bus import EventBus
from orbit.adapters.factory import create_capability_registry
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.contracts.runtime import SystemState

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("live_model_mgmt_test")

async def main():
    print("=" * 70)
    print("ORBIT V1 MVP - MODEL MANAGEMENT ACCEPTANCE TEST")
    print("=" * 70)

    event_bus = EventBus()
    registry = create_capability_registry()
    orchestrator = OrbitOrchestrator(event_bus=event_bus, registry=registry)
    await orchestrator.initialize()

    msm = orchestrator.model_session_manager
    assert msm is not None, "ModelSessionManager must be present on orchestrator"

    # 1. Verify single active model on boot
    active_ctx = msm.get_active_context()
    print(f"\n1. Boot Active Model: {active_ctx.model_id if active_ctx else 'None'}")
    assert active_ctx is not None, "Active model must be initialized"
    assert active_ctx.model_id == "ollama:qwen2.5:latest"
    gen_0 = active_ctx.generation

    # 2. List available models in registry
    models = await msm._registry.list_models()
    print(f"\n2. Available Models ({len(models)} total):")
    for m in models:
        print(f"  - ID: {m.model_id}, Provider: {m.provider.value}, Display: {m.display_name}")
    assert len(models) >= 1, "At least 1 local Ollama model must be registered"

    # 3. Switch to another registered model
    target_model_id = "ollama:llama3.2-vision:latest"
    has_target = any(m.model_id == target_model_id for m in models)
    if not has_target:
        target_model_id = models[0].model_id

    print(f"\n3. Switching model to '{target_model_id}'...")
    switch_res = await msm.switch_model(new_model_id=target_model_id)
    print(f"Switch Result: success={switch_res.is_successful}, status={switch_res.status}, active_model={switch_res.active_model_id}, gen={switch_res.generation}")
    assert switch_res.is_successful, f"Switch failed: {switch_res.diagnostic_message}"
    
    # Verify authoritative state
    active_after = msm.get_active_context()
    assert active_after.model_id == target_model_id
    assert active_after.generation > gen_0
    print("Switch to target model verified.")

    # 4. Attempt invalid switch to non-existent model (Must fail truthfully)
    print("\n4. Testing invalid model switch (should fail truthfully)...")
    invalid_res = await msm.switch_model(new_model_id="ollama:nonexistent_fake_model_9999")
    print(f"Invalid Switch Result: success={invalid_res.is_successful}, failure_reason={invalid_res.failure_reason}, diag={invalid_res.diagnostic_message}")
    assert not invalid_res.is_successful, "Switching to non-existent model must fail"
    assert invalid_res.failure_reason in ("MODEL_NOT_FOUND", "MODEL_UNAVAILABLE", "INITIALIZATION_FAILED")
    
    # Verify rollback: active model is STILL the previous valid model
    active_rollback = msm.get_active_context()
    assert active_rollback.model_id == target_model_id, "Active model must not change on switch failure"
    print("Atomic rollback and truthful failure verified.")

    # 5. Switch back to primary default
    print("\n5. Switching back to primary 'ollama:qwen2.5:latest'...")
    res_back = await msm.switch_model(new_model_id="ollama:qwen2.5:latest")
    assert res_back.is_successful
    print(f"Active model restored to: {msm.get_active_context().model_id}")

    await orchestrator.shutdown()
    print("\nALL MODEL MANAGEMENT TESTS PASSED.")

if __name__ == "__main__":
    asyncio.run(main())
