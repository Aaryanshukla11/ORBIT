import ctypes
from ctypes import wintypes
import os
import subprocess
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def set_clipboard_text(text: str):
    user32.OpenClipboard(None)
    user32.EmptyClipboard()
    
    # Allocate global memory
    GMEM_MOVEABLE = 0x0002
    encoded = text.encode("utf-16le") + b"\x00\x00"
    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
    ptr = kernel32.GlobalLock(h_mem)
    ctypes.memmove(ptr, encoded, len(encoded))
    kernel32.GlobalUnlock(h_mem)
    
    CF_UNICODETEXT = 13
    user32.SetClipboardData(CF_UNICODETEXT, h_mem)
    user32.CloseClipboard()

def get_clipboard_text() -> str:
    user32.OpenClipboard(None)
    CF_UNICODETEXT = 13
    h_data = user32.GetClipboardData(CF_UNICODETEXT)
    result = ""
    if h_data:
        ptr = kernel32.GlobalLock(h_data)
        result = ctypes.wstring_at(ptr)
        kernel32.GlobalUnlock(h_data)
    user32.CloseClipboard()
    return result

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
    user32.SetForegroundWindow(notepad_hwnd)
    time.sleep(0.5)
    
    # Save original clipboard
    orig_clip = get_clipboard_text()
    print(f"Original clipboard: {orig_clip!r}")
    
    target_text = "ORBIT Vision Test 123"
    set_clipboard_text(target_text)
    
    # Dispatch Ctrl+V
    WM_PASTE = 0x0302
    user32.SendMessageW(notepad_hwnd, WM_PASTE, 0, 0)
    time.sleep(0.1)
    
    # Also send Ctrl+V keystroke to active foreground
    user32.keybd_event(0x11, 0, 0, 0) # Ctrl down
    user32.keybd_event(ord('V'), 0, 0, 0) # V down
    user32.keybd_event(ord('V'), 0, 2, 0) # V up
    user32.keybd_event(0x11, 0, 2, 0) # Ctrl up
    time.sleep(0.5)
    
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(notepad_hwnd, buf, 256)
    print(f"Notepad title after paste: {buf.value!r}")

subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
