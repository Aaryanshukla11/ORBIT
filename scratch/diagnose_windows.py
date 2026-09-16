import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath("src"))

from orbit.runtime.capabilities.application_launcher import ApplicationLauncher
from orbit.runtime.perception.windows import Win32WindowObserver

async def main():
    observer = Win32WindowObserver()
    fg, visible = observer.observe_windows()
    print(f"Foreground window before: {fg.title if fg else None}, class: {fg.window_class if fg else None}, proc: {fg.process_name if fg else None}")
    print(f"Total visible windows before: {len(visible)}")

    launcher = ApplicationLauncher()
    print("Launching edge...")
    res = launcher.launch("edge")
    print(f"Launch result: success={res.success}, path={res.executable_path}, error={res.error_message}")

    for i in range(1, 6):
        await asyncio.sleep(1.0)
        fg, visible = observer.observe_windows()
        print(f"\n[+{i}s] Foreground: {fg.title if fg else None} (Proc: {fg.process_name if fg else None}, Class: {fg.window_class if fg else None})")
        matching = [w for w in visible if "edge" in (w.title or "").lower() or "edge" in (w.process_name or "").lower()]
        print(f"[+{i}s] Matching visible windows: {[w.title for w in matching]}")

if __name__ == "__main__":
    asyncio.run(main())
