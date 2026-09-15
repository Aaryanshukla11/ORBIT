import subprocess
import time
import sys
sys.path.insert(0, 'src')
from orbit.runtime.perception.windows import Win32WindowObserver

observer = Win32WindowObserver()

tests = [
    ("start notepad: (protocol)", 'cmd /c start notepad:'),
    ("notepad.exe dummy.txt", 'notepad.exe dummy.txt'),
    ("explorer shell:appsFolder", 'explorer.exe shell:appsFolder\\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App'),
]

for name, cmd in tests:
    print(f"\nTesting: {name}")
    subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
    time.sleep(1)
    
    subprocess.Popen(cmd, shell=True)
    time.sleep(3)
    
    fg, windows = observer.observe_windows()
    np_wins = [w for w in windows if "notepad" in (w.title or "").lower() or "notepad" in (w.process_name or "").lower()]
    print(f"Foreground: {fg.title if fg else None}")
    print(f"Notepad windows found: {len(np_wins)}")
    for w in np_wins:
        print(f"  MATCH: HWND={w.hwnd}, Title={w.title!r}")
    
    p = subprocess.run(['powershell', '-Command', 'Get-CimInstance Win32_Process | Where-Object { $_.Name -like "*notepad*" } | Select-Object ProcessId, CommandLine | Format-List'], capture_output=True, text=True)
    print("Processes:\n", p.stdout.strip())
    
    subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
