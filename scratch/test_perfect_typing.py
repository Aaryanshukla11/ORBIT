import ctypes
from ctypes import wintypes
import os
import subprocess
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Set 64-bit signatures for clipboard
user32.OpenClipboard.argtypes = [wintypes.HWND]; user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []; user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []; user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]; user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]; user32.SetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]; kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]; kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]; kernel32.GlobalUnlock.restype = wintypes.BOOL

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

def release_all_modifiers():
    """Ensure no modifier keys or characters are stuck in down state."""
    for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0x33): # Shift, Ctrl, Alt, Win, Win, '3'
        user32.keybd_event(vk, 0, 2, 0) # Key Up

# Pre-cleanup
subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
release_all_modifiers()
time.sleep(1)

# Clean tabstate
local_state = os.path.expandvars(r"%LOCALAPPDATA%\Packages\Microsoft.WindowsNotepad_8wekyb3d8bbwe\LocalState")
for sub_dir in ["TabState", "WindowState"]:
    p = os.path.join(local_state, sub_dir)
    if os.path.isdir(p):
        for f in os.listdir(p):
            try: os.remove(os.path.join(p, f))
            except Exception: pass

print("1. Launching fresh Notepad...")
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
print(f"2. Notepad HWND: {np_hwnd}")

# Ensure foreground
user32.SetForegroundWindow(np_hwnd)
time.sleep(0.3)

target_text = "ORBIT Vision Test 123"
print(f"3. Injecting text {target_text!r} via deterministic paste...")

# Save original clipboard
orig_clipboard = safe_get_clipboard()

# Set clipboard to target text
safe_set_clipboard(target_text)

# Send Ctrl+V with atomic down/up
user32.keybd_event(0x11, 0, 0, 0) # Ctrl down
time.sleep(0.02)
user32.keybd_event(ord('V'), 0, 0, 0) # V down
time.sleep(0.02)
user32.keybd_event(ord('V'), 0, 2, 0) # V up
time.sleep(0.02)
user32.keybd_event(0x11, 0, 2, 0) # Ctrl up
time.sleep(0.5)

# Restore original clipboard
safe_set_clipboard(orig_clipboard)

# Read window title
buf = ctypes.create_unicode_buffer(256)
user32.GetWindowTextW(np_hwnd, buf, 256)
print(f"4. Notepad Window Title after paste: {buf.value!r}")

# Also verify via Ctrl+A, Ctrl+C copy back to verify exact document content!
user32.keybd_event(0x11, 0, 0, 0) # Ctrl down
user32.keybd_event(ord('A'), 0, 0, 0) # A down
user32.keybd_event(ord('A'), 0, 2, 0) # A up
user32.keybd_event(ord('C'), 0, 0, 0) # C down
user32.keybd_event(ord('C'), 0, 2, 0) # C up
user32.keybd_event(0x11, 0, 2, 0) # Ctrl up
time.sleep(0.5)

actual_document_text = safe_get_clipboard()
print(f"5. Actual document content copied back: {actual_document_text!r}")
print(f"6. Exact match: {actual_document_text == target_text}")

subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
release_all_modifiers()
