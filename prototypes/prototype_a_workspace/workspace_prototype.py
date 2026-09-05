"""
Interactive Prototype A: Windows Workspace & Docking Manager.
Provides an interactive GUI to test AppBar docking, work area changes,
maximized window interactions, multi-monitor metrics, and crash watchdog recovery.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import ctypes
from ctypes import wintypes
import os
import sys
import subprocess
import time
import json

from appbar_native import (
    Win32AppBar,
    RECT,
    ABE_RIGHT,
    ABE_LEFT,
    set_dpi_awareness,
    get_desktop_workarea,
    get_screen_dimensions,
    enum_monitors,
    user32,
    kernel32,
    SPI_SETWORKAREA,
    SPIF_SENDCHANGE,
    SPIF_UPDATEINIFILE,
)


class WorkspacePrototypeApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ORBIT — Prototype A: Workspace & Docking")
        self.root.geometry("440x680")
        self.root.configure(bg="#0f172a")

        # Configure DPI awareness
        set_dpi_awareness()

        # Capture baseline initial work area
        self.initial_workarea = get_desktop_workarea()
        self.screen_w, self.screen_h = get_screen_dimensions()

        # Get Win32 HWND for Tkinter window
        self.root.update_idletasks()
        self.hwnd = user32.GetParent(self.root.winfo_id())
        if not self.hwnd:
            self.hwnd = self.root.winfo_id()

        # Initialize AppBar wrapper
        self.appbar = Win32AppBar(self.hwnd)

        # Telemetry / Log file
        self.log_path = os.path.join(os.path.dirname(__file__), "prototype_a_results.json")
        self.watchdog_log = os.path.join(os.path.dirname(__file__), "watchdog_telemetry.json")

        # Spawn background watchdog process
        self.spawn_watchdog()

        # Test process handle (e.g. Notepad)
        self.test_process: subprocess.Popen | None = None

        # Build UI layout
        self.build_ui()

        # Start periodic telemetry polling
        self.update_telemetry()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def spawn_watchdog(self):
        """Spawns an independent, detached watchdog process monitoring this PID."""
        watchdog_script = os.path.join(os.path.dirname(__file__), "watchdog.py")
        pid = os.getpid()
        args = [
            sys.executable,
            watchdog_script,
            str(pid),
            str(self.initial_workarea.left),
            str(self.initial_workarea.top),
            str(self.initial_workarea.right),
            str(self.initial_workarea.bottom),
            self.watchdog_log,
        ]
        # Spawn detached process on Windows
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(
            args,
            creationflags=DETACHED_PROCESS,
            close_fds=True,
        )
        print(f"[Prototype A] Detached watchdog spawned for PID {pid}.")

    def build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # Title Frame
        title_frame = tk.Frame(self.root, bg="#1e293b", pady=12, padx=16)
        title_frame.pack(fill="x")

        title_lbl = tk.Label(
            title_frame,
            text="ORBIT Workspace Manager",
            font=("Segoe UI", 13, "bold"),
            fg="#38bdf8",
            bg="#1e293b",
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = tk.Label(
            title_frame,
            text="Prototype A: Win32 AppBar & Docking Validation",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#1e293b",
        )
        subtitle_lbl.pack(anchor="w")

        # Live Telemetry Frame
        self.telemetry_frame = tk.LabelFrame(
            self.root,
            text=" Live Desktop Telemetry ",
            font=("Segoe UI", 9, "bold"),
            fg="#38bdf8",
            bg="#0f172a",
            padx=12,
            pady=8,
        )
        self.telemetry_frame.pack(fill="x", padx=16, pady=8)

        self.lbl_screen = tk.Label(
            self.telemetry_frame,
            text=f"Screen: {self.screen_w}x{self.screen_h} px",
            font=("Consolas", 9),
            fg="#f8fafc",
            bg="#0f172a",
            anchor="w",
        )
        self.lbl_screen.pack(fill="x")

        self.lbl_baseline = tk.Label(
            self.telemetry_frame,
            text=f"Baseline WorkArea: ({self.initial_workarea.left}, {self.initial_workarea.top}, {self.initial_workarea.right}, {self.initial_workarea.bottom}) [{self.initial_workarea.width}x{self.initial_workarea.height}]",
            font=("Consolas", 8),
            fg="#94a3b8",
            bg="#0f172a",
            anchor="w",
        )
        self.lbl_baseline.pack(fill="x")

        self.lbl_current_wa = tk.Label(
            self.telemetry_frame,
            text="Current WorkArea: ...",
            font=("Consolas", 9, "bold"),
            fg="#4ade80",
            bg="#0f172a",
            anchor="w",
        )
        self.lbl_current_wa.pack(fill="x", pady=2)

        self.lbl_dock_status = tk.Label(
            self.telemetry_frame,
            text="Dock Status: FLOATING / UNDOCKED",
            font=("Consolas", 9),
            fg="#fbbf24",
            bg="#0f172a",
            anchor="w",
        )
        self.lbl_dock_status.pack(fill="x")

        self.lbl_monitors = tk.Label(
            self.telemetry_frame,
            text="Monitors: Detecting...",
            font=("Consolas", 8),
            fg="#cbd5e1",
            bg="#0f172a",
            anchor="w",
        )
        self.lbl_monitors.pack(fill="x", pady=2)

        # Control Actions Frame
        ctrl_frame = tk.LabelFrame(
            self.root,
            text=" Docking Actions & Experiments ",
            font=("Segoe UI", 9, "bold"),
            fg="#38bdf8",
            bg="#0f172a",
            padx=12,
            pady=8,
        )
        ctrl_frame.pack(fill="x", padx=16, pady=4)

        btn_dock_right = tk.Button(
            ctrl_frame,
            text="▶ Dock Right (~25% Work Area)",
            command=self.dock_right,
            bg="#0284c7",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            activebackground="#0369a1",
            relief="flat",
            pady=5,
        )
        btn_dock_right.pack(fill="x", pady=3)

        btn_dock_left = tk.Button(
            ctrl_frame,
            text="◀ Dock Left (~25% Work Area)",
            command=self.dock_left,
            bg="#0284c7",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            activebackground="#0369a1",
            relief="flat",
            pady=5,
        )
        btn_dock_left.pack(fill="x", pady=3)

        btn_undock = tk.Button(
            ctrl_frame,
            text="⏹ Undock & Restore Work Area",
            command=self.undock,
            bg="#475569",
            fg="white",
            font=("Segoe UI", 9),
            activebackground="#334155",
            relief="flat",
            pady=4,
        )
        btn_undock.pack(fill="x", pady=3)

        # Third-Party App Test Frame
        test_frame = tk.LabelFrame(
            self.root,
            text=" Third-Party App & Maximized Test ",
            font=("Segoe UI", 9, "bold"),
            fg="#38bdf8",
            bg="#0f172a",
            padx=12,
            pady=8,
        )
        test_frame.pack(fill="x", padx=16, pady=4)

        btn_launch_notepad = tk.Button(
            test_frame,
            text="🪟 Launch & Maximize Notepad",
            command=self.test_maximized_app,
            bg="#334155",
            fg="#f8fafc",
            font=("Segoe UI", 9),
            relief="flat",
            pady=4,
        )
        btn_launch_notepad.pack(fill="x", pady=2)

        self.lbl_notepad_bounds = tk.Label(
            test_frame,
            text="Maximized App Rect: None",
            font=("Consolas", 8),
            fg="#94a3b8",
            bg="#0f172a",
            anchor="w",
        )
        self.lbl_notepad_bounds.pack(fill="x")

        # Crash Simulation Frame
        crash_frame = tk.LabelFrame(
            self.root,
            text=" Safety & Crash Cleanup Validation ",
            font=("Segoe UI", 9, "bold"),
            fg="#ef4444",
            bg="#0f172a",
            padx=12,
            pady=8,
        )
        crash_frame.pack(fill="x", padx=16, pady=4)

        btn_crash = tk.Button(
            crash_frame,
            text="💥 Hard Kill PID (Verify Watchdog Cleanup)",
            command=self.simulate_crash,
            bg="#dc2626",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            activebackground="#b91c1c",
            relief="flat",
            pady=5,
        )
        btn_crash.pack(fill="x", pady=2)

        btn_run_suite = tk.Button(
            self.root,
            text="⚡ Run Full Automated Benchmark Suite",
            command=self.run_automated_suite,
            bg="#10b981",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            activebackground="#059669",
            relief="flat",
            pady=7,
        )
        btn_run_suite.pack(fill="x", padx=16, pady=10)

    def update_telemetry(self):
        """Polls current Windows Work Area and monitors."""
        try:
            curr_wa = get_desktop_workarea()
            self.lbl_current_wa.config(
                text=f"Current WorkArea: ({curr_wa.left}, {curr_wa.top}, {curr_wa.right}, {curr_wa.bottom}) [{curr_wa.width}x{curr_wa.height}]"
            )

            # Check if shrunken
            if curr_wa.width < self.initial_workarea.width:
                shrunk_px = self.initial_workarea.width - curr_wa.width
                self.lbl_current_wa.config(fg="#38bdf8")
            else:
                self.lbl_current_wa.config(fg="#4ade80")

            if self.appbar.is_registered:
                edge_str = "RIGHT" if self.appbar.current_edge == ABE_RIGHT else "LEFT"
                self.lbl_dock_status.config(
                    text=f"Dock Status: DOCKED [{edge_str}] ({self.appbar.current_rect.width}px width)",
                    fg="#4ade80",
                )
            else:
                self.lbl_dock_status.config(text="Dock Status: FLOATING / UNDOCKED", fg="#fbbf24")

            # Mon info
            mons = enum_monitors()
            mon_str = f"Monitors ({len(mons)}): " + ", ".join(
                [f"Mon{i+1}: {m.rect.width}x{m.rect.height} (DPI {m.dpi})" for i, m in enumerate(mons)]
            )
            self.lbl_monitors.config(text=mon_str)

        except Exception as e:
            print(f"[Telemetry] Error: {e}")

        # Re-poll every 500ms
        self.root.after(500, self.update_telemetry)

    def dock_right(self):
        """Registers and docks AppBar to the Right edge."""
        try:
            if not self.appbar.is_registered:
                self.appbar.register()
            rc = self.appbar.set_dock_position(edge=ABE_RIGHT, target_width_ratio=0.25)
            print(f"[Prototype A] Docked Right successfully. Rect: {rc}")
        except Exception as e:
            messagebox.showerror("Dock Error", f"Failed to dock right: {e}")

    def dock_left(self):
        """Registers and docks AppBar to the Left edge."""
        try:
            if not self.appbar.is_registered:
                self.appbar.register()
            rc = self.appbar.set_dock_position(edge=ABE_LEFT, target_width_ratio=0.25)
            print(f"[Prototype A] Docked Left successfully. Rect: {rc}")
        except Exception as e:
            messagebox.showerror("Dock Error", f"Failed to dock left: {e}")

    def undock(self):
        """Unregisters AppBar and restores baseline work area."""
        try:
            self.appbar.unregister()
            # Set standard floating window rect
            user32.SetWindowPos(self.hwnd, 0, 100, 100, 440, 680, 0x0040)
            print("[Prototype A] Undocked and restored work area.")
        except Exception as e:
            messagebox.showerror("Undock Error", f"Failed to undock: {e}")

    def test_maximized_app(self):
        """Launches a test Notepad process, maximizes it, and measures its window bounds."""
        try:
            if self.test_process is None or self.test_process.poll() is not None:
                self.test_process = subprocess.Popen(["notepad.exe"])
                time.sleep(0.5)

            # Find Notepad HWND
            notepad_hwnd = user32.FindWindowW("Notepad", None)
            if not notepad_hwnd:
                self.lbl_notepad_bounds.config(text="Notepad window not found.")
                return

            # Maximize Notepad (SW_MAXIMIZE = 3)
            user32.ShowWindow(notepad_hwnd, 3)
            time.sleep(0.3)

            # Read maximized rect
            rc = RECT()
            user32.GetWindowRect(notepad_hwnd, ctypes.byref(rc))
            self.lbl_notepad_bounds.config(
                text=f"Maximized Rect: ({rc.left}, {rc.top}, {rc.right}, {rc.bottom}) [{rc.width}x{rc.height}]",
                fg="#f8fafc",
            )
            print(f"[Prototype A] Notepad Maximized Rect: {rc}")

        except Exception as e:
            messagebox.showerror("Test App Error", f"Failed to launch/measure test app: {e}")

    def simulate_crash(self):
        """Simulates an abrupt process crash (SIGKILL / os._exit) while docked."""
        if not self.appbar.is_registered:
            self.dock_right()
            time.sleep(0.2)

        ans = messagebox.askyesno(
            "Confirm Hard Crash",
            "This will abruptly terminate this PID using os._exit(1) while docked.\n\nThe independent background watchdog should automatically detect the crash and restore the desktop work area in <1s.\n\nProceed?",
        )
        if ans:
            print("[Prototype A] Simulating hard crash now (os._exit(1))...")
            os._exit(1)

    def run_automated_suite(self):
        """Runs the complete formal audit suite and generates a structured report."""
        from formal_test_suite import run_formal_validation
        self.undock()
        time.sleep(0.2)
        report = run_formal_validation()
        
        msg = "Formal Acceptance Audit Complete\n\n"
        for tc in report["tests"]:
            msg += f"• {tc['name']}: {tc['verdict']}\n"
        
        messagebox.showinfo("Formal Audit Complete", msg)

    def on_close(self):
        """Gracefully unregister AppBar on application exit."""
        print("[Prototype A] Exiting gracefully...")
        self.appbar.unregister()
        if self.test_process and self.test_process.poll() is None:
            self.test_process.terminate()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = WorkspacePrototypeApp(root)
    root.mainloop()
