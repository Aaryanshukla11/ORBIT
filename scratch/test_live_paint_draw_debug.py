import asyncio
import os
import subprocess
import sys
import time
from PIL import Image

sys.path.insert(0, os.path.abspath("src"))

from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.runtime.environment.drawing_provider import CanvasDrawingProvider
from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType
from orbit.runtime.cognitive.primitive_execution_controller import PrimitiveExecutionController

async def test_paint():
    subprocess.run(["taskkill", "/F", "/IM", "mspaint.exe"], capture_output=True)
    time.sleep(1.0)
    subprocess.Popen(["mspaint.exe"])
    time.sleep(2.5)

    registry = create_capability_registry(config=RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION))
    await registry.initialize_all()
    pointer = registry.get_optional(CapabilityType.POINTER)
    obs = registry.get_optional(CapabilityType.OBSERVATION)
    keyboard = registry.get_optional(CapabilityType.KEYBOARD)
    workspace = registry.get_optional(CapabilityType.WORKSPACE)

    from PIL import ImageGrab
    pre_img = ImageGrab.grab()
    pre_img.save("scratch/pre_draw.png")

    # Execute DRAW_STROKES
    provider = CanvasDrawingProvider(pointer=pointer)
    draw_act = AbstractAction(
        action_type=AbstractActionType.DRAW_STROKES,
        parameters={"shape": "circle", "canvas_rect": [300, 250, 600, 400]}
    )
    res = await provider.execute(draw_act)
    print("Draw result:", res.success, res.output, res.error)

    # Capture post-draw screenshot
    post_img = ImageGrab.grab()
    post_img.save("scratch/post_draw.png")

    # Check pixel difference between pre and post
    import numpy as np
    diff = np.abs(np.array(post_img).astype(int) - np.array(pre_img).astype(int))
    diff_pixels = np.sum(diff > 20)
    print("Different pixels on screen after draw:", diff_pixels)

if __name__ == "__main__":
    asyncio.run(test_paint())
