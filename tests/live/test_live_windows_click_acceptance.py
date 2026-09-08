"""Live Windows Click Acceptance Test Suite.

Validates that ORBIT's pointer subsystem executes genuine physical clicks on
real Windows applications and controlled desktop fixtures, verifying:
1. Real cursor movement to physical screen coordinates.
2. Real SendInput MOUSEEVENTF_LEFTDOWN / MOUSEEVENTF_LEFTUP dispatch.
3. Target applications physically registering the click and updating observable UI state.

Epistemic Classification:
- LIVE_OS_VALIDATED: Executed against live Windows applications and GUI fixtures.
"""

from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import time
import tkinter as tk
from typing import Generator, Optional
import pytest

from orbit.adapters.keyboard.adapter import ProductionKeyboardAdapter
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.pointer.buttons import ClickExecutionStatus
from orbit.adapters.pointer.movement import get_live_cursor_position
from orbit.adapters.pointer.safety import (
    create_mouse_input_packet,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    ORBIT_EXTRA_INFO_SIGNATURE,
)
from orbit.adapters.workspace.abi import IS_WINDOWS
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="Live OS tests require genuine Windows environment")
async def test_live_physical_clicking_acceptance_matrix():
    """Live OS Acceptance: Comprehensive Physical Pointer Click & Interaction Matrix.
    
    Proves that ProductionPointerAdapter:
    1. Physically moves to real target desktop coordinates.
    2. Sends real Win32 SendInput MOUSEEVENTF_LEFTDOWN / MOUSEEVENTF_LEFTUP packets.
    3. Successfully triggers single-click button callbacks.
    4. Successfully triggers toggle-click button state changes.
    5. Successfully focuses text inputs via pointer click for keyboard input.
    """
    u32 = ctypes.windll.user32
    hwinsta = u32.OpenWindowStationW("WinSta0", False, 0x37F)
    if hwinsta:
        u32.SetProcessWindowStation(hwinsta)
    hdesk = u32.OpenDesktopW("Default", 0, False, 0x1FF)
    if hdesk:
        u32.SetThreadDesktop(hdesk)

    root = tk.Tk()
    root.title("ORBIT_PHYSICAL_CLICK_MATRIX")
    root.geometry("450x350+300+200")
    root.attributes("-topmost", True)

    btn1_clicks = 0
    btn2_toggled = False

    def on_btn1():
        nonlocal btn1_clicks
        btn1_clicks += 1
        lbl1.config(text=f"BTN1 CLICKS: {btn1_clicks}")

    def on_btn2():
        nonlocal btn2_toggled
        btn2_toggled = not btn2_toggled
        lbl2.config(text=f"BTN2 TOGGLED: {btn2_toggled}")

    btn1 = tk.Button(root, text="ACTUATE_COUNTER", command=on_btn1, font=("Arial", 11, "bold"), width=20, bg="#2196F3", fg="white")
    btn1.pack(pady=10)
    lbl1 = tk.Label(root, text="BTN1 CLICKS: 0", font=("Arial", 10))
    lbl1.pack()

    btn2 = tk.Button(root, text="TOGGLE_SWITCH", command=on_btn2, font=("Arial", 11, "bold"), width=20, bg="#9C27B0", fg="white")
    btn2.pack(pady=10)
    lbl2 = tk.Label(root, text="BTN2 TOGGLED: False", font=("Arial", 10))
    lbl2.pack()

    entry = tk.Entry(root, font=("Arial", 13), width=24)
    entry.pack(pady=12)

    root.update()
    root.update_idletasks()

    def get_widget_center(widget):
        root.update_idletasks()
        wx = root.winfo_rootx()
        wy = root.winfo_rooty()
        return wx + widget.winfo_x() + (widget.winfo_width() // 2), wy + widget.winfo_y() + (widget.winfo_height() // 2)

    b1_x, b1_y = get_widget_center(btn1)
    b2_x, b2_y = get_widget_center(btn2)
    entry_x, entry_y = get_widget_center(entry)

    pointer = ProductionPointerAdapter()
    keyboard = ProductionKeyboardAdapter()

    await pointer.initialize()
    await keyboard.initialize()

    hwnd = int(root.frame(), 16) if isinstance(root.frame(), str) else int(root.frame())
    if hwnd:
        EvidenceBasedTargetLocator._force_foreground_window(hwnd)
    await asyncio.sleep(0.15)
    root.update()

    # --- ACTION 1: Click Button 1 twice ---
    res1 = await pointer.click(b1_x, b1_y)
    assert res1 is True, "First pointer click on Button 1 must succeed"
    for _ in range(5):
        root.update()
        await asyncio.sleep(0.02)

    res2 = await pointer.click(b1_x, b1_y)
    assert res2 is True, "Second pointer click on Button 1 must succeed"
    for _ in range(5):
        root.update()
        await asyncio.sleep(0.02)

    assert btn1_clicks == 2, f"Physical clicks failed to actuate Button 1 callback (expected 2, got {btn1_clicks})"

    # --- ACTION 2: Click Button 2 once ---
    res3 = await pointer.click(b2_x, b2_y)
    assert res3 is True, "Pointer click on Toggle Button must succeed"
    for _ in range(5):
        root.update()
        await asyncio.sleep(0.02)

    assert btn2_toggled is True, f"Physical click failed to toggle Button 2 (expected True, got {btn2_toggled})"

    # --- ACTION 3: Click Entry Box to focus and type text ---
    res4 = await pointer.click(entry_x, entry_y)
    assert res4 is True, "Pointer click to focus Entry box must succeed"
    for _ in range(5):
        root.update()
        await asyncio.sleep(0.02)

    type_ok = await keyboard.type_text("ORBIT_CLICK_PASS")
    assert type_ok is True, "Keyboard typing into focused entry box must succeed"

    for _ in range(5):
        root.update()
        await asyncio.sleep(0.02)

    val = entry.get()
    assert val == "ORBIT_CLICK_PASS", f"Expected Entry content 'ORBIT_CLICK_PASS', got '{val}'"

    await pointer.shutdown()
    await keyboard.shutdown()
    root.destroy()

