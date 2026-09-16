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
    obs = await engine.observe()

    print("\n--- UIA ELEMENTS ---")
    for elem in obs.uia_elements[:25]:
        print(f"Name: {elem.name!r}, Type: {elem.control_type!r}, Bounds: {elem.bounding_box}")

    print("\n--- OCR TOKENS ---")
    for tok in obs.ocr_tokens[:25]:
        print(f"Text: {tok.text!r}, Bounds: {tok.bounding_box}")

if __name__ == "__main__":
    asyncio.run(inspect_paint())
