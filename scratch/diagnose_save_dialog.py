import asyncio
import os
import sys
import ctypes
import pyautogui

sys.path.insert(0, os.path.abspath("src"))

from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.runtime.perception.windows import Win32WindowObserver

async def main():
    observer = Win32WindowObserver()
    registry = create_capability_registry(config=RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION))
    await registry.initialize_all()

    workspace_cap = registry.get_optional(CapabilityType.WORKSPACE)
    keyboard_cap = registry.get_optional(CapabilityType.KEYBOARD)

    # 1. Launch Paint
    await workspace_cap.launch_process("mspaint")
    await asyncio.sleep(2.0)

    fg, visible = observer.observe_windows()
    print("FG before Save:", fg.title if fg else None, "HWND:", fg.hwnd if fg else None)

    # 2. Focus paint
    if fg and fg.hwnd:
        ctypes.windll.user32.SetForegroundWindow(fg.hwnd)
        await asyncio.sleep(0.5)

    # 3. Send Ctrl+S
    print("Sending Ctrl+S via keyboard_cap.press_shortcut...")
    await keyboard_cap.press_shortcut("ctrl+s")
    await asyncio.sleep(1.5)

    fg, visible = observer.observe_windows()
    print("FG after Ctrl+S:", fg.title if fg else None, "Class:", fg.window_class if fg else None, "HWND:", fg.hwnd if fg else None)
    for w in visible:
        print("  Visible window:", w.title, "(Class:", w.window_class, ")")

    target_path = os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "Desktop", "test.png")
    print(f"Typing target_path: {target_path}")
    await keyboard_cap.type_text(target_path)
    await asyncio.sleep(0.5)

    print("Sending Enter...")
    await keyboard_cap.press_key("enter")
    await keyboard_cap.release_key("enter")
    await asyncio.sleep(1.5)

    print("File exists on disk:", os.path.exists(target_path))

if __name__ == "__main__":
    asyncio.run(main())
