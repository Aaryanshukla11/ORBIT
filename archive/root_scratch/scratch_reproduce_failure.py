import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from orbit.adapters.registry import CapabilityRegistry
from orbit.contracts.capabilities import CapabilityType
from orbit.infrastructure.event_bus import EventBus
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.keyboard.adapter import ProductionKeyboardAdapter
from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter
from orbit.runtime.orchestrator import OrbitOrchestrator

async def main():
    event_bus = EventBus()
    registry = CapabilityRegistry()
    
    pointer = ProductionPointerAdapter()
    keyboard = ProductionKeyboardAdapter()
    obs = ProductionObservationAdapter()
    workspace = ProductionWorkspaceAdapter()
    
    registry.register(CapabilityType.POINTER, pointer)
    registry.register(CapabilityType.KEYBOARD, keyboard)
    registry.register(CapabilityType.OBSERVATION, obs)
    registry.register(CapabilityType.WORKSPACE, workspace)
    
    orch = OrbitOrchestrator(
        event_bus=event_bus,
        registry=registry,
        auto_activate_models=False,
    )
    
    await orch.initialize()
    print("Orchestrator initialized.")
    
    print("Executing task: 'Open Paint and draw a car'")
    res = await orch.execute_task(goal="Open Paint and draw a car")
    print("Task Result:")
    print("  Status:", res.completion_status)
    print("  Success:", res.is_success)
    print("  Failure reason:", res.failure_reason)
    print("  Failure code:", res.failure_code)
    print("  Completed steps:", res.completed_steps)
    print("  Failed steps:", res.failed_steps)
    print("  Diagnostics:", res.diagnostics)
    
    await orch.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
