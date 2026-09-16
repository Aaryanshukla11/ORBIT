import ctypes
from ctypes import wintypes
import time
import subprocess
from PIL import Image

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
    
    # PW_RENDERFULLCONTENT = 0x00000002
    res = user32.PrintWindow(hwnd, hdc_mem, 2)
    if not res:
        res = user32.PrintWindow(hwnd, hdc_mem, 0)
        
    bmp_info = BITMAPINFO()
    bmp_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmp_info.bmiHeader.biWidth = width
    bmp_info.bmiHeader.biHeight = -height # top-down
    bmp_info.bmiHeader.biPlanes = 1
    bmp_info.bmiHeader.biBitCount = 32
    bmp_info.bmiHeader.biCompression = 0
    
    buf = (ctypes.c_ubyte * (width * height * 4))()
    gdi32.GetDIBits(hdc_mem, hbmp, 0, height, ctypes.byref(buf), ctypes.byref(bmp_info), 0)
    
    # Cleanup
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_win)
    
    # Convert BGRA to RGB
    img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1)
    return img

async def test_printwindow_ocr():
    import asyncio
    from orbit.runtime.perception.ocr import WindowsNativeOCRProvider
    
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    
    hwnd = user32.FindWindowW(None, "Untitled - Notepad")
    if not hwnd:
        hwnd = user32.FindWindowW("Notepad", None)
    print(f"Notepad HWND: {hwnd}")
    
    img = capture_window_printwindow(hwnd)
    img.save("printwindow_notepad.png")
    print(f"Saved printwindow_notepad.png: {img.size}")
    
    ocr = WindowsNativeOCRProvider()
    ocr_res = await ocr.extract_text(img)
    print(f"PrintWindow OCR Status: {ocr_res.status}")
    print(f"PrintWindow OCR Text: '{ocr_res.full_text}'")
    
    proc.terminate()

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_printwindow_ocr())
