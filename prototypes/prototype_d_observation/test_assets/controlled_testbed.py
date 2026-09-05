"""
Controlled Reference GUI Target for ORBIT Prototype D (Tier 1 Validation).
Spawns Tkinter GUI with exact controls specified in ground_truth_manifest.json.
"""

import sys
import json
import os
import tkinter as tk

def launch_testbed():
    root = tk.Tk()
    root.title("ORBIT_TIER1_TARGET_TESTBED")
    root.geometry("500x400+150+150")
    root.configure(bg="#1e293b")

    btn_submit = tk.Button(root, text="Submit Action", bg="#0284c7", fg="white", font=("Segoe UI", 10, "bold"))
    btn_submit.place(x=20, y=40, width=120, height=35)

    btn_cancel = tk.Button(root, text="Cancel Action", bg="#e11d48", fg="white", font=("Segoe UI", 10, "bold"))
    btn_cancel.place(x=160, y=40, width=120, height=35)

    entry_query = tk.Entry(root, font=("Segoe UI", 10))
    entry_query.insert(0, "Target Query String")
    entry_query.place(x=20, y=100, width=330, height=30)

    chk_var = tk.IntVar(value=1)
    chk_mode = tk.Checkbutton(root, text="Enable High-Accuracy Mode", variable=chk_var, bg="#1e293b", fg="white", selectcolor="#0f172a")
    chk_mode.place(x=20, y=150, width=230, height=30)

    lbl_status = tk.Label(root, text="Status: Ready", bg="#1e293b", fg="#38bdf8", font=("Segoe UI", 10))
    lbl_status.place(x=20, y=210, width=330, height=30)

    root.mainloop()

if __name__ == "__main__":
    launch_testbed()
