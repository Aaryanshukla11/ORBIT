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

async def test_child_windows_and_typing():
    from orbit.runtime.perception.ocr import WindowsNativeOCRProvider
    
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    
    hwnd = user32.FindWindowW(None, "Untitled - Notepad")
    if not hwnd:
        hwnd = user32.FindWindowW("Notepad", None)
    print(f"Notepad HWND: {hwnd}")
    
    # Enumerate child windows
    children = []
    def enum_cb(h, l):
        buf_c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf_c, 256)
        buf_t = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, buf_t, 256)
        children.append((h, buf_c.value, buf_t.value))
        return 1
        
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    cb = WNDENUMPROC(enum_cb)
    user32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
    user32.EnumChildWindows.restype = wintypes.BOOL
    user32.EnumChildWindows(hwnd, cb, 0)
    
    print("Notepad Child Windows:")
    for h, cls, txt in children:
        print(f"  Child HWND: {h}, Class: '{cls}', Text: '{txt}'")
        
    # Find edit / RichEdit child
    edit_hwnd = next((h for h, cls, _ in children if "edit" in cls.lower() or "rich" in cls.lower()), None)
    print(f"Target Edit HWND: {edit_hwnd}")
    
    # Send characters
    target = edit_hwnd or hwnd
    user32.SetForegroundWindow(hwnd)
    user32.SetFocus(target)
    
    WM_CHAR = 0x0102
    for c in "HELLO ORBIT":
        user32.SendMessageW(target, WM_CHAR, ord(c), 0)
        time.sleep(0.02)
        
    time.sleep(0.5)
    
    # Capture & OCR
    img = capture_window_printwindow(hwnd)
    img.save("child_typed_notepad.png")
    
    ocr = WindowsNativeOCRProvider()
    ocr_res = await ocr.extract_text(img)
    print(f"OCR Full Text: '{ocr_res.full_text}'")
    print(f"Contains 'HELLO ORBIT': {'HELLO ORBIT' in ocr_res.full_text.upper()}")
    
    proc.terminate()

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_child_windows_and_typing())
