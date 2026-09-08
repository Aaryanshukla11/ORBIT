import ctypes
from ctypes import wintypes
import os
import subprocess
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.OpenClipboard.argtypes = [wintypes.HWND]; user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []; user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []; user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]; user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]; user32.SetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]; kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]; kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]; kernel32.GlobalUnlock.restype = wintypes.BOOL

def release_all_modifiers():
    for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0x33):
        user32.keybd_event(vk, 0, 2, 0)

def safe_set_clipboard(text: str) -> bool:
    for attempt in range(5):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                encoded = text.encode("utf-16le") + b"\x00\x00"
                h_mem = kernel32.GlobalAlloc(0x0002, len(encoded))
                ptr = kernel32.GlobalLock(h_mem)
                ctypes.memmove(ptr, encoded, len(encoded))
                kernel32.GlobalUnlock(h_mem)
                user32.SetClipboardData(13, h_mem)
                return True
            finally:
                user32.CloseClipboard()
        time.sleep(0.05)
    return False

def safe_get_clipboard() -> str:
    for attempt in range(5):
        if user32.OpenClipboard(None):
            try:
                h_data = user32.GetClipboardData(13)
                if h_data:
                    ptr = kernel32.GlobalLock(h_data)
                    res = ctypes.wstring_at(ptr)
                    kernel32.GlobalUnlock(h_data)
                    return res
                return ""
            finally:
                user32.CloseClipboard()
        time.sleep(0.05)
    return ""

def deterministic_type_text(hwnd: int, text: str) -> bool:
    release_all_modifiers()
    if hwnd:
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.1)
    
    orig_clip = safe_get_clipboard()
    try:
        if not safe_set_clipboard(text):
            return False
        
        # Dispatch Ctrl+V with explicit down/up pairing
        user32.keybd_event(0x11, 0, 0, 0) # Ctrl down
        time.sleep(0.01)
        user32.keybd_event(ord('V'), 0, 0, 0) # V down
        time.sleep(0.01)
        user32.keybd_event(ord('V'), 0, 2, 0) # V up
        time.sleep(0.01)
        user32.keybd_event(0x11, 0, 2, 0) # Ctrl up
        time.sleep(0.15)
        return True
    finally:
        release_all_modifiers()
        if orig_clip:
            safe_set_clipboard(orig_clip)

def inspect_active_document_text(hwnd: int) -> str:
    """Read document text by copying to clipboard and restoring."""
    if hwnd:
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.05)
    
    orig = safe_get_clipboard()
    try:
        # Ctrl+A then Ctrl+C
        user32.keybd_event(0x11, 0, 0, 0) # Ctrl down
        user32.keybd_event(ord('A'), 0, 0, 0) # A down
        user32.keybd_event(ord('A'), 0, 2, 0) # A up
        user32.keybd_event(ord('C'), 0, 0, 0) # C down
        user32.keybd_event(ord('C'), 0, 2, 0) # C up
        user32.keybd_event(0x11, 0, 2, 0) # Ctrl up
        time.sleep(0.15)
        
        copied = safe_get_clipboard()
        # Deselect by pressing Right arrow
        user32.keybd_event(0x27, 0, 0, 0) # Right down
        user32.keybd_event(0x27, 0, 2, 0) # Right up
        return copied
    finally:
        release_all_modifiers()
        if orig:
            safe_set_clipboard(orig)

# Pre-cleanup
subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
time.sleep(1)

local_state = os.path.expandvars(r"%LOCALAPPDATA%\Packages\Microsoft.WindowsNotepad_8wekyb3d8bbwe\LocalState")
for sub_dir in ["TabState", "WindowState"]:
    p = os.path.join(local_state, sub_dir)
    if os.path.isdir(p):
        for f in os.listdir(p):
            try: os.remove(os.path.join(p, f))
            except Exception: pass

subprocess.Popen("cmd /c start notepad.exe", shell=True)
time.sleep(2)

np_hwnd = None
def cb(h, _):
    global np_hwnd
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, buf, 256)
    if "notepad" in buf.value.lower() and user32.IsWindowVisible(h):
        np_hwnd = h; return False
    return True
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows(WNDENUMPROC(cb), 0)
print(f"Notepad HWND: {np_hwnd}")

# Inject text
target = "ORBIT Vision Test 123"
ok = deterministic_type_text(np_hwnd, target)
print(f"deterministic_type_text returned: {ok}")

# Inspect document text
observed = inspect_active_document_text(np_hwnd)
print(f"inspect_active_document_text observed: {observed!r}")
print(f"Exact match: {observed == target}")

# Try typing again with idempotency check:
if observed == target:
    print("IDEMPOTENCY: Target text already in document, skipping duplicate typing!")

subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
