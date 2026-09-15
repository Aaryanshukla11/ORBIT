import ctypes
import ctypes.wintypes

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.wintypes.LPARAM]
user32.EnumWindows.restype = ctypes.wintypes.BOOL

wins = []
def enum_proc(hwnd, lparam):
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    cls_buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls_buf, 256)
    vis = user32.IsWindowVisible(hwnd)
    wins.append({
        "pid": pid.value,
        "hwnd": hwnd,
        "visible": vis,
        "length": length,
        "title": buf.value,
        "class_name": cls_buf.value,
    })
    return True

cb = WNDENUMPROC(enum_proc)
res = user32.EnumWindows(cb, 0)
err = ctypes.get_last_error()
print(f"EnumWindows returned: {res}, last error: {err}")
print(f"Total windows enumerated: {len(wins)}")
for w in wins:
    if w["pid"] == 27476:
        print("Window for PID 27476:", w)
    elif "paint" in w["title"].lower() or "paint" in w["class_name"].lower():
        print("Window with paint in title/class:", w)
