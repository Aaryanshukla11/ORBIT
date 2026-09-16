import asyncio
import ctypes
import os
import subprocess
import sys
import time
from PIL import Image, ImageGrab
import numpy as np

user32 = ctypes.windll.user32
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

def test_drawing_modes():
    subprocess.run(["taskkill", "/F", "/IM", "mspaint.exe"], capture_output=True)
    time.sleep(1.0)
    subprocess.Popen(["mspaint.exe"])
    time.sleep(2.5)

    # Bring Paint to foreground
    # Find Paint window
    hwnd = user32.FindWindowW(None, "Untitled - Paint")
    if not hwnd:
        hwnd = user32.FindWindowW(None, "Paint")
    if hwnd:
        user32.SetForegroundWindow(hwnd)
        user32.ShowWindow(hwnd, 3) # SW_MAXIMIZE
        time.sleep(1.0)

    # Mode 1: pyautogui drag
    import pyautogui
    pyautogui.FAILSAFE = False
    
    # Click canvas center
    pyautogui.click(600, 400)
    time.sleep(0.5)

    # Drag circle with pyautogui
    import math
    cx, cy, r = 600, 400, 150
    pyautogui.moveTo(cx + r, cy)
    pyautogui.mouseDown(button="left")
    time.sleep(0.1)
    for i in range(1, 31):
        angle = 2 * math.pi * (i / 30.0)
        px = int(cx + r * math.cos(angle))
        py = int(cy + r * math.sin(angle))
        pyautogui.moveTo(px, py, duration=0.02)
    pyautogui.mouseUp(button="left")
    time.sleep(0.5)

    # Save to desktop
    user_profile = os.environ.get("USERPROFILE", "")
    target = os.path.join(user_profile, "OneDrive", "Desktop", "test_ink.png")
    if os.path.exists(target):
        os.remove(target)

    pyautogui.hotkey("ctrl", "s")
    time.sleep(1.5)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.write(target, interval=0.01)
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(1.0)
    pyautogui.hotkey("alt", "y")
    time.sleep(1.5)

    if os.path.exists(target):
        img = Image.open(target)
        arr = np.array(img.convert("RGB"))
        non_white = np.sum(arr < 240)
        print("Saved file size:", os.path.getsize(target))
        print("Non-white pixel count:", non_white)
    else:
        print("File was not saved")

if __name__ == "__main__":
    test_drawing_modes()
