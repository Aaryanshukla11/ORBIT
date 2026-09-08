import subprocess
import time

print("1. Testing subprocess.run(['where', 'notepad'])...")
p = subprocess.run(["where", "notepad"], capture_output=True, text=True)
print(p.stdout)

print("2. Starting notepad.exe and polling its returncode / status...")
proc = subprocess.Popen(["notepad.exe"])
for i in range(10):
    ret = proc.poll()
    print(f"  Second {i}: poll() = {ret}")
    if ret is not None:
        print(f"Notepad exited with return code: {ret}")
        break
    time.sleep(1)

print("\n3. Checking tasklist for any notepad...")
p = subprocess.run(["tasklist", "/fi", "imagename eq *notepad*"], capture_output=True, text=True)
print(p.stdout)

subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
