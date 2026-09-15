import ctypes
import os
from ctypes import wintypes
import psutil

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def get_proc_name(hwnd):
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 0:
        return 0, ''
    h_proc = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h_proc:
        return pid.value, ''
    buf = ctypes.create_unicode_buffer(1024)
    size = wintypes.DWORD(1024)
    name = ''
    if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
        name = os.path.basename(buf.value)
    kernel32.CloseHandle(h_proc)
    return pid.value, name

def inspect():
    results = []
    def enum_cb(h, _):
        pid, name = get_proc_name(h)
        length = user32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(h, buf, length + 1)
        vis = bool(user32.IsWindowVisible(h))
        r = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        results.append((h, pid, name, buf.value, vis, r.left, r.top, r.right, r.bottom))
        return True

    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(enum_cb)
    if hdesk:
        user32.EnumDesktopWindows(hdesk, cb, 0)
        user32.CloseDesktop(hdesk)
    
    print(f"Total enumerated windows: {len(results)}")
    for item in results:
        h, pid, name, title, vis, l, t, r, b = item
        if vis and (r - l > 50) and (b - t > 50):
            print(f"HWND: {h:8d} | PID: {pid:6d} | Proc: {name:20s} | Vis: {vis} | Rect: ({l},{t},{r},{b}) | Title: '{title}'")

if __name__ == "__main__":
    inspect()
