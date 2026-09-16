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

class INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]
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

def test_notepad_typing():
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)
    
    hwnd = user32.FindWindowW(None, "Untitled - Notepad")
    if not hwnd:
        hwnd = user32.FindWindowW("Notepad", None)
    print(f"Notepad hwnd: {hwnd}")
    
    # Set foreground
    user32.ShowWindow(hwnd, 5) # SW_SHOW
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    
    # Type 'HELLO ORBIT'
    for c in "HELLO ORBIT":
        send_unicode(c)
        time.sleep(0.02)
    
    time.sleep(0.5)
    
    # Check title
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    print(f"Notepad title after typing: '{buf.value}'")
    
    # Terminate
    proc.terminate()

if __name__ == "__main__":
    test_notepad_typing()
