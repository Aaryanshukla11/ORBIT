import sys
sys.path.insert(0, 'src')
from orbit.runtime.perception.windows import Win32WindowObserver

# Modify _ensure_desktop_attached temporarily to be a no-op
Win32WindowObserver._ensure_desktop_attached = lambda self: None

observer = Win32WindowObserver()
fg, wins = observer.observe_windows()

print(f"Foreground: {fg.title if fg else None} (HWND: {fg.hwnd if fg else None})")
print(f"Total windows observed: {len(wins)}")
for w in wins:
    print(f"  Win: HWND={w.hwnd:<8} | Title={w.title!r:<30} | Proc={w.process_name}")
