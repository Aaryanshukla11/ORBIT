"""
Complex Hierarchical Native UI Testbed for ORBIT Prototype D (Tier 3 Validation).
Creates multi-pane hierarchical UI with Treeview, Notebook tabs, Comboboxes, Menubars,
and deep control nesting to validate accessibility tree depth traversal and watchdog safety.
"""

import sys
import tkinter as tk
from tkinter import ttk

def launch_complex_testbed():
    root = tk.Tk()
    root.title("ORBIT_TIER3_COMPLEX_SHELL_TESTBED")
    root.geometry("650x500+100+100")
    root.configure(bg="#0f172a")

    # Menu bar
    menubar = tk.Menu(root)
    filemenu = tk.Menu(menubar, tearoff=0)
    filemenu.add_command(label="New Observation")
    filemenu.add_command(label="Open Workspace")
    filemenu.add_separator()
    filemenu.add_command(label="Exit", command=root.quit)
    menubar.add_cascade(label="File", menu=filemenu)
    root.config(menu=menubar)

    # Notebook with tabs
    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)

    # Tab 1: Tree View & Navigation
    tab1 = ttk.Frame(notebook)
    notebook.add(tab1, text="Process Hierarchy")

    tree = ttk.Treeview(tab1, columns=("PID", "Status", "Memory"), show="tree headings")
    tree.heading("#0", text="Application Name")
    tree.heading("PID", text="Process ID")
    tree.heading("Status", text="Health")
    tree.heading("Memory", text="Working Set")

    node1 = tree.insert("", "end", text="System Root", values=("0", "HEALTHY", "128MB"))
    node2 = tree.insert(node1, "end", text="Window Server", values=("104", "HEALTHY", "64MB"))
    tree.insert(node2, "end", text="Desktop Window Manager", values=("1088", "HEALTHY", "32MB"))
    tree.insert("", "end", text="ORBIT Engine", values=("4096", "ACTIVE", "256MB"))
    tree.pack(fill="both", expand=True, padx=5, pady=5)

    # Tab 2: Control Panel
    tab2 = ttk.Frame(notebook)
    notebook.add(tab2, text="Diagnostics & Watchdog")

    lbl = ttk.Label(tab2, text="Watchdog Timeout Configuration (ms):")
    lbl.pack(anchor="w", padx=10, pady=5)
    combo = ttk.Combobox(tab2, values=["50ms", "150ms", "250ms", "500ms"])
    combo.current(1)
    combo.pack(anchor="w", padx=10, pady=5)

    chk_val = tk.IntVar(value=1)
    chk = ttk.Checkbutton(tab2, text="Enforce Circuit Breaker Quarantine", variable=chk_val)
    chk.pack(anchor="w", padx=10, pady=5)

    btn_diag = ttk.Button(tab2, text="Execute Full Diagnostic Scan")
    btn_diag.pack(anchor="w", padx=10, pady=10)

    root.mainloop()

if __name__ == "__main__":
    launch_complex_testbed()
