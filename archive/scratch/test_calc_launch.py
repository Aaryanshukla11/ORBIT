import subprocess
import time
import sys

sys.path.extend(['src', 'prototypes/prototype_d_observation'])
from window_tracker import WindowTracker

wt = WindowTracker()
subprocess.run('taskkill /f /im CalculatorApp.exe', shell=True, capture_output=True)
subprocess.run('taskkill /f /im calc.exe', shell=True, capture_output=True)
time.sleep(1)

print('Before launch:', [(w.hwnd, w.window_title, w.process_name) for w in wt.enumerate_visible_windows() if 'calc' in w.process_name.lower() or 'calc' in (w.window_title or '').lower()])

p = subprocess.Popen('calc.exe')
print('Launched PID:', p.pid)
t0 = time.perf_counter()
found = []
for i in range(40):
    time.sleep(0.25)
    wins = wt.enumerate_visible_windows()
    found = [(w.hwnd, w.window_title, w.process_name) for w in wins if 'calc' in w.process_name.lower() or 'calc' in (w.window_title or '').lower()]
    if found:
        print(f'Found in {time.perf_counter()-t0:.2f}s (iter {i}):', found)
        break

if not found:
    print('Not found after 10s. All windows:', [(w.hwnd, w.window_title, w.process_name) for w in wt.enumerate_visible_windows() if w.window_title])
