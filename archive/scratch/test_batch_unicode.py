import ctypes
from ctypes import wintypes
import os
import subprocess
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# INPUT structures
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_uint64),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_uint64),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

def send_unicode_string(text: str):
    packets = []
    for ch in text:
        code = ord(ch)
        
        down = INPUT()
        down.type = INPUT_KEYBOARD
        down.union.ki.wScan = code & 0xFFFF
        down.union.ki.wVk = 0
        down.union.ki.dwFlags = KEYEVENTF_UNICODE
        
        up = INPUT()
        up.type = INPUT_KEYBOARD
        up.union.ki.wScan = code & 0xFFFF
        up.union.ki.wVk = 0
        up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        
        packets.extend([down, up])
        
    arr = (INPUT * len(packets))(*packets)
    accepted = user32.SendInput(len(packets), arr, ctypes.sizeof(INPUT))
    return accepted

# Clean and launch Notepad
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

# Find notepad
notepad_hwnd = None
def cb(hwnd, _):
    global notepad_hwnd
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    if "notepad" in buf.value.lower() and user32.IsWindowVisible(hwnd):
        notepad_hwnd = hwnd
        return False
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows(WNDENUMPROC(cb), 0)
print(f"Notepad HWND: {notepad_hwnd}")

if notepad_hwnd:
    # Bring to foreground and focus
    user32.SetForegroundWindow(notepad_hwnd)
    time.sleep(0.5)
    
    # Send Unicode string
    test_str = "ORBIT Vision Test 123"
    print(f"Sending {test_str!r} via batch SendInput...")
    acc = send_unicode_string(test_str)
    print(f"Accepted packets: {acc} / {len(test_str) * 2}")
    time.sleep(1)
    
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(notepad_hwnd, buf, 256)
    print(f"Notepad title after batch SendInput: {buf.value!r}")

subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
