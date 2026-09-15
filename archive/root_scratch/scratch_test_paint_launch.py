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

print("1. Testing os.system('start mspaint'):")
os.system('start mspaint')
time.sleep(2.5)
res1 = get_paint()
print("Result 1:", res1)

if not res1:
    print("2. Testing subprocess.Popen(['cmd.exe', '/c', 'start', 'mspaint']):")
    subprocess.Popen(['cmd.exe', '/c', 'start', 'mspaint'])
    time.sleep(2.5)
    res2 = get_paint()
    print("Result 2:", res2)

if not res1 and not res2:
    print("3. Testing os.startfile('ms-paint:'):")
    try:
        os.startfile('ms-paint:')
        time.sleep(2.5)
        print("Result 3:", get_paint())
    except Exception as e:
        print("Error 3:", e)
