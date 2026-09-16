import os
import subprocess
import shutil

print("Testing shutil.which('msedge'):", shutil.which("msedge"))
print("Testing shutil.which('msedge.exe'):", shutil.which("msedge.exe"))

edge_paths = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
for ep in edge_paths:
    print(f"Path {ep} exists:", os.path.exists(ep))

try:
    print("Testing os.startfile('microsoft-edge:')")
    os.startfile("microsoft-edge:")
    print("os.startfile('microsoft-edge:') succeeded!")
except Exception as ex:
    print("os.startfile('microsoft-edge:') failed:", ex)
