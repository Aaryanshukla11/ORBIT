import asyncio
import io
import time
import subprocess
import ctypes
from ctypes import wintypes
from PIL import Image

from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.keyboard.adapter import ProductionKeyboardAdapter
from orbit.runtime.perception.engine import SemanticPerceptionEngine

user32 = ctypes.windll.user32

async def inspect_ocr():
    # Launch notepad
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)
    
    hwnd = user32.FindWindowW(None, "Untitled - Notepad")
    if not hwnd:
        hwnd = user32.FindWindowW("Notepad", None)
    print(f"Notepad HWND: {hwnd}")
    
    # Focus and Click
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    center_x = (rect.left + rect.right) // 2
    center_y = (rect.top + rect.bottom) // 2
    user32.SetCursorPos(center_x, center_y)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.2)
    
    # Type
    kb = ProductionKeyboardAdapter()
    await kb.initialize()
    await kb.type_text("HELLO ORBIT", target_hwnd=hwnd)
    time.sleep(0.5)
    
    # Capture screen
    obs = ProductionObservationAdapter()
    await obs.initialize()
    snapshot = await obs.capture_snapshot()
    frame = await obs.capture_screen(0)
    post_image = Image.open(io.BytesIO(frame.raw_bytes))
    post_image.save("captured_desktop.png")
    
    # Also check cropped image around Notepad window rect
    crop_bbox = (rect.left, rect.top, rect.right, rect.bottom)
    cropped_img = post_image.crop(crop_bbox)
    cropped_img.save("captured_notepad.png")
    print(f"Saved captured_desktop.png ({post_image.size}) and captured_notepad.png ({cropped_img.size})")
    perception = SemanticPerceptionEngine()
    cropped_ocr = await perception.extract_text_from_image(cropped_img)
    print(f"Cropped OCR Status: {cropped_ocr.status}")
    print(f"Cropped OCR Full Text: '{cropped_ocr.full_text}'")
    
    await kb.shutdown()
    await obs.shutdown()
    proc.terminate()

if __name__ == "__main__":
    asyncio.run(inspect_ocr())
