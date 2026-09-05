"""
Interactive Prototype UI Dashboard for Prototype C (Keyboard Interaction & Unicode Engine).
Provides a dedicated Tier 1 controlled text target widget, live modifier status lamps,
real-time telemetry view, and emergency stop controls.
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from app_types import (
    ShortcutSequence,
    CancellationRequest,
    CancellationSource,
)
from keyboard_controller import KeyboardController
from unicode_engine import UnicodeEngine


class PrototypeCDashboard:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ORBIT — Prototype C: Keyboard & Unicode Engine")
        self.root.geometry("640x780")
        self.root.configure(bg="#0f172a")

        self.controller = KeyboardController()
        self._is_typing = False

        self.build_ui()
        self.update_telemetry_loop()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Global Hotkey simulation for UI
        self.root.bind("<F12>", lambda e: self.trigger_emergency_stop())

    def build_ui(self):
        # Header
        header = tk.Frame(self.root, bg="#1e293b", pady=10, padx=14)
        header.pack(fill="x")

        title = tk.Label(
            header,
            text="ORBIT Keyboard & Unicode Controller (Prototype C)",
            font=("Segoe UI", 12, "bold"),
            fg="#38bdf8",
            bg="#1e293b",
        )
        title.pack(anchor="w")

        # Modifier Status Lamps Frame
        lamps_frame = tk.Frame(header, bg="#1e293b")
        lamps_frame.pack(fill="x", pady=6)

        self.lamp_ctrl = tk.Label(lamps_frame, text="CTRL", font=("Segoe UI", 9, "bold"), fg="#64748b", bg="#334155", width=8, pady=2)
        self.lamp_ctrl.pack(side="left", padx=2)

        self.lamp_shift = tk.Label(lamps_frame, text="SHIFT", font=("Segoe UI", 9, "bold"), fg="#64748b", bg="#334155", width=8, pady=2)
        self.lamp_shift.pack(side="left", padx=2)

        self.lamp_alt = tk.Label(lamps_frame, text="ALT", font=("Segoe UI", 9, "bold"), fg="#64748b", bg="#334155", width=8, pady=2)
        self.lamp_alt.pack(side="left", padx=2)

        self.lamp_win = tk.Label(lamps_frame, text="WIN", font=("Segoe UI", 9, "bold"), fg="#64748b", bg="#334155", width=8, pady=2)
        self.lamp_win.pack(side="left", padx=2)

        # Tier 1 Controlled Text Target Widget
        target_frame = tk.LabelFrame(
            self.root,
            text=" Tier 1 Controlled Text Input Target ",
            font=("Segoe UI", 9, "bold"),
            fg="#38bdf8",
            bg="#0f172a",
            padx=10,
            pady=6,
        )
        target_frame.pack(fill="x", padx=14, pady=6)

        self.txt_target = tk.Text(
            target_frame,
            height=6,
            bg="#020617",
            fg="#38bdf8",
            font=("Consolas", 11),
            insertbackground="#38bdf8",
            relief="flat",
        )
        self.txt_target.pack(fill="both", expand=True)

        # Action Buttons Frame
        btn_frame = tk.LabelFrame(
            self.root,
            text=" Test Corpora & Shortcut Triggers ",
            font=("Segoe UI", 9, "bold"),
            fg="#38bdf8",
            bg="#0f172a",
            padx=10,
            pady=6,
        )
        btn_frame.pack(fill="x", padx=14, pady=4)

        row1 = tk.Frame(btn_frame, bg="#0f172a")
        row1.pack(fill="x", pady=2)

        tk.Button(row1, text="Type ASCII", command=self.type_ascii, bg="#0284c7", fg="white", font=("Segoe UI", 8, "bold"), width=16).pack(side="left", padx=2)
        tk.Button(row1, text="Type Hindi (Devanagari)", command=self.type_hindi, bg="#0369a1", fg="white", font=("Segoe UI", 8), width=22).pack(side="left", padx=2)
        tk.Button(row1, text="Type Emojis (Non-BMP)", command=self.type_emojis, bg="#0369a1", fg="white", font=("Segoe UI", 8), width=20).pack(side="left", padx=2)

        row2 = tk.Frame(btn_frame, bg="#0f172a")
        row2.pack(fill="x", pady=2)

        tk.Button(row2, text="Type Math & Currency", command=self.type_math, bg="#0369a1", fg="white", font=("Segoe UI", 8), width=20).pack(side="left", padx=2)
        tk.Button(row2, text="Stream 1000 Chars", command=self.stream_long_text, bg="#475569", fg="white", font=("Segoe UI", 8), width=18).pack(side="left", padx=2)
        tk.Button(row2, text="Clear Target", command=self.clear_target, bg="#334155", fg="white", font=("Segoe UI", 8), width=16).pack(side="left", padx=2)

        # Emergency Stop Button
        self.btn_estop = tk.Button(
            self.root,
            text="🛑 EMERGENCY STOP (Press F12)",
            command=self.trigger_emergency_stop,
            bg="#dc2626",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            activebackground="#b91c1c",
            relief="flat",
            pady=6,
        )
        self.btn_estop.pack(fill="x", padx=14, pady=6)

        # Telemetry & Log Frame
        log_frame = tk.LabelFrame(
            self.root,
            text=" Telemetry & Event Stream ",
            font=("Segoe UI", 9, "bold"),
            fg="#38bdf8",
            bg="#0f172a",
            padx=10,
            pady=4,
        )
        log_frame.pack(fill="both", expand=True, padx=14, pady=6)

        self.lbl_stats = tk.Label(
            log_frame,
            text="Sessions: 0 | Typed: 0 chars | Avg CPS: 0.0 | True Cancel Latency: 0.0 µs",
            font=("Consolas", 8),
            fg="#cbd5e1",
            bg="#0f172a",
            anchor="w",
        )
        self.lbl_stats.pack(fill="x", pady=2)

        self.lst_log = tk.Listbox(
            log_frame,
            bg="#020617",
            fg="#e2e8f0",
            font=("Consolas", 8),
            selectbackground="#1e293b",
            relief="flat",
        )
        self.lst_log.pack(fill="both", expand=True)

    def trigger_emergency_stop(self):
        req = CancellationRequest(
            source=CancellationSource.GLOBAL_EMERGENCY_STOP,
            timestamp_ns=time.perf_counter_ns(),
            reason="Global Emergency Stop triggered by operator (F12)",
            session_id="estop",
        )
        self.controller.coordinator.request_cancellation(req)
        self.controller.sanitize_all_orbit_keys()

    def update_telemetry_loop(self):
        # Update modifier lamps
        is_ctrl = self.controller.state_manager.is_key_down(0x11)
        is_shift = self.controller.state_manager.is_key_down(0x10)
        is_alt = self.controller.state_manager.is_key_down(0x12)
        is_win = self.controller.state_manager.is_key_down(0x5B) or self.controller.state_manager.is_key_down(0x5C)

        self.lamp_ctrl.config(bg="#dc2626" if is_ctrl else "#334155", fg="white" if is_ctrl else "#64748b")
        self.lamp_shift.config(bg="#dc2626" if is_shift else "#334155", fg="white" if is_shift else "#64748b")
        self.lamp_alt.config(bg="#dc2626" if is_alt else "#334155", fg="white" if is_alt else "#64748b")
        self.lamp_win.config(bg="#dc2626" if is_win else "#334155", fg="white" if is_win else "#64748b")

        stats = self.controller.telemetry.get_summary_statistics()
        self.lbl_stats.config(
            text=f"Sessions: {stats['total_sessions']} | Typed: {stats['total_characters_typed']} chars | "
                 f"Avg CPS: {stats['characters_per_second']['mean']} | "
                 f"Cancel Latency: {stats['true_cancellation_latency_us (T7 - T4)']['mean']:.1f} µs"
        )

        # Drain records to listbox
        while len(self.lst_log.get(0, "end")) < len(self.controller.telemetry.records):
            idx = len(self.lst_log.get(0, "end"))
            r = self.controller.telemetry.records[idx]
            entry = f"[{r.state}] {r.action_type}: {r.character_count} chars ({r.duration_ms}ms, {r.characters_per_second} CPS)"
            if r.cancellation_source:
                entry += f" -> Cancelled by {r.cancellation_source}"
            self.lst_log.insert("end", entry)
            self.lst_log.see("end")

        self.root.after(100, self.update_telemetry_loop)

    def _run_async_typing(self, text: str):
        self.txt_target.focus_set()
        time.sleep(0.05)

        def worker():
            hwnd = int(self.root.winfo_id())
            self.controller.type_text(text, target_hwnd=hwnd, inter_char_delay_ms=3.0)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def type_ascii(self):
        self._run_async_typing("Hello ORBIT! 1234567890 !@#$%^&*()")

    def type_hindi(self):
        self._run_async_typing("नमस्ते दुनिया Hello ORBIT")

    def type_emojis(self):
        self._run_async_typing("ORBIT 🚀 Launching High-Speed Assistant 😀 ❤️")

    def type_math(self):
        self._run_async_typing("Math: α + β = γ | π ≈ 3.14159 | ∑ √x | Currency: ₹100 €50 £20 © ® ™")

    def stream_long_text(self):
        chunk = "The quick brown fox jumps over the lazy dog. " * 25  # ~1125 chars
        self._run_async_typing(chunk)

    def clear_target(self):
        self.txt_target.delete("1.0", "end")

    def on_close(self):
        self.trigger_emergency_stop()
        self.root.destroy()


def run_ui():
    root = tk.Tk()
    app = PrototypeCDashboard(root)
    root.mainloop()


if __name__ == "__main__":
    run_ui()
