"""
Independent Watchdog Process for Prototype A (Workspace & Docking).
Monitors the parent/target ORBIT process PID. If the process crashes or terminates
ungracefully without removing its AppBar, this watchdog immediately restores
the default Windows Desktop Work Area.
"""

import ctypes
from ctypes import wintypes
import sys
import time
import json
import os

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
INFINITE = 0xFFFFFFFF
SPI_GETWORKAREA = 0x0030
SPI_SETWORKAREA = 0x002F
SPIF_SENDCHANGE = 0x0002
SPIF_UPDATEINIFILE = 0x0001


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]

    def to_dict(self):
        return {"left": self.left, "top": self.top, "right": self.right, "bottom": self.bottom}


def get_current_workarea() -> RECT:
    rc = RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rc), 0)
    return rc


def restore_workarea(rc: RECT):
    user32.SystemParametersInfoW(SPI_SETWORKAREA, 0, ctypes.byref(rc), SPIF_SENDCHANGE | SPIF_UPDATEINIFILE)


def run_watchdog(target_pid: int, default_left: int, default_top: int, default_right: int, default_bottom: int, log_path: str):
    default_rect = RECT(default_left, default_top, default_right, default_bottom)

    # Open handle to target process
    h_process = kernel32.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, target_pid)
    if not h_process:
        print(f"[Watchdog] Failed to open process handle for PID {target_pid}. Exiting.")
        return

    print(f"[Watchdog] Successfully attached to PID {target_pid}. Default work area: {default_rect.to_dict()}")

    # Block until target process exits
    kernel32.WaitForSingleObject(h_process, INFINITE)
    kernel32.CloseHandle(h_process)

    death_time = time.perf_counter()
    print(f"[Watchdog] Target PID {target_pid} terminated. Checking work area consistency...")

    # Wait 100ms for standard clean-up to settle
    time.sleep(0.1)

    current_rc = get_current_workarea()
    needs_restoration = (
        current_rc.left != default_rect.left
        or current_rc.top != default_rect.top
        or current_rc.right != default_rect.right
        or current_rc.bottom != default_rect.bottom
    )

    restored = False
    restore_time = 0.0

    if needs_restoration:
        print(f"[Watchdog] Work area was NOT restored by target process! Current: {current_rc.to_dict()}")
        print(f"[Watchdog] Restoring default work area: {default_rect.to_dict()}...")
        restore_start = time.perf_counter()
        restore_workarea(default_rect)
        restore_time = (time.perf_counter() - restore_start) * 1000  # ms
        restored = True
        print(f"[Watchdog] Default work area restored in {restore_time:.2f} ms.")
    else:
        print(f"[Watchdog] Target process cleanly restored work area. No action needed.")

    # Write telemetry log
    if log_path:
        log_entry = {
            "target_pid": target_pid,
            "target_terminated_at": time.time(),
            "detected_workarea_on_exit": current_rc.to_dict(),
            "default_workarea": default_rect.to_dict(),
            "watchdog_restored_workarea": restored,
            "restoration_latency_ms": restore_time,
        }
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(log_entry, f, indent=2)
        except Exception as e:
            print(f"[Watchdog] Failed to write log: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("Usage: python watchdog.py <PID> <left> <top> <right> <bottom> [log_path]")
        sys.exit(1)

    pid = int(sys.argv[1])
    l = int(sys.argv[2])
    t = int(sys.argv[3])
    r = int(sys.argv[4])
    b = int(sys.argv[5])
    log = sys.argv[6] if len(sys.argv) > 6 else ""

    run_watchdog(pid, l, t, r, b, log)
