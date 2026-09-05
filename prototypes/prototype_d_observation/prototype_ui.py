"""
Visual Inspector & Desktop Observation Testbed UI for ORBIT Prototype D v1.2.1.
Displays real-time screen capture, fused UI elements, spatial overlays, and confidence badges.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from typing import Optional

from capture_engine import CaptureEngine
from window_tracker import WindowTracker
from accessibility_coordinator import AccessibilityCoordinator
from fusion_engine import FusionEngine
from freshness_tracker import FreshnessTracker
from app_types import ConfidenceLevel, InvalidationReason


class PrototypeUI:
    """
    Tkinter-based Visual Inspector for Prototype D.
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ORBIT Prototype D — Screen Observation & Fusion Inspector")
        self.root.geometry("900x650")
        self.root.configure(bg="#0f172a")

        self.capture_engine = CaptureEngine()
        self.window_tracker = WindowTracker()
        self.access_coordinator = AccessibilityCoordinator()
        self.fusion_engine = FusionEngine()
        self.freshness_tracker = FreshnessTracker()

        self._build_ui()

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg="#1e293b", height=60)
        hdr.pack(fill="x", padx=10, pady=10)

        lbl_title = tk.Label(
            hdr,
            text="ORBIT PROTOTYPE D: SCREEN OBSERVATION & FUSION INSPECTOR",
            font=("Segoe UI", 12, "bold"),
            bg="#1e293b",
            fg="#38bdf8",
        )
        lbl_title.pack(side="left", padx=15, pady=10)

        self.lbl_gen = tk.Label(
            hdr,
            text="Generation: #0",
            font=("Segoe UI", 10, "bold"),
            bg="#1e293b",
            fg="#4ade80",
        )
        self.lbl_gen.pack(side="right", padx=15, pady=10)

        # Controls Toolbar
        toolbar = tk.Frame(self.root, bg="#0f172a")
        toolbar.pack(fill="x", padx=10, pady=5)

        btn_snap = tk.Button(
            toolbar,
            text="Capture & Fuse Desktop",
            command=self._on_capture_click,
            bg="#0284c7",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=5,
        )
        btn_snap.pack(side="left", padx=5)

        btn_inval = tk.Button(
            toolbar,
            text="Simulate Invalidation",
            command=self._on_invalidate_click,
            bg="#e11d48",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=5,
        )
        btn_inval.pack(side="left", padx=5)

        self.lbl_status = tk.Label(
            toolbar,
            text="Status: IDLE",
            font=("Segoe UI", 10),
            bg="#0f172a",
            fg="#94a3b8",
        )
        self.lbl_status.pack(side="left", padx=15)

        # Main Content Panes (Split: Windows list / Elements Tree)
        panes = tk.PanedWindow(self.root, orient="horizontal", bg="#334155")
        panes.pack(fill="both", expand=True, padx=10, pady=10)

        # Left: Windows Tree
        left_frame = tk.Frame(panes, bg="#1e293b")
        panes.add(left_frame, width=320)

        lbl_win_hdr = tk.Label(left_frame, text="Active Desktop Windows (Z-Order)", font=("Segoe UI", 10, "bold"), bg="#1e293b", fg="#94a3b8")
        lbl_win_hdr.pack(anchor="w", padx=10, pady=5)

        self.tree_windows = ttk.Treeview(left_frame, columns=("HWND", "Title", "PID"), show="headings")
        self.tree_windows.heading("HWND", text="HWND")
        self.tree_windows.heading("Title", text="Title")
        self.tree_windows.heading("PID", text="PID")
        self.tree_windows.column("HWND", width=80)
        self.tree_windows.column("Title", width=160)
        self.tree_windows.column("PID", width=60)
        self.tree_windows.pack(fill="both", expand=True, padx=5, pady=5)

        # Right: Fused Targets Tree
        right_frame = tk.Frame(panes, bg="#1e293b")
        panes.add(right_frame, width=540)

        lbl_elem_hdr = tk.Label(right_frame, text="Fused Observable Targets & Confidence", font=("Segoe UI", 10, "bold"), bg="#1e293b", fg="#94a3b8")
        lbl_elem_hdr.pack(anchor="w", padx=10, pady=5)

        self.tree_targets = ttk.Treeview(
            right_frame,
            columns=("Name", "Role", "Bounds", "Confidence", "Occluded"),
            show="headings",
        )
        self.tree_targets.heading("Name", text="Name")
        self.tree_targets.heading("Role", text="Role")
        self.tree_targets.heading("Bounds", text="Physical Bounds")
        self.tree_targets.heading("Confidence", text="Confidence")
        self.tree_targets.heading("Occluded", text="Occluded")
        self.tree_targets.column("Name", width=130)
        self.tree_targets.column("Role", width=90)
        self.tree_targets.column("Bounds", width=140)
        self.tree_targets.column("Confidence", width=100)
        self.tree_targets.column("Occluded", width=60)
        self.tree_targets.pack(fill="both", expand=True, padx=5, pady=5)

    def _on_capture_click(self):
        self.lbl_status.config(text="Capturing & Fusing...")
        t = threading.Thread(target=self._capture_worker, daemon=True)
        t.start()

    def _capture_worker(self):
        t0 = time.perf_counter()
        img, cap_dur, v_bounds = self.capture_engine.capture_full_desktop()
        windows = self.window_tracker.enumerate_visible_windows()
        fg_win = self.window_tracker.get_foreground_window_observation()

        curr_gen = self.freshness_tracker.current_generation
        target_hwnd = fg_win.hwnd if fg_win else (windows[0].hwnd if windows else 0)

        elems, prov_res = self.access_coordinator.collect_accessibility_observations(
            hwnd=target_hwnd,
            generation_id=curr_gen,
        )

        fused_targets, vis_feats, conflicts, conf = self.fusion_engine.fuse_observations(
            screenshot=img,
            windows=tuple(windows),
            accessibility_elements=elems,
            provider_results=prov_res,
            generation_id=curr_gen,
        )

        snap = self.freshness_tracker.build_snapshot(
            snapshot_id=f"snap_{curr_gen}",
            capture_duration_ms=cap_dur,
            desktop_geometry=v_bounds,
            foreground_window=fg_win,
            windows=tuple(windows),
            visual_evidence=vis_feats,
            accessibility_evidence=elems,
            detected_targets=fused_targets,
            confidence=conf,
            conflicts=conflicts,
        )

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        self.root.after(0, lambda: self._update_ui(snap, windows, fused_targets, elapsed_ms))

    def _update_ui(self, snap, windows, fused_targets, elapsed_ms):
        self.lbl_gen.config(text=f"Generation: #{snap.generation_id}")
        self.lbl_status.config(text=f"Fused {len(fused_targets)} targets in {elapsed_ms}ms (Conf: {snap.confidence.value})")

        # Update Windows
        for item in self.tree_windows.get_children():
            self.tree_windows.delete(item)
        for w in windows[:20]:
            self.tree_windows.insert("", "end", values=(w.hwnd, w.window_title[:25], w.process_id))

        # Update Targets
        for item in self.tree_targets.get_children():
            self.tree_targets.delete(item)
        for t in fused_targets:
            b_str = f"({t.physical_bounds.left},{t.physical_bounds.top}) {t.physical_bounds.width}x{t.physical_bounds.height}"
            self.tree_targets.insert("", "end", values=(t.name[:20], t.role, b_str, t.confidence.value, "YES" if t.is_occluded else "NO"))

    def _on_invalidate_click(self):
        new_gen = self.freshness_tracker.increment_generation(reason=InvalidationReason.USER_TAKEOVER)
        self.lbl_gen.config(text=f"Generation: #{new_gen}")
        self.lbl_status.config(text=f"Invalidated! Active generation is now #{new_gen}")


if __name__ == "__main__":
    root = tk.Tk()
    app = PrototypeUI(root)
    root.mainloop()
