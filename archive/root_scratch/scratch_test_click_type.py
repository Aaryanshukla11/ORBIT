import ctypes
from ctypes import wintypes
import time
import subprocess
import os

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

class INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]
    _anonymous_ = ("_union",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_union", _INPUT_UNION),
    ]

def send_unicode(char):
    code = ord(char)
    inp1 = INPUT(type=1)
    inp1.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=0x0004, time=0, dwExtraInfo=0) # KEYEVENTF_UNICODE
    inp2 = INPUT(type=1)
    inp2.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=0x0004 | 0x0002, time=0, dwExtraInfo=0) # KEYUP
    arr = (INPUT * 2)(inp1, inp2)
    user32.SendInput(2, arr, ctypes.sizeof(INPUT))

def test_notepad_click_and_type():
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    
    hwnd = user32.FindWindowW(None, "Untitled - Notepad")
    if not hwnd:
        hwnd = user32.FindWindowW("Notepad", None)
    print(f"Notepad hwnd: {hwnd}")
    
    # Get window rect
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    center_x = (rect.left + rect.right) // 2
    center_y = (rect.top + rect.bottom) // 2
    print(f"Window rect: ({rect.left}, {rect.top}, {rect.right}, {rect.bottom}), center: ({center_x}, {center_y})")
    
    # Unlock foreground and bring to top
    VK_MENU = 0x12
    KEYEVENTF_KEYUP = 0x0002
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    user32.ShowWindow(hwnd, 9) # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.2)
    
    # Click inside the text area
    user32.SetCursorPos(center_x, center_y)
    user32.mouse_event(0x0002, 0, 0, 0, 0) # MOUSEEVENTF_LEFTDOWN
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0) # MOUSEEVENTF_LEFTUP
    time.sleep(0.3)
    
    # Type 'HELLO ORBIT'
    for c in "HELLO ORBIT":
        send_unicode(c)
        time.sleep(0.03)
    
    time.sleep(0.8)
    
    # Check title
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    print(f"Notepad title after typing: '{buf.value}'")
    
    # Terminate
    proc.terminate()

if __name__ == "__main__":
    test_notepad_click_and_type()
