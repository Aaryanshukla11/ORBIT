import asyncio
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath("src"))

from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.runtime.perception.engine import DesktopPerceptionEngine

async def inspect_paint():
    subprocess.run(["taskkill", "/F", "/IM", "mspaint.exe"], capture_output=True)
    time.sleep(1.0)
    subprocess.Popen(["mspaint.exe"])
    time.sleep(2.0)

    registry = create_capability_registry(config=RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION))
    await registry.initialize_all()
    obs_cap = registry.get_optional(CapabilityType.OBSERVATION)
    
    engine = DesktopPerceptionEngine(observation_capability=obs_cap)
    frame = await obs_cap.capture_screen()
    perception = await engine.perceive_desktop(frame)

    print("\n--- PAINT INTERACTIVE CONTROLS ---")
    for elem in perception.interactive_elements:
        if "paint" in elem.name.lower() or "brush" in elem.name.lower() or "canvas" in elem.name.lower() or "pencil" in elem.name.lower() or "tool" in elem.name.lower():
            print(f"Name: {elem.name!r}, Role: {elem.role!r}, Bounds: {elem.bounds}")

    print("\n--- ALL ROLES DETECTED ---")
    for elem in perception.interactive_elements[:30]:
        print(f"Name: {elem.name!r}, Role: {elem.role!r}, Bounds: {elem.bounds}")

if __name__ == "__main__":
    asyncio.run(inspect_paint())
