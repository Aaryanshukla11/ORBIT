import asyncio
import ctypes
from ctypes import wintypes
import time
import subprocess
import os

from orbit.runtime.perception.ocr import WindowsNativeOCRProvider

user32 = ctypes.windll.user32

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

class INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]
    _anonymous_ = ("_union",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_union", _INPUT_UNION),
    ]

def send_unicode(char):
    code = ord(char)
    inp1 = INPUT(type=1)
    inp1.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=0x0004, time=0, dwExtraInfo=0)
    inp2 = INPUT(type=1)
    inp2.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=0x0004 | 0x0002, time=0, dwExtraInfo=0)
    arr = (INPUT * 2)(inp1, inp2)
    user32.SendInput(2, arr, ctypes.sizeof(INPUT))

async def test_ocr_and_typing():
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    
    hwnd = user32.FindWindowW(None, "Untitled - Notepad")
    if not hwnd:
        hwnd = user32.FindWindowW("Notepad", None)
    print(f"Notepad hwnd: {hwnd}")
    
    # Focus and Click
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    center_x = (rect.left + rect.right) // 2
    center_y = (rect.top + rect.bottom) // 2
    
    VK_MENU = 0x12
    KEYEVENTF_KEYUP = 0x0002
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.2)
    
    user32.SetCursorPos(center_x, center_y)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.3)
    
    # Type 'HELLO ORBIT'
    for c in "HELLO ORBIT":
        send_unicode(c)
        time.sleep(0.03)
        
    time.sleep(1.0)
    
    # Take screenshot and run WindowsNativeOCRProvider
    from PIL import ImageGrab
    bbox = (rect.left, rect.top, rect.right, rect.bottom)
    screenshot = ImageGrab.grab(bbox=bbox)
    screenshot.save("notepad_screenshot.png")
    print(f"Saved screenshot: {screenshot.size}")
    
    ocr = WindowsNativeOCRProvider()
    ocr_res = await ocr.recognize_text(screenshot)
    print(f"OCR Recognized Text: '{ocr_res.full_text}'")
    print(f"Contains 'HELLO ORBIT': {'HELLO ORBIT' in ocr_res.full_text}")
    
    proc.terminate()

if __name__ == "__main__":
    asyncio.run(test_ocr_and_typing())
