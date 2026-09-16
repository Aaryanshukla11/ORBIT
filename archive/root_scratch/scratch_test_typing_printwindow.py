import asyncio
import ctypes
from ctypes import wintypes
import time
import subprocess
from PIL import Image

from orbit.adapters.keyboard.adapter import ProductionKeyboardAdapter
from orbit.runtime.perception.ocr import WindowsNativeOCRProvider

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]

def capture_window_printwindow(hwnd):
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    
    hdc_win = user32.GetWindowDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_win, width, height)
    gdi32.SelectObject(hdc_mem, hbmp)
    
    res = user32.PrintWindow(hwnd, hdc_mem, 2)
    if not res:
        res = user32.PrintWindow(hwnd, hdc_mem, 0)
        
    bmp_info = BITMAPINFO()
    bmp_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmp_info.bmiHeader.biWidth = width
    bmp_info.bmiHeader.biHeight = -height
    bmp_info.bmiHeader.biPlanes = 1
    bmp_info.bmiHeader.biBitCount = 32
    bmp_info.bmiHeader.biCompression = 0
    
    buf = (ctypes.c_ubyte * (width * height * 4))()
    gdi32.GetDIBits(hdc_mem, hbmp, 0, height, ctypes.byref(buf), ctypes.byref(bmp_info), 0)
    
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_win)
    
    img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1)
    return img

async def test_full_typing_and_ocr():
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)
    
    hwnd = user32.FindWindowW(None, "Untitled - Notepad")
    if not hwnd:
        hwnd = user32.FindWindowW("Notepad", None)
    print(f"Notepad HWND: {hwnd}")
    
    # Focus and Click inside client area
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
    
    # Type text using ORBIT production keyboard adapter
    kb = ProductionKeyboardAdapter()
    await kb.initialize()
    res = await kb.type_text("HELLO ORBIT", target_hwnd=hwnd)
    print(f"Typed text result: {res}")
    time.sleep(0.5)
    
    # Capture window via PrintWindow
    img = capture_window_printwindow(hwnd)
    img.save("typed_notepad.png")
    
    # Run WinRT OCR
    ocr = WindowsNativeOCRProvider()
    ocr_res = await ocr.extract_text(img)
    print(f"OCR Status: {ocr_res.status}")
    print(f"OCR Full Text: '{ocr_res.full_text}'")
    print(f"Contains 'HELLO ORBIT': {'HELLO ORBIT' in ocr_res.full_text.upper() or 'HELLO' in ocr_res.full_text.upper()}")
    
    await kb.shutdown()
    proc.terminate()

if __name__ == "__main__":
    asyncio.run(test_full_typing_and_ocr())
