"""Desktop Screenshot Perception Observer (Step 3).

Captures live desktop screen frames using native ORBIT observation capabilities
(DXGI desktop duplication with GDI / PIL fallbacks) and extracts base64 encodings.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import io
import logging
from typing import Any, Optional
from uuid import uuid4
from PIL import Image

from orbit.contracts.capabilities import ObservationCapability
from orbit.runtime.perception.models import ScreenshotObservation

logger = logging.getLogger(__name__)


class DesktopScreenshotObserver:
    """Production screenshot observation capture coordinator."""

    def __init__(self, observation_capability: Optional[ObservationCapability] = None) -> None:
        self._observation_cap = observation_capability

    def set_observation_capability(self, cap: ObservationCapability) -> None:
        """Attach or update the underlying ObservationCapability adapter."""
        self._observation_cap = cap

    async def capture(self, include_base64: bool = True, format: str = "jpeg") -> ScreenshotObservation:
        """Capture a fresh desktop screenshot observation."""
        capture_id = f"cap_{uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)

        # 1. Try attached ORBIT ObservationCapability adapter
        if self._observation_cap is not None:
            try:
                frame = await self._observation_cap.capture_screen(display_index=0)
                width = frame.resolution.width if frame.resolution else 1920
                height = frame.resolution.height if frame.resolution else 1080

                b64_str = None
                raw_bytes = None
                if hasattr(frame, "data") and isinstance(frame.data, (bytes, bytearray)) and len(frame.data) > 0:
                    raw_bytes = bytes(frame.data)
                    if include_base64:
                        b64_str = base64.b64encode(raw_bytes).decode("ascii")

                return ScreenshotObservation(
                    capture_id=capture_id,
                    timestamp_utc=now,
                    width=width,
                    height=height,
                    image_base64=b64_str,
                    capture_method="OBSERVATION_CAPABILITY",
                    format=format,
                    raw_bytes=raw_bytes,
                )
            except Exception as cap_err:
                logger.debug("ObservationCapability capture notice: %s; falling back to GDI/PIL", cap_err)

        # 2. Try PIL ImageGrab
        pil_img = None
        capture_method = "PIL_IMAGEGRAB"
        try:
            from PIL import ImageGrab
            pil_img = ImageGrab.grab(all_screens=False)
        except Exception:
            pil_img = None

        # 3. Try Win32 GDI BitBlt
        if pil_img is None:
            pil_img = self._capture_gdi()
            capture_method = "WIN32_GDI"

        if pil_img is not None:
            width, height = pil_img.size
            b64_str = None
            raw_bytes = None
            try:
                buffer = io.BytesIO()
                save_fmt = "JPEG" if format.lower() in ("jpeg", "jpg") else "PNG"
                if pil_img.mode in ("RGBA", "P"):
                    pil_img = pil_img.convert("RGB")
                pil_img.save(buffer, format=save_fmt, quality=85)
                raw_bytes = buffer.getvalue()
                if include_base64:
                    b64_str = base64.b64encode(raw_bytes).decode("ascii")

                return ScreenshotObservation(
                    capture_id=capture_id,
                    timestamp_utc=now,
                    width=width,
                    height=height,
                    image_base64=b64_str,
                    capture_method=capture_method,
                    format=format,
                    raw_bytes=raw_bytes,
                )
            except Exception as enc_err:
                logger.debug("Image encoding notice: %s", enc_err)

        # 4. Safe synthetic fallback observation if display capture is physically unavailable
        return ScreenshotObservation(
            capture_id=capture_id,
            timestamp_utc=now,
            width=1920,
            height=1080,
            image_base64=None,
            capture_method="SYNTHETIC_FALLBACK",
            format=format,
            raw_bytes=None,
        )

    def _capture_gdi(self) -> Optional[Image.Image]:
        """Capture screen using Win32 GDI BitBlt."""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            # SM_XVIRTUALSCREEN = 76, SM_YVIRTUALSCREEN = 77, SM_CXVIRTUALSCREEN = 78, SM_CYVIRTUALSCREEN = 79
            x = user32.GetSystemMetrics(76)
            y = user32.GetSystemMetrics(77)
            w = user32.GetSystemMetrics(78)
            h = user32.GetSystemMetrics(79)
            if w <= 0 or h <= 0:
                w = user32.GetSystemMetrics(0)
                h = user32.GetSystemMetrics(1)
                x, y = 0, 0

            hdesktop = user32.GetDesktopWindow()
            desktop_dc = user32.GetWindowDC(hdesktop)
            mem_dc = gdi32.CreateCompatibleDC(desktop_dc)
            hbitmap = gdi32.CreateCompatibleBitmap(desktop_dc, w, h)
            old_bmp = gdi32.SelectObject(mem_dc, hbitmap)

            # SRCCOPY = 0x00CC0020, CAPTUREBLT = 0x40000000
            gdi32.BitBlt(mem_dc, 0, 0, w, h, desktop_dc, x, y, 0x00CC0020 | 0x40000000)

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

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h  # top-down
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0  # BI_RGB

            buf = ctypes.create_string_buffer(w * h * 4)
            gdi32.GetDIBits(desktop_dc, hbitmap, 0, h, buf, ctypes.byref(bmi), 0)

            # Clean up GDI objects
            gdi32.SelectObject(mem_dc, old_bmp)
            gdi32.DeleteObject(hbitmap)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(hdesktop, desktop_dc)

            img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
            return img.convert("RGB")
        except Exception as ex:
            logger.debug("GDI screenshot capture notice: %s", ex)
            return None
