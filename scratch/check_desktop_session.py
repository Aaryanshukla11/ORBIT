import ctypes
from ctypes import wintypes
import os
import subprocess
import sys

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32

# Get current process session
session_id = wintypes.DWORD()
kernel32.ProcessIdToSessionId(kernel32.GetCurrentProcessId(), ctypes.byref(session_id))
print(f"Current Process PID: {os.getpid()}, Session ID: {session_id.value}")

# Get current thread desktop
h_desk = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
name_buf = ctypes.create_unicode_buffer(256)
needed = wintypes.DWORD()
user32.GetUserObjectInformationW(h_desk, 2, name_buf, 256, ctypes.byref(needed))
print(f"Current Thread Desktop Handle: {h_desk}, Name: {name_buf.value}")

# Get window station
h_winsta = user32.GetProcessWindowStation()
winsta_buf = ctypes.create_unicode_buffer(256)
user32.GetUserObjectInformationW(h_winsta, 2, winsta_buf, 256, ctypes.byref(needed))
print(f"Current Process WindowStation Handle: {h_winsta}, Name: {winsta_buf.value}")

# What desktop does Explorer have?
print("\nChecking Explorer process and windows...")
p = subprocess.run(["tasklist", "/fi", "imagename eq explorer.exe"], capture_output=True, text=True)
print(p.stdout)

# What desktop does Antigravity have?
p = subprocess.run(["tasklist", "/fi", "imagename eq Antigravity IDE.exe"], capture_output=True, text=True)
print(p.stdout)
