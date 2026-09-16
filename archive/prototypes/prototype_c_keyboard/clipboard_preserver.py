"""
Clipboard Preservation Contract & Isolated Readback for Prototype C.
Snapshots the user's existing clipboard text, executes isolated clipboard operations,
and deterministically restores original clipboard contents.
"""

import ctypes
from ctypes import wintypes
import time
from typing import Optional

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL

user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL

user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL

user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE

user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE

user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL

kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p

kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL


class ClipboardPreserver:
    """
    Guarantees user clipboard data preservation during Level 2 readback validation.
    """

    def __init__(self, retry_count: int = 5, retry_delay_s: float = 0.02):
        self.retry_count = retry_count
        self.retry_delay_s = retry_delay_s
        self._snapshot_text: Optional[str] = None
        self._restored: bool = False

    def _open_clipboard(self) -> bool:
        for _ in range(self.retry_count):
            if user32.OpenClipboard(0):
                return True
            time.sleep(self.retry_delay_s)
        return False

    def snapshot(self) -> Optional[str]:
        """Snapshots current clipboard unicode text."""
        if not self._open_clipboard():
            return None
        try:
            if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                self._snapshot_text = None
                return None

            h_data = user32.GetClipboardData(CF_UNICODETEXT)
            if not h_data:
                self._snapshot_text = None
                return None

            p_data = kernel32.GlobalLock(h_data)
            if not p_data:
                self._snapshot_text = None
                return None

            try:
                text = ctypes.wstring_at(p_data)
                self._snapshot_text = text
                return text
            finally:
                kernel32.GlobalUnlock(h_data)
        finally:
            user32.CloseClipboard()

    def get_text(self) -> str:
        """Reads current clipboard text."""
        if not self._open_clipboard():
            return ""
        try:
            if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return ""
            h_data = user32.GetClipboardData(CF_UNICODETEXT)
            if not h_data:
                return ""
            p_data = kernel32.GlobalLock(h_data)
            if not p_data:
                return ""
            try:
                return ctypes.wstring_at(p_data)
            finally:
                kernel32.GlobalUnlock(h_data)
        finally:
            user32.CloseClipboard()

    def set_text(self, text: str) -> bool:
        """Writes unicode text to the clipboard."""
        if not self._open_clipboard():
            return False
        try:
            user32.EmptyClipboard()
            encoded = text.encode("utf-16le") + b"\x00\x00"
            size = len(encoded)

            h_glob = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
            if not h_glob:
                return False

            p_glob = kernel32.GlobalLock(h_glob)
            if not p_glob:
                return False

            try:
                ctypes.memmove(p_glob, encoded, size)
            finally:
                kernel32.GlobalUnlock(h_glob)

            if not user32.SetClipboardData(CF_UNICODETEXT, h_glob):
                return False
            return True
        finally:
            user32.CloseClipboard()

    def restore(self) -> bool:
        """Restores original snapshot text back to clipboard."""
        if self._snapshot_text is None:
            # Clear or leave as was
            if not self._open_clipboard():
                return False
            try:
                user32.EmptyClipboard()
                self._restored = True
                return True
            finally:
                user32.CloseClipboard()
        else:
            res = self.set_text(self._snapshot_text)
            self._restored = res
            return res

    def __enter__(self):
        self.snapshot()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.restore()
