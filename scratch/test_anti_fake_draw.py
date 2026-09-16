import asyncio
import hashlib
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

def sha256_file(filepath: str):
    if not os.path.exists(filepath):
        return None
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

async def run_draw_and_save(shape: str, out_name: str):
    user_profile = os.environ.get("USERPROFILE", "")
    target_path = os.path.join(user_profile, "OneDrive", "Desktop", out_name)
    if not os.path.exists(os.path.dirname(target_path)):
        target_path = os.path.join(user_profile, "Desktop", out_name)

    if os.path.exists(target_path):
        os.remove(target_path)

    # Launch Paint fresh
    subprocess.run(["taskkill", "/F", "/IM", "mspaint.exe"], capture_output=True)
    time.sleep(1.0)
    subprocess.Popen(["mspaint.exe"])
    time.sleep(2.0)

    registry = create_capability_registry(config=RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION))
    await registry.initialize_all()
    pointer = registry.get_optional(CapabilityType.POINTER)
    keyboard = registry.get_optional(CapabilityType.KEYBOARD)
    workspace = registry.get_optional(CapabilityType.WORKSPACE)

    # Drawing
    provider = CanvasDrawingProvider(pointer=pointer)
    draw_act = AbstractAction(
        action_type=AbstractActionType.DRAW_STROKES,
        parameters={"shape": shape, "color": "red" if shape == "circle" else "blue"}
    )
    await provider.execute(draw_act)
    time.sleep(1.0)

    # Save
    controller = PrimitiveExecutionController(
        workspace=workspace,
        pointer=pointer,
        keyboard=keyboard,
    )
    save_act = AbstractAction(
        action_type=AbstractActionType.SAVE_FILE,
        parameters={"file_path": target_path, "format": "png"}
    )
    res = await controller._dispatch_save_file(save_act, None)
    print(f"[{shape}] Save result: {res.expected_effect_observed}")
    h = sha256_file(target_path)
    sz = os.path.getsize(target_path) if os.path.exists(target_path) else 0
    print(f"[{shape}] Path: {target_path}, Size: {sz}, SHA256: {h}")
    return h

async def main():
    h_circle = await run_draw_and_save("circle", "test_circle.png")
    h_rect = await run_draw_and_save("rectangle", "test_rect.png")
    print("\n--- COMPARISON ---")
    print("Circle hash:", h_circle)
    print("Rect hash:  ", h_rect)
    print("Different:  ", h_circle != h_rect)

if __name__ == "__main__":
    asyncio.run(main())
