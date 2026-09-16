import asyncio
import ctypes
import ctypes.wintypes
import logging
import time

user32 = ctypes.windll.user32
user32.GetWindowRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]
user32.GetWindowRect.restype = ctypes.wintypes.BOOL
from orbit.adapters.pointer.safety import attached_to_input_desktop

def find_paint_hwnd():
    with attached_to_input_desktop():
        wins = []
        def proc(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    cls_buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, cls_buf, 256)
                    title = buf.value
                    cls_name = cls_buf.value
                    if "antigravity" in title.lower():
                        return True
                    if 'paint' in title.lower() or 'paint' in cls_name.lower():
                        wins.append((hwnd, title, cls_name))
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        cb = WNDENUMPROC(proc)
        user32.EnumWindows(cb, 0)
        return wins[0][0] if wins else None

hwnd = find_paint_hwnd()
print("Paint HWND:", hwnd)
rect = ctypes.wintypes.RECT()
ok = user32.GetWindowRect(hwnd, ctypes.byref(rect))
print(f"GetWindowRect ok={ok}: left={rect.left}, top={rect.top}, right={rect.right}, bottom={rect.bottom}")
