import ctypes
import pyautogui
pyautogui.FAILSAFE = False
import os
import subprocess
import time
import hashlib

def sha256_file(filepath: str):
    if not os.path.exists(filepath):
        return None
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

user32 = ctypes.windll.user32
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000

def to_norm(x, y):
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    return int((x * 65535) / (sw - 1)), int((y * 65535) / (sh - 1))

def draw_shape(shape: str):
    subprocess.run(["taskkill", "/F", "/IM", "mspaint.exe"], capture_output=True)
    time.sleep(1.0)
    p = subprocess.Popen(["mspaint.exe"])
    time.sleep(2.0)

    # Click canvas center to focus
    nx, ny = to_norm(500, 400)
    user32.mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, nx, ny, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.02)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.1)

    # Draw shape
    if shape == "circle":
        import math
        user32.mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, *to_norm(500 + 100, 400), 0, 0)
        time.sleep(0.05)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        for i in range(30):
            angle = 2 * math.pi * (i / 29.0)
            px = int(500 + 100 * math.cos(angle))
            py = int(400 + 100 * math.sin(angle))
            user32.mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, *to_norm(px, py), 0, 0)
            time.sleep(0.02)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    else:
        # Rectangle
        user32.mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, *to_norm(400, 300), 0, 0)
        time.sleep(0.05)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        for px, py in [(600, 300), (600, 500), (400, 500), (400, 300)]:
            user32.mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, *to_norm(px, py), 0, 0)
            time.sleep(0.05)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    time.sleep(1.0)
    
    # Save via hotkey
    import pyautogui
    user_profile = os.environ.get("USERPROFILE", "")
    target = os.path.join(user_profile, "OneDrive", "Desktop", f"raw_{shape}.png")
    if os.path.exists(target):
        os.remove(target)
    
    pyautogui.hotkey("ctrl", "s")
    time.sleep(1.0)
    pyautogui.write(target, interval=0.01)
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(1.0)
    
    sz = os.path.getsize(target) if os.path.exists(target) else 0
    h = sha256_file(target)
    print(f"Shape: {shape}, File: {target}, Size: {sz}, SHA256: {h}")
    return h

if __name__ == "__main__":
    h1 = draw_shape("circle")
    h2 = draw_shape("rectangle")
    print("\nHashes different:", h1 != h2)
