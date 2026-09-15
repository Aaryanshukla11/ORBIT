import ctypes
from ctypes import wintypes
import subprocess
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Find notepad threads
p = subprocess.run(['powershell', '-Command', 'Get-CimInstance Win32_Thread | Where-Object { $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($_.ProcessId)"; $proc.Name -like "*notepad*" } | Select-Object ProcessId, Handle, ThreadState | Format-List'], capture_output=True, text=True)
print("Notepad threads:")
print(p.stdout)
