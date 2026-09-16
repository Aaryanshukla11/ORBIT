import asyncio
import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import time

sys.path.insert(0, "src")
from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.runtime.perception.windows import Win32WindowObserver

# Clean and launch
subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
time.sleep(1)

# Clean tabstate
local_state = os.path.expandvars(r"%LOCALAPPDATA%\Packages\Microsoft.WindowsNotepad_8wekyb3d8bbwe\LocalState")
for sub_dir in ["TabState", "WindowState"]:
    p = os.path.join(local_state, sub_dir)
    if os.path.isdir(p):
        for f in os.listdir(p):
            try: os.remove(os.path.join(p, f))
            except Exception: pass

subprocess.Popen("cmd /c start notepad.exe", shell=True)
time.sleep(2)

obs = Win32WindowObserver()
fg, wins = obs.observe_windows()
print(f"Foreground: {fg.title if fg else None} (HWND: {fg.hwnd if fg else None})")

user32 = ctypes.windll.user32
if fg:
    user32.SetForegroundWindow(fg.hwnd)
time.sleep(0.5)

# Now let's test typing via agent_loop's exact fallback path:
text = "ORBIT Vision Test 123"
print(f"Testing direct typing of {text!r}...")

for ch in text:
    if ch == "\n":
        user32.keybd_event(0x0D, 0, 0, 0)
        user32.keybd_event(0x0D, 0, 2, 0)
    else:
        vk = user32.VkKeyScanW(ord(ch))
        if vk != -1:
            shift = (vk >> 8) & 1
            code = vk & 0xFF
            print(f"  Char {ch!r}: vk=0x{vk:04X}, shift={shift}, code=0x{code:02X}")
            if shift:
                user32.keybd_event(0x10, 0, 0, 0)
            user32.keybd_event(code, 0, 0, 0)
            user32.keybd_event(code, 0, 2, 0)
            if shift:
                user32.keybd_event(0x10, 0, 2, 0)
    time.sleep(0.02)

time.sleep(2)

fg2, _ = obs.observe_windows()
print(f"Notepad Title after typing: {fg2.title if fg2 else None}")

subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
