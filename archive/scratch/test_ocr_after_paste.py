import asyncio
import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import time

sys.path.insert(0, "src")
from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.runtime.perception.engine import DesktopPerceptionEngine
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.cognitive.models import StructuredObjective

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

def safe_set_clipboard(text: str) -> bool:
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
    return False

async def main():
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

    user32.SetForegroundWindow(np_hwnd)
    time.sleep(0.3)

    target_text = "ORBIT Vision Test 123"
    safe_set_clipboard(target_text)

    # Ctrl+V
    user32.keybd_event(0x11, 0, 0, 0)
    user32.keybd_event(ord('V'), 0, 0, 0)
    user32.keybd_event(ord('V'), 0, 2, 0)
    user32.keybd_event(0x11, 0, 2, 0)
    time.sleep(1)

    # Observe via CurrentStateObserver
    reg = create_capability_registry(config=RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION))
    await reg.initialize_all()
    obs_cap = reg.get_optional(CapabilityType.OBSERVATION)
    perc = DesktopPerceptionEngine(observation_capability=obs_cap)
    observer = CurrentStateObserver(observation=obs_cap, perception_engine=perc)
    
    obj = StructuredObjective(
        raw_prompt="Open Notepad and type ORBIT Vision Test 123",
        user_goal="Open Notepad and type ORBIT Vision Test 123",
        end_condition="text_typed",
        target_entities=["notepad"],
    )
    obs = await observer.observe(obj)
    
    print(f"Observation ID: {obs.observation_id}")
    print(f"Foreground window: {obs.active_window_title}")
    print(f"OCR Tokens ({len(obs.ocr_tokens)}):", obs.ocr_tokens[:30])
    
    d_obs = obs.desktop_observation
    uia_names = []
    if d_obs:
        for elem in (d_obs.uia_elements or []) + (d_obs.perceived_elements or []):
            if elem.name: uia_names.append(elem.name)
            if hasattr(elem, 'value') and elem.value: uia_names.append(elem.value)
    print(f"UIA Elements/values ({len(uia_names)}):", uia_names[:20])

    await reg.shutdown_all()
    subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)

if __name__ == "__main__":
    asyncio.run(main())
