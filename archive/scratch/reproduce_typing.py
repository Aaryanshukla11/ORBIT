import asyncio
import ctypes
import os
import subprocess
import sys
import time

sys.path.insert(0, "src")
from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.runtime.perception.windows import Win32WindowObserver

async def test_typing():
    # 1. Clean and launch Notepad
    subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
    time.sleep(1)
    
    # Clear session restore state
    local_state = os.path.expandvars(r"%LOCALAPPDATA%\Packages\Microsoft.WindowsNotepad_8wekyb3d8bbwe\LocalState")
    for sub_dir in ["TabState", "WindowState"]:
        p = os.path.join(local_state, sub_dir)
        if os.path.isdir(p):
            for f in os.listdir(p):
                try:
                    os.remove(os.path.join(p, f))
                except Exception:
                    pass

    print("Launching Notepad...")
    subprocess.Popen("cmd /c start notepad.exe", shell=True)
    time.sleep(2)
    
    obs = Win32WindowObserver()
    fg, wins = obs.observe_windows()
    print(f"Foreground: {fg.title if fg else None} (HWND: {fg.hwnd if fg else None})")
    if not fg:
        print("Notepad not found!")
        return
        
    registry = create_capability_registry(config=RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION))
    await registry.initialize_all()
    keyboard_cap = registry.get_optional(CapabilityType.KEYBOARD)
    print("Keyboard capability:", type(keyboard_cap))
    
    # Focus Notepad
    user32 = ctypes.windll.user32
    user32.SetForegroundWindow(fg.hwnd)
    time.sleep(0.5)
    
    # Try keyboard_cap.type_text
    test_str = "ORBIT Vision Test 123"
    print(f"Calling keyboard_cap.type_text({test_str!r})...")
    res = await keyboard_cap.type_text(test_str, target_hwnd=fg.hwnd)
    print(f"keyboard_cap.type_text returned: {res}")
    time.sleep(1)
    
    # Read text from Notepad window title / UIA
    fg2, _ = obs.observe_windows()
    print(f"Window title after keyboard_cap typing: {fg2.title if fg2 else None}")
    
    await registry.shutdown_all()
    subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)

if __name__ == "__main__":
    asyncio.run(test_typing())
