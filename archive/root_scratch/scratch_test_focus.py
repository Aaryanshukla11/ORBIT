import ctypes
import time
import subprocess
import os

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def test_focus():
    # Spawn notepad
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.0)
    
    # Find notepad hwnd
    hwnd = user32.FindWindowW(None, "Untitled - Notepad")
    if not hwnd:
        hwnd = user32.FindWindowW("Notepad", None)
    print(f"Found Notepad hwnd: {hwnd}")
    
    # Check current foreground
    fg = user32.GetForegroundWindow()
    print(f"Current foreground: {fg}")
    
    # Try focus with Alt key unlock
    VK_MENU = 0x12
    KEYEVENTF_KEYUP = 0x0002
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.1)
    
    new_fg = user32.GetForegroundWindow()
    print(f"New foreground: {new_fg} (matches hwnd={hwnd}: {new_fg == hwnd})")
    
    # Clean up
    proc.terminate()

if __name__ == "__main__":
    test_focus()
