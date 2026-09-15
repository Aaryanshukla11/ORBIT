import sys
sys.path.insert(0, 'prototypes/prototype_d_observation')
from window_tracker import WindowTracker

wt = WindowTracker()
wins = wt.enumerate_visible_windows()
for w in wins:
    print(f"HWND: {w.hwnd}, Title: '{w.window_title}', Proc: '{w.process_name}', PID: {w.process_id}, Bounds: {w.extended_bounds}")
