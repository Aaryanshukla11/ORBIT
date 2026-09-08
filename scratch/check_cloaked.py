import ctypes
import ctypes.wintypes
from orbit.adapters.pointer.safety import attached_to_input_desktop

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.wintypes.LPARAM]
user32.EnumWindows.restype = ctypes.wintypes.BOOL

DWMWA_CLOAKED = 14

with attached_to_input_desktop():
    wins = []
    def proc(hwnd, lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buf, 256)
        vis = user32.IsWindowVisible(hwnd)
        cloaked = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        wins.append({
            "hwnd": hwnd,
            "pid": pid.value,
            "title": buf.value,
            "class": cls_buf.value,
            "visible": vis,
            "cloaked": cloaked.value,
        })
        return True

    cb = WNDENUMPROC(proc)
    user32.EnumWindows(cb, 0)

    print(f"Total enumerated: {len(wins)}")
    for w in wins:
        if w["pid"] == 28804 or "paint" in w["title"].lower() or "paint" in w["class"].lower():
            print("MATCH:", w)
