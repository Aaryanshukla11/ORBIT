import ctypes
import os
import sys

sys.path.insert(0, os.path.abspath("src"))

from orbit.runtime.capabilities.application_launcher import ApplicationLauncher
import time

launcher = ApplicationLauncher()
print("Launching Edge and Paint...")
launcher.launch("edge")
launcher.launch("mspaint")
time.sleep(3.0)

user32 = ctypes.windll.user32
fg = user32.GetForegroundWindow()
fg_title = ctypes.create_unicode_buffer(512)
user32.GetWindowTextW(fg, fg_title, 512)
fg_cls = ctypes.create_unicode_buffer(256)
user32.GetClassNameW(fg, fg_cls, 256)
print(f"Foreground: '{fg_title.value}' (HWND: {fg}, Class: '{fg_cls.value}')")

all_windows = []
def enum_cb(hwnd, _):
    vis = user32.IsWindowVisible(hwnd)
    length = user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1) if length > 0 else ctypes.create_unicode_buffer(1)
    if length > 0:
        user32.GetWindowTextW(hwnd, buff, length + 1)
    cls_buff = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls_buff, 256)
    
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top

    all_windows.append({
        "hwnd": hwnd,
        "title": buff.value,
        "class": cls_buff.value,
        "vis": bool(vis),
        "rect": (rect.left, rect.top, w, h),
    })
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.c_void_p)
user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

print(f"\nTotal windows enumerated: {len(all_windows)}")
for w in all_windows:
    t = w["title"].lower()
    c = w["class"].lower()
    if any(k in t or k in c for k in ("edge", "paint", "chrome", "msedge", "mspaint")):
        print(f"  Match: HWND={w['hwnd']}, Vis={w['vis']}, Title='{w['title']}', Class='{w['class']}', Rect={w['rect']}")
