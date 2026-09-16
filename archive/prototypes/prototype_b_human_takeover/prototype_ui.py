"""
Interactive Dashboard for Prototype B (Human Takeover & Input Ownership).
Visualizes state transitions, real-time trajectory tracking, telemetry, and manual test triggers.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import time
import threading

from app_types import Point, ActionCategory, TakeoverState
from takeover_detector import TakeoverDetector


class PrototypeBDashboard:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ORBIT — Prototype B: Human Takeover & Input Ownership")
        self.root.geometry("520x740")
        self.root.configure(bg="#0f172a")

        self.detector = TakeoverDetector(dpi_scale=2.0)
        self.detector.start()

        # Connect state change listener
        self.detector.state_machine.add_listener(self._on_state_change)

        self.build_ui()
        self.update_telemetry_loop()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Global hotkey binding for Emergency Stop (Escape / F12)
        self.root.bind("<Escape>", lambda e: self.emergency_stop())
        self.root.bind("<F12>", lambda e: self.emergency_stop())

    def build_ui(self):
        # Header & State Banner
        header = tk.Frame(self.root, bg="#1e293b", pady=10, padx=14)
        header.pack(fill="x")

        title = tk.Label(
            header,
            text="ORBIT Human Takeover Controller",
            font=("Segoe UI", 12, "bold"),
            fg="#38bdf8",
            bg="#1e293b",
        )
        title.pack(anchor="w")

        self.lbl_state_banner = tk.Label(
            header,
            text="STATE: IDLE",
            font=("Segoe UI", 13, "bold"),
            fg="#94a3b8",
            bg="#334155",
            pady=4,
            padx=8,
        )
        self.lbl_state_banner.pack(fill="x", pady=6)

        # Live Metrics Frame
        metrics_frame = tk.LabelFrame(
            self.root,
            text=" Live Input & Trajectory Telemetry ",
            font=("Segoe UI", 9, "bold"),
            fg="#38bdf8",
            bg="#0f172a",
            padx=12,
            pady=8,
        )
        metrics_frame.pack(fill="x", padx=14, pady=6)

        self.lbl_cursor_pos = tk.Label(
            metrics_frame, text="Observed Cursor: (0, 0)", font=("Consolas", 9), fg="#f8fafc", bg="#0f172a", anchor="w"
        )
        self.lbl_cursor_pos.pack(fill="x")

        self.lbl_expected_pos = tk.Label(
            metrics_frame, text="Expected Trajectory: (None)", font=("Consolas", 9), fg="#94a3b8", bg="#0f172a", anchor="w"
        )
        self.lbl_expected_pos.pack(fill="x")

        self.lbl_deviation = tk.Label(
            metrics_frame, text="Current Deviation: 0.0 px (Threshold: 0.0 px)", font=("Consolas", 9), fg="#4ade80", bg="#0f172a", anchor="w"
        )
        self.lbl_deviation.pack(fill="x", pady=2)

        self.lbl_stats = tk.Label(
            metrics_frame, text="Events Processed: 0 | Takeovers: 0", font=("Consolas", 8), fg="#cbd5e1", bg="#0f172a", anchor="w"
        )
        self.lbl_stats.pack(fill="x")

        # Action Trigger Testbed
        actions_frame = tk.LabelFrame(
            self.root,
            text=" Autonomous Input Action Testbed ",
            font=("Segoe UI", 9, "bold"),
            fg="#38bdf8",
            bg="#0f172a",
            padx=12,
            pady=8,
        )
        actions_frame.pack(fill="x", padx=14, pady=6)

        btn_move = tk.Button(
            actions_frame,
            text="▶ Move Cursor Across Screen (Normal)",
            command=self.trigger_normal_move,
            bg="#0284c7",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            pady=4,
        )
        btn_move.pack(fill="x", pady=2)

        btn_click = tk.Button(
            actions_frame,
            text="🎯 Precise Move & Click",
            command=self.trigger_precise_click,
            bg="#0369a1",
            fg="white",
            font=("Segoe UI", 9),
            relief="flat",
            pady=4,
        )
        btn_click.pack(fill="x", pady=2)

        btn_drag = tk.Button(
            actions_frame,
            text="↔ Drag Operation (Canvas Drag)",
            command=self.trigger_drag_operation,
            bg="#475569",
            fg="white",
            font=("Segoe UI", 9),
            relief="flat",
            pady=4,
        )
        btn_drag.pack(fill="x", pady=2)

        btn_reset = tk.Button(
            actions_frame,
            text="🔄 Re-observe & Reset to IDLE",
            command=self.reset_state,
            bg="#334155",
            fg="#f8fafc",
            font=("Segoe UI", 9),
            relief="flat",
            pady=4,
        )
        btn_reset.pack(fill="x", pady=2)

        # Emergency Stop Button
        btn_estop = tk.Button(
            self.root,
            text="🛑 EMERGENCY STOP (Press ESC or F12)",
            command=self.emergency_stop,
            bg="#dc2626",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            activebackground="#b91c1c",
            relief="flat",
            pady=6,
        )
        btn_estop.pack(fill="x", padx=14, pady=4)

        # Event Log Feed
        log_frame = tk.LabelFrame(
            self.root,
            text=" Low-Level Event Stream ",
            font=("Segoe UI", 9, "bold"),
            fg="#38bdf8",
            bg="#0f172a",
            padx=10,
            pady=6,
        )
        log_frame.pack(fill="both", expand=True, padx=14, pady=6)

        self.lst_events = tk.Listbox(
            log_frame,
            bg="#020617",
            fg="#e2e8f0",
            font=("Consolas", 8),
            selectbackground="#1e293b",
            relief="flat",
        )
        self.lst_events.pack(fill="both", expand=True)

    def _on_state_change(self, old_state: TakeoverState, new_state: TakeoverState, duration_ms: float):
        """Updates UI state banner when state machine changes."""
        color_map = {
            TakeoverState.IDLE: ("#94a3b8", "#334155"),
            TakeoverState.EXECUTING: ("#ffffff", "#0284c7"),
            TakeoverState.SUSPECTED_TAKEOVER: ("#ffffff", "#d97706"),
            TakeoverState.PAUSED_BY_USER: ("#ffffff", "#dc2626"),
            TakeoverState.RELEASE_PENDING: ("#ffffff", "#16a34a"),
        }
        fg, bg = color_map.get(new_state, ("#ffffff", "#334155"))
        self.lbl_state_banner.config(text=f"STATE: {new_state.value}", fg=fg, bg=bg)

    def update_telemetry_loop(self):
        """Periodically polls telemetry and event stream."""
        try:
            cur_pos = self.detector.input_controller.get_cursor_pos()
            self.lbl_cursor_pos.config(text=f"Observed Cursor: ({cur_pos[0]}, {cur_pos[1]})")

            stats = self.detector.telemetry.get_summary_statistics()
            self.lbl_stats.config(
                text=f"Events: {stats['total_events_processed']} | Takeovers: {stats['takeover_events_triggered']} | Avg Latency: {stats['detection_latency_us']['mean']:.1f}µs"
            )

            # Update event listbox with recent records
            if self.detector.telemetry.records:
                latest = self.detector.telemetry.records[-1]
                if latest.expected_pos:
                    self.lbl_expected_pos.config(text=f"Expected Trajectory: {latest.expected_pos}")
                    self.lbl_deviation.config(
                        text=f"Deviation: {latest.deviation_px:.1f} px (Threshold: {latest.allowed_threshold_px:.1f} px)",
                        fg="#ef4444" if latest.decision == "PAUSE_REQUESTED" else "#4ade80",
                    )

            # Drain recent records into listbox
            while len(self.lst_events.get(0, "end")) < len(self.detector.telemetry.records):
                idx = len(self.lst_events.get(0, "end"))
                r = self.detector.telemetry.records[idx]
                entry = f"[{r.decision}] {r.input_source} @ {r.observed_pos} (Δd={r.deviation_px}px, {r.decision_latency_us}µs)"
                self.lst_events.insert("end", entry)
                self.lst_events.see("end")

        except Exception as e:
            print(f"[UI] Telemetry error: {e}")

        self.root.after(100, self.update_telemetry_loop)

    def trigger_normal_move(self):
        cur_x, cur_y = self.detector.input_controller.get_cursor_pos()
        target_x = 2000 if cur_x < 1000 else 300
        target_y = 1200 if cur_y < 600 else 200
        self.detector.execute_movement_action(
            start_pos=Point(cur_x, cur_y),
            target_pos=Point(target_x, target_y),
            category=ActionCategory.NORMAL_MOVE,
            speed_multiplier=0.6,  # Slow enough for manual takeover testing
        )

    def trigger_precise_click(self):
        cur_x, cur_y = self.detector.input_controller.get_cursor_pos()
        self.detector.execute_movement_action(
            start_pos=Point(cur_x, cur_y),
            target_pos=Point(cur_x + 300, cur_y + 200),
            category=ActionCategory.PRECISE_CLICK,
            speed_multiplier=0.5,
        )

    def trigger_drag_operation(self):
        cur_x, cur_y = self.detector.input_controller.get_cursor_pos()
        self.detector.input_controller.mouse_down("left")
        self.detector.execute_movement_action(
            start_pos=Point(cur_x, cur_y),
            target_pos=Point(cur_x + 400, cur_y + 100),
            category=ActionCategory.DRAG_OPERATION,
            speed_multiplier=0.5,
        )

    def reset_state(self):
        self.detector.state_machine.reset_to_idle()

    def emergency_stop(self):
        self.detector.input_controller.request_cancel()
        self.detector.state_machine.transition_to(TakeoverState.PAUSED_BY_USER, "Emergency Stop Triggered")

    def on_close(self):
        self.detector.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = PrototypeBDashboard(root)
    root.mainloop()
