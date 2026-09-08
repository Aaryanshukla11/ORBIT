import subprocess
import time

print("Launching mspaint...")
p = subprocess.Popen(["mspaint.exe"])
time.sleep(3)

out = subprocess.run(["tasklist"], capture_output=True, text=True)
for line in out.stdout.splitlines():
    if "paint" in line.lower() or "mspaint" in line.lower():
        print("FOUND:", line)

subprocess.run("taskkill /f /im mspaint.exe", shell=True, capture_output=True)
subprocess.run("taskkill /f /im PaintApp.exe", shell=True, capture_output=True)
