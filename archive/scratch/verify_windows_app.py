import ctypes
from ctypes import wintypes

def check_all():
    results = []
    def callback(hwnd, extra):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
            class_buff = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd, class_buff, 256)
            cls_name = class_buff.value
            rect = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w > 100 and h > 100:
                pid = wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                results.append((hwnd, hex(hwnd), pid.value, cls_name, title, (rect.left, rect.top, w, h)))
        return True
    
    cb_proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    ctypes.windll.user32.EnumWindows(cb_proto(callback), 0)
    return results

if __name__ == "__main__":
    for hwnd, hhex, pid, cls_name, title, bbox in check_all():
        print(f"HWND: {hhex} | PID: {pid} | Class: {cls_name} | Title: '{title}' | Box: {bbox}")
