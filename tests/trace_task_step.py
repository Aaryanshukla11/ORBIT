import os
import sys
import asyncio
import traceback
import logging

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("prototypes/prototype_d_observation"))

from orbit.adapters.keyboard.adapter import ProductionKeyboardAdapter
from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator

async def main():
    bus = EventBus()
    obs = ProductionObservationAdapter()
    ptr = ProductionPointerAdapter()
    kbd = ProductionKeyboardAdapter()

    orchestrator = OrbitOrchestrator(
        event_bus=bus,
        observation=obs,
        pointer=ptr,
        keyboard=kbd,
    )
    await orchestrator.initialize()
    print("Orchestrator initialized successfully.", flush=True)

    try:
        res = await orchestrator.execute_task("Open Calculator and click 7")
        print(f"Result: success={res.is_success}, status={res.completion_status.value}", flush=True)
    except Exception as ex:
        print("EXCEPTION CAUGHT IN EXECUTE_TASK:", ex, flush=True)
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as ex:
        print("OUTER EXCEPTION:", ex, flush=True)
        traceback.print_exc()
