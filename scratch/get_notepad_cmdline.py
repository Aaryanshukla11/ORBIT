import subprocess

cmd = ['powershell', '-Command', 'Get-CimInstance Win32_Process | Where-Object { $_.Name -like "*notepad*" } | Select-Object ProcessId, CommandLine, ExecutablePath | Format-List']
p = subprocess.run(cmd, capture_output=True, text=True)
print(p.stdout)
