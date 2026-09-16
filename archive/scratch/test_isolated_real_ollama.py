"""Minimal isolated real Ollama model activation & inference verification script.

Follows strict isolation rules:
- Does NOT launch Notepad.
- Confirms genuine Ollama daemon health.
- Confirms qwen2.5:latest is installed.
- Activates exact model through ModelSessionManager with explicit timeout budget.
- Verifies LOCAL classification.
- Performs one genuine model chat/generation inference request.
- Prints the actual model response and execution latency.
"""

import asyncio
import sys
import time

from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.model_providers.ollama import OllamaProvider
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.model_runtime.contracts import (
    ModelActivationRequest,
    ModelRuntimeKind,
)
from orbit.runtime.models.models import (
    ModelChatMessage,
    ModelChatRequest,
    ModelProviderKind,
    ProviderHealthStatus,
)


async def main():
    print("=" * 80)
    print("ISOLATED REAL OLLAMA ACTIVATION & INFERENCE VERIFICATION")
    print("=" * 80)

    # 1. Confirm Ollama health
    provider = OllamaProvider(endpoint="http://127.0.0.1:11434")
    print("\n[STEP 1: OLLAMA HEALTH PROBE]")
    health = await provider.health_check()
    print(f"  Endpoint:           {provider.endpoint}")
    print(f"  Status:             {health.status.value}")
    print(f"  Latency:            {health.latency_ms:.1f}ms")
    print(f"  Diagnostic Message: {health.diagnostic_message}")
    if health.status != ProviderHealthStatus.HEALTHY:
        print("[-] FAILED: Ollama daemon is unhealthy. Aborting isolated test.")
        sys.exit(1)
    print("[+] Ollama health probe PASSED")

    # 2. Confirm qwen2.5:latest exists
    print("\n[STEP 2: MODEL DISCOVERY]")
    models = await provider.discover_models()
    print(f"  Total models discovered: {len(models)}")
    target_desc = None
    for m in models:
        print(f"    - {m.model_id} (provider_model: {m.provider_model_name}, size: {m.parameter_size or 'N/A'})")
        if m.provider_model_name == "qwen2.5:latest":
            target_desc = m

    if target_desc is None:
        print("[-] FAILED: qwen2.5:latest not found in Ollama inventory. Aborting.")
        sys.exit(1)
    print(f"[+] Target model confirmed: {target_desc.model_id}")

    # 3. Setup ModelSessionManager
    print("\n[STEP 3: MODEL SESSION MANAGER SETUP]")
    event_bus = EventBus()
    session_mgr = ModelSessionManager(
        providers=[provider],
        event_bus=event_bus,
    )
    await session_mgr.register_descriptor(target_desc)
    print(f"[+] Model descriptor registered in session manager: {target_desc.model_id}")

    # 4. Activate model through ModelSessionManager with 60s timeout budget
    print("\n[STEP 4: ACTIVATE MODEL THROUGH SESSION MANAGER]")
    t_act_start = time.perf_counter()
    activation_req = ModelActivationRequest(
        model_id=target_desc.model_id,
        timeout_seconds=60.0,
        preload_weights=True,
    )
    act_result = await session_mgr.activate_model(activation_req)
    act_duration = time.perf_counter() - t_act_start

    print(f"  Activation Success:    {act_result.is_successful}")
    print(f"  Status:                {act_result.status.value}")
    print(f"  Duration:              {act_duration:.2f}s ({act_result.duration_ms:.1f}ms)")
    if act_result.diagnostic_message:
        print(f"  Diagnostic Message:    {act_result.diagnostic_message}")
    if act_result.failure_reason:
        print(f"  Failure Reason:        {act_result.failure_reason}")

    if not act_result.is_successful:
        print("[-] FAILED: Model activation failed. Aborting.")
        sys.exit(1)
    print("[+] Model activation PASSED")

    # 5. Verify LOCAL classification
    print("\n[STEP 5: VERIFY LOCAL/CLOUD CLASSIFICATION]")
    active_runtime = session_mgr.get_active_runtime()
    active_ctx = session_mgr.get_active_context()
    if active_runtime is None or active_ctx is None:
        print("[-] FAILED: Active runtime or active context is None.")
        sys.exit(1)

    prov_str = active_ctx.provider.value if hasattr(active_ctx.provider, "value") else str(active_ctx.provider)
    is_local = (
        prov_str.upper() in ("OLLAMA", "LM_STUDIO", "LOCAL_FILE")
        or "LOCAL" in prov_str.upper()
        or active_runtime.runtime_kind == ModelRuntimeKind.LOCAL
    )
    print(f"  Active Model ID:       {active_ctx.model_id}")
    print(f"  Active Provider:       {prov_str}")
    print(f"  Active Runtime Kind:   {active_runtime.runtime_kind.value}")
    print(f"  Classification:        {'LOCAL' if is_local else 'CLOUD'}")

    if not is_local or active_runtime.runtime_kind != ModelRuntimeKind.LOCAL:
        print("[-] FAILED: Ollama runtime was incorrectly classified as CLOUD.")
        sys.exit(1)
    print("[+] LOCAL classification PASSED")

    # 6. Execute one real chat / generation request
    print("\n[STEP 6: REAL INFERENCE REQUEST]")
    test_prompt = "Reply with exactly: 'ORBIT LIVE COGNITIVE RUNTIME READY 2026' and nothing else."
    chat_req = ModelChatRequest(
        messages=[
            ModelChatMessage(role="user", content=test_prompt),
        ],
        temperature=0.0,
        max_tokens=64,
    )
    t_inf_start = time.perf_counter()
    resp = await active_runtime.chat(chat_req)
    inf_duration = time.perf_counter() - t_inf_start

    print(f"  Inference Duration:    {inf_duration:.2f}s ({resp.total_duration_ms:.1f}ms)")
    print(f"  Done:                  {resp.done}")
    print(f"  Prompt Tokens:         {resp.prompt_tokens}")
    print(f"  Completion Tokens:     {resp.completion_tokens}")
    print("-" * 50)
    print("ACTUAL MODEL RESPONSE:")
    print(resp.content)
    print("-" * 50)

    if not resp.content or not resp.content.strip():
        print("[-] FAILED: Model returned empty content.")
        sys.exit(1)
    print("[+] Real inference PASSED")

    # Cleanup
    await session_mgr.shutdown()
    await provider.shutdown()

    print("\n" + "=" * 80)
    print("ALL ISOLATED REAL OLLAMA VERIFICATION CHECKS COMPLETED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
