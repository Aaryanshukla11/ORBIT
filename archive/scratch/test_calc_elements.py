import subprocess
import time
import sys
import os

sys.path.extend(['src', 'prototypes/prototype_d_observation'])
from window_tracker import WindowTracker
from accessibility_coordinator import AccessibilityCoordinator

# Clean any existing Calculator instances
subprocess.run('taskkill /f /im CalculatorApp.exe', shell=True, capture_output=True)
subprocess.run('taskkill /f /im calc.exe', shell=True, capture_output=True)
time.sleep(1)

# Launch Calculator
os.system("start calculator:")
time.sleep(2)

wt = WindowTracker()
calc_wins = [w for w in wt.enumerate_visible_windows() if 'calc' in w.process_name.lower() or 'calc' in (w.window_title or '').lower()]
print('Calculator windows found:', [(w.hwnd, w.window_title, w.process_name, w.is_foreground) for w in calc_wins])

coord = AccessibilityCoordinator(timeout_ms=2000)
for w in calc_wins:
    elems, _ = coord.collect_accessibility_observations(w.hwnd)
    print(f"HWND {w.hwnd} ({w.process_name}): {len(elems)} elements")
    for e in elems:
        if e.name in ('4', '5', '6', '2', '3', '7', '8', '9', '0', 'Equals', 'Multiply') or e.automation_id in ('num4Button', 'equalButton', 'multiplyButton'):
            print(f"  Element: name='{e.name}', aid='{e.automation_id}', role='{e.role}', bounds=({e.bounds.left},{e.bounds.top},{e.bounds.width},{e.bounds.height})")
