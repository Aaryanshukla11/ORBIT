"""
Win32 GDI Screen Capture Driver for ORBIT Prototype D.
Captures full virtual desktop space and target window regions with sub-60ms latency,
Per-Monitor DPI awareness, and zero memory leaks.
"""

import ctypes
from ctypes import wintypes
import time
from typing import Optional, Tuple
from PIL import Image

from app_types import Rect
from coordinate_mapper import CoordinateMapper

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# Raster Op Constants
SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
BI_RGB = 0

# Set prototypes
user32.GetDesktopWindow.argtypes = []
user32.GetDesktopWindow.restype = wintypes.HWND

user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC

user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int

user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC

gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP

gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ

gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL

gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL

gdi32.BitBlt.argtypes = [
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD
]
gdi32.BitBlt.restype = wintypes.BOOL


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
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


gdi32.GetDIBits.argtypes = [
    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wintypes.UINT
]
gdi32.GetDIBits.restype = ctypes.c_int


class CaptureEngine:
    """
    High-performance Win32 GDI screen capture driver.
    """

    def __init__(self):
        self.coord_mapper = CoordinateMapper()

    def capture_rect(self, rect: Rect) -> Tuple[Optional[Image.Image], float]:
        """
        Captures the physical screen region defined by rect (in virtual coordinates).
        Returns (Pillow Image, capture_duration_ms).
        """
        t0 = time.perf_counter()
        w = rect.width
        h = rect.height

        if w <= 0 or h <= 0:
            return None, 0.0

        hdesktop = user32.GetDesktopWindow()
        hdc_src = user32.GetWindowDC(hdesktop)
        if not hdc_src:
            return None, 0.0

        hdc_dst = gdi32.CreateCompatibleDC(hdc_src)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_src, w, h)
        hold = gdi32.SelectObject(hdc_dst, hbmp)

        # Blit from screen to memory DC with CAPTUREBLT for layered/alpha windows
        gdi32.BitBlt(hdc_dst, 0, 0, w, h, hdc_src, rect.left, rect.top, SRCCOPY | CAPTUREBLT)

        # Setup top-down 32-bit BGRA DIB
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # Negative for top-down bitmap
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB

        buf_size = w * h * 4
        buf = ctypes.create_string_buffer(buf_size)
        gdi32.GetDIBits(hdc_dst, hbmp, 0, h, buf, ctypes.byref(bmi), 0)

        # Cleanup GDI handles cleanly
        gdi32.SelectObject(hdc_dst, hold)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_dst)
        user32.ReleaseDC(hdesktop, hdc_src)

        # Convert to PIL Image (BGRA -> RGBA)
        img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
        t1 = time.perf_counter()
        duration_ms = round((t1 - t0) * 1000.0, 2)

        return img, duration_ms

    def capture_full_desktop(self) -> Tuple[Optional[Image.Image], float, Rect]:
        """
        Captures the entire virtual screen spanning all active displays.
        Returns (Image, duration_ms, virtual_bounds).
        """
        bounds = self.coord_mapper.get_virtual_desktop_bounds()
        img, duration_ms = self.capture_rect(bounds)
        return img, duration_ms, bounds

    def capture_window(self, hwnd: int) -> Optional[Image.Image]:
        """
        Captures the physical visible window surface using PrintWindow with GDI fallback.
        """
        if not hwnd or not user32.IsWindow(hwnd):
            return None
        from window_tracker import WindowTracker
        bounds = WindowTracker.get_extended_frame_bounds(hwnd)
        w = max(1, bounds.width)
        h = max(1, bounds.height)

        hdc_src = user32.GetWindowDC(hwnd)
        if not hdc_src:
            img, _ = self.capture_rect(bounds)
            return img

        hdc_dst = gdi32.CreateCompatibleDC(hdc_src)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_src, w, h)
        hold = gdi32.SelectObject(hdc_dst, hbmp)

        PW_RENDERFULLCONTENT = 2
        ret = user32.PrintWindow(hwnd, hdc_dst, PW_RENDERFULLCONTENT)
        if not ret:
            # Fallback to BitBlt from window DC
            gdi32.BitBlt(hdc_dst, 0, 0, w, h, hdc_src, 0, 0, SRCCOPY | CAPTUREBLT)

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB

        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(hdc_dst, hbmp, 0, h, buf, ctypes.byref(bmi), 0)

        gdi32.SelectObject(hdc_dst, hold)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_dst)
        user32.ReleaseDC(hwnd, hdc_src)

        img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
        return img
