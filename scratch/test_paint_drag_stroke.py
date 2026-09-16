import asyncio
import os
import sys
import time
import ctypes

sys.path.insert(0, os.path.abspath("src"))

from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.runtime.environment.drawing_provider import CanvasDrawingProvider
from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType

async def test_drawing():
    registry = create_capability_registry(config=RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION))
    await registry.initialize_all()
    pointer = registry.get_optional(CapabilityType.POINTER)
    provider = CanvasDrawingProvider(pointer=pointer)

    # Launch Paint if not open
    import subprocess
    subprocess.Popen(["mspaint.exe"])
    time.sleep(2.0)

    # Draw circle
    act = AbstractAction(
        action_type=AbstractActionType.DRAW_STROKES,
        parameters={"shape": "circle", "color": "red"}
    )
    res = await provider.execute(act)
    print("Drawing result:", res.success, res.output, res.error)

if __name__ == "__main__":
    asyncio.run(test_drawing())
