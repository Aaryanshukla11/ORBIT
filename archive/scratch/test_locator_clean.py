import time
import os
import ctypes
from ctypes import wintypes
from typing import Optional, List, Tuple
from orbit.models.common import BoundingBox
from orbit.adapters.observation.snapshot import ObservedWindow

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def get_proc_name(hwnd: int) -> Tuple[int, str]:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 0:
        return 0, ""
    h_proc = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h_proc:
        return pid.value, ""
    buf = ctypes.create_unicode_buffer(1024)
    size = wintypes.DWORD(1024)
    name = ""
    if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
        name = os.path.basename(buf.value)
    kernel32.CloseHandle(h_proc)
    return pid.value, name

def poll_and_resolve_window(target_query: str, timeout: float = 3.0) -> Optional[ObservedWindow]:
    tq_clean = target_query.strip().lower()
    known_app_launchers = {
        "notepad": "notepad.exe",
        "paint": "mspaint.exe",
        "mspaint": "mspaint.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "cmd": "cmd.exe",
        "terminal": "wt.exe",
        "explorer": "explorer.exe",
    }
    exe_name = known_app_launchers.get(tq_clean, f"{tq_clean}.exe")
    
    def enumerate_windows() -> List[ObservedWindow]:
        raw_wins = []
        def _cb(h, _):
            if user32.IsWindowVisible(h):
                r = wintypes.RECT()
                if user32.GetWindowRect(h, ctypes.byref(r)):
                    w = r.right - r.left
                    height = r.bottom - r.top
                    if w > 50 and height > 50:
                        length = user32.GetWindowTextLengthW(h)
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(h, buf, length + 1)
                        title = buf.value
                        pid, proc_name = get_proc_name(h)
                        
                        title_match = bool(title and tq_clean in title.lower())
                        proc_match = bool(proc_name and (tq_clean in proc_name.lower() or exe_name.lower() in proc_name.lower()))
                        
                        if title_match or proc_match:
                            raw_wins.append(ObservedWindow(
                                hwnd=h,
                                process_id=pid,
                                process_name=proc_name or exe_name,
                                window_title=title,
                                extended_bounds=BoundingBox(left=r.left, top=r.top, width=w, height=height),
                                is_visible=True,
                                is_foreground=(user32.GetForegroundWindow() == h),
                            ))
            return True
        cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_cb)
        user32.EnumWindows(cb, 0)
        return raw_wins

    candidates = enumerate_windows()
    if not candidates:
        import subprocess
        try:
            subprocess.Popen([exe_name], shell=False)
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < timeout:
                candidates = enumerate_windows()
                if candidates:
                    break
                time.sleep(0.1)
        except Exception as ex:
            print(f"Failed to launch {exe_name}: {ex}")

    if not candidates:
        return None

    def score_win(w: ObservedWindow) -> tuple:
        has_title = 1 if bool(w.window_title and w.window_title.strip()) else 0
        title_matches = 1 if (w.window_title and tq_clean in w.window_title.lower()) else 0
        area = w.extended_bounds.width * w.extended_bounds.height
        is_fg = 1 if w.is_foreground else 0
        return (has_title, title_matches, is_fg, area)

    best_win = max(candidates, key=score_win)
    
    # Restore and foreground
    user32.ShowWindow(best_win.hwnd, 9)
    user32.SetForegroundWindow(best_win.hwnd)
    
    return best_win

if __name__ == "__main__":
    print("Testing Notepad resolution...")
    w_notepad = poll_and_resolve_window("notepad")
    print("Resolved Notepad:", w_notepad.hwnd, w_notepad.process_name, w_notepad.window_title)

    print("\nTesting Paint resolution...")
    w_paint = poll_and_resolve_window("paint")
    print("Resolved Paint:", w_paint.hwnd, w_paint.process_name, w_paint.window_title)

    print("\nTesting NonExistentFakeApp999 resolution...")
    w_fake = poll_and_resolve_window("NonExistentFakeApp999", timeout=1.0)
    print("Resolved Fake App:", w_fake)
