import ctypes
from ctypes import wintypes
import sys
import os

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
wins = []

def cb(h, l):
    if user32.IsWindow(h) and user32.IsWindowVisible(h):
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(h, buf, 512)
        title = buf.value
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        pname = ""
        if pid.value:
            hp = kernel32.OpenProcess(0x1000, False, pid.value)
            if hp:
                pbuf = ctypes.create_unicode_buffer(512)
                size = wintypes.DWORD(512)
                kernel32.QueryFullProcessImageNameW(hp, 0, pbuf, ctypes.byref(size))
                pname = os.path.basename(pbuf.value)
                kernel32.CloseHandle(hp)
        r = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        w = r.right - r.left
        h_dim = r.bottom - r.top
        if title and w > 100 and h_dim > 100:
            wins.append((h, title, pname, (r.left, r.top, w, h_dim)))
    return True

user32.EnumDesktopWindows(hdesk, ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
user32.CloseDesktop(hdesk)

print(f"Active Interactive Windows ({len(wins)}):")
for item in wins:
    print(" ", item)
