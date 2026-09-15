import asyncio
import ctypes
from ctypes import wintypes
import subprocess
import time
import sys

sys.path.insert(0, 'src')
from orbit.runtime.perception.windows import Win32WindowObserver

# Do not force SetThreadDesktop("Default")
Win32WindowObserver._ensure_desktop_attached = lambda self: None

# 1. Clean and launch
subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
time.sleep(1)

print("1. Launching Notepad...")
subprocess.run("cmd /c start notepad.exe", shell=True)
time.sleep(2)

# 2. Observe
obs = Win32WindowObserver()
fg, wins = obs.observe_windows()
print(f"2. Observation: FG={fg.title if fg else None} (HWND={fg.hwnd if fg else None})")

# 3. Focus and Type
user32 = ctypes.windll.user32
if fg:
    user32.SetForegroundWindow(fg.hwnd)
time.sleep(0.5)

text_to_type = "ORBIT Vision Test 123"
print(f"3. Typing {text_to_type!r}...")
for ch in text_to_type:
    vk = user32.VkKeyScanW(ord(ch))
    if vk != -1:
        shift = (vk >> 8) & 1
        code = vk & 0xFF
        if shift:
            user32.keybd_event(0x10, 0, 0, 0)
        user32.keybd_event(code, 0, 0, 0)
        user32.keybd_event(code, 0, 2, 0)
        if shift:
            user32.keybd_event(0x10, 0, 2, 0)
    time.sleep(0.02)

time.sleep(1)

# 4. Read text via Ctrl+A, Ctrl+C to verify clipboard
print("4. Selecting all and copying to clipboard...")
# Ctrl down
user32.keybd_event(0x11, 0, 0, 0)
# 'A'
user32.keybd_event(ord('A'), 0, 0, 0)
user32.keybd_event(ord('A'), 0, 2, 0)
# 'C'
user32.keybd_event(ord('C'), 0, 0, 0)
user32.keybd_event(ord('C'), 0, 2, 0)
# Ctrl up
user32.keybd_event(0x11, 0, 2, 0)
time.sleep(0.5)

# Read clipboard
import tkinter as tk
try:
    r = tk.Tk()
    r.withdraw()
    cb_text = r.clipboard_get()
    print(f"5. Clipboard content: {cb_text!r}")
    r.destroy()
except Exception as ex:
    print(f"5. Clipboard notice: {ex}")

# Also check Window Title (Windows 11 Notepad updates title to "*Untitled - Notepad" when edited)
fg2, _ = obs.observe_windows()
print(f"6. Post-typing Window Title: {fg2.title if fg2 else None}")

subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
