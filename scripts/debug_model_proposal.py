import asyncio
import json
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.cognitive.prompt_builder import MultimodalPromptBuilder
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.cognitive.models import StructuredObjective
from orbit.runtime.models.models import ModelGenerateRequest

async def test_prompt():
    bus = EventBus()
    orch = OrbitOrchestrator(event_bus=bus)
    inv = await orch.refresh_model_inventory(include_runtimes=True, include_cloud=False, include_files=False)
    for d in inv.models:
        await orch.model_session_manager.register_descriptor(d)
    await orch.model_session_manager.activate_model("ollama:qwen2.5:3b")
    
    obs = await orch.agent_loop._observer.observe(None)
    pb = MultimodalPromptBuilder()
    prompt_payload = pb.build_prompt(
        user_goal="Open Notepad and type: ORBIT ASTRA-6 AUTONOMY TEST",
        current_observation=obs,
    )
    
    print("--- SYSTEM PROMPT ---")
    print(prompt_payload["system_prompt"][:300])
    print("--- USER PROMPT ---")
    print(prompt_payload["user_prompt"][:300])
    
    gen_req = ModelGenerateRequest(
        prompt=prompt_payload["user_prompt"],
        system_prompt=prompt_payload["system_prompt"],
        temperature=0.1,
        max_tokens=512,
    )
    resp = await orch.model_session_manager.generate(gen_req)
    print("\n--- RAW MODEL RESPONSE ---")
    print(resp.content)

if __name__ == "__main__":
    asyncio.run(test_prompt())
