import ctypes
import ctypes.wintypes as w
import os
import sys

sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\src")
sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\prototypes\prototype_d_observation")

import comtypes.client

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32

ctypes.windll.ole32.CoInitializeEx(None, 0)
h_desk = u32.OpenInputDesktop(0, False, 0x1FF)
if h_desk:
    u32.SetThreadDesktop(h_desk)

from pyuia_wrapper import CUIAutomation8, IUIAutomation

try:
    uia = comtypes.client.CreateObject(CUIAutomation8, interface=IUIAutomation)
    root = uia.GetRootElement()
    tree_walker = uia.RawViewWalker
    child = tree_walker.GetFirstChildElement(root)
    count = 0
    print("Enumerating UI Automation Root Children:")
    while child:
        name = child.CurrentName
        proc_id = child.CurrentProcessId
        c_type = child.CurrentControlType
        auto_id = child.CurrentAutomationId
        hwnd = child.CurrentNativeWindowHandle
        if "notepad" in (name or "").lower() or "calc" in (name or "").lower() or proc_id in (30148, 8752):
            print(f"MATCH: hwnd={hwnd}, pid={proc_id}, name={repr(name)}, auto_id={auto_id}, c_type={c_type}")
        child = tree_walker.GetNextSiblingElement(child)
        count += 1
    print(f"Total root UIA children checked: {count}")
except Exception as e:
    print(f"UIA Error: {e}")
