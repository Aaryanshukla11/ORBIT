import sys
sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\src")
sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\prototypes\prototype_d_observation")

from window_tracker import WindowTracker
from uia_provider import UIAutomationProvider

wt = WindowTracker()
wins = wt.enumerate_visible_windows()
print(f"Total visible windows: {len(wins)}")
for w in wins:
    print(f"HWND: {w.hwnd} | PID: {w.process_id} | Process: {w.process_name} | Title: {repr(w.window_title)}")

calc_wins = [w for w in wins if "calc" in w.process_name.lower() or "calc" in w.window_title.lower()]
if calc_wins:
    c_hwnd = calc_wins[0].hwnd
    print(f"\nQuerying UIA for Calculator HWND {c_hwnd}...")
    uia = UIAutomationProvider()
    res = uia.collect_observations(hwnd=c_hwnd, generation_id=1, timeout_ms=3000)
    print(f"Status: {res.status.value}, Elements found: {len(res.elements)}")
    for el in res.elements[:15]:
        print(f"  - [{el.control_type}] name={repr(el.name)} id={el.automation_id} bounds={el.bounds}")
