import os
import subprocess
import time
import ctypes

user32 = ctypes.windll.user32

def get_paint():
    wins = []
    def proc(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                if 'paint' in buf.value.lower() or 'paint' in cls_buf.value.lower():
                    wins.append((hwnd, buf.value, cls_buf.value))
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WNDENUMPROC(proc), 0)
    return wins

# Close any open paint first
for w in get_paint():
    user32.PostMessageW(w[0], 0x0010, 0, 0) # WM_CLOSE
time.sleep(1.0)

print("Testing os.startfile('mspaint'):")
try:
    os.startfile('mspaint')
    print("startfile called.")
except Exception as e:
    print("startfile failed:", e)

time.sleep(2.5)
print("Paint after startfile:", get_paint())

print("Testing subprocess.Popen(['cmd.exe', '/c', 'start', '', 'mspaint']):")
subprocess.Popen(['cmd.exe', '/c', 'start', '', 'mspaint'])
time.sleep(2.5)
print("Paint after cmd start:", get_paint())
