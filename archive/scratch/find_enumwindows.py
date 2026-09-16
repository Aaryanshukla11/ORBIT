import ctypes
import ctypes.wintypes as w
import os
import subprocess

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32

# Let's inspect all top-level windows using EnumWindows
all_wins = []
def cb(h, l):
    pid = w.DWORD(0)
    u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    if pid.value:
        hp = k32.OpenProcess(0x1000, False, pid.value)
        if hp:
            pbuf = ctypes.create_unicode_buffer(512)
            sz = w.DWORD(512)
            if k32.QueryFullProcessImageNameW(hp, 0, pbuf, ctypes.byref(sz)):
                pname = os.path.basename(pbuf.value)
                if "notepad" in pname.lower() or "calc" in pname.lower():
                    tbuf = ctypes.create_unicode_buffer(512)
                    u32.GetWindowTextW(h, tbuf, 512)
                    r = w.RECT()
                    u32.GetWindowRect(h, ctypes.byref(r))
                    vis = u32.IsWindowVisible(h)
                    all_wins.append((h, pid.value, pname, repr(tbuf.value), vis, (r.left, r.top, r.right, r.bottom)))
            k32.CloseHandle(hp)
    return True

proc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(cb)
u32.EnumWindows(proc, 0)
print(f"Windows found via EnumWindows: {len(all_wins)}")
for x in all_wins:
    print(x)
