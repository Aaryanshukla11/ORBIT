"""Hierarchical cooperative cancellation tokens and sources."""

from __future__ import annotations

import asyncio
import threading
from typing import Callable, List, Optional


class CancellationToken:
    """Read-only cancellation token that can be polled or awaited."""

    def __init__(self, source: CancellationSource) -> None:
        self._source = source

    @property
    def is_cancelled(self) -> bool:
        """Return True if cancellation has been requested."""
        return self._source.is_cancelled

    @property
    def reason(self) -> Optional[str]:
        """Return cancellation reason if cancelled."""
        return self._source.reason

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be invoked when cancelled."""
        self._source.register_callback(callback)

    async def wait_cancelled(self) -> None:
        """Asynchronously wait until cancellation is triggered."""
        await self._source.wait_cancelled()


class CancellationSource:
    """Controller that can request cancellation and issue child tokens."""

    def __init__(self, parent: Optional[CancellationToken] = None) -> None:
        self._cancelled: bool = False
        self._reason: Optional[str] = None
        self._callbacks: List[Callable[[], None]] = []
        self._event = asyncio.Event()
        self._lock = threading.Lock()

        if parent:
            parent.register_callback(self._on_parent_cancelled)

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    @property
    def reason(self) -> Optional[str]:
        return self._reason

    @property
    def token(self) -> CancellationToken:
        return CancellationToken(self)

    def cancel(self, reason: str = "Operation cancelled") -> None:
        """Trigger cancellation atomically."""
        with self._lock:
            if self._cancelled:
                return
            self._cancelled = True
            self._reason = reason

        # Fire async event in loop if loop is running
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(self._event.set)
        except RuntimeError:
            self._event.set()

        # Fire registered callbacks
        for cb in list(self._callbacks):
            try:
                cb()
            except Exception:
                pass

    def _on_parent_cancelled(self) -> None:
        self.cancel(reason="Parent cancellation requested")

    def register_callback(self, callback: Callable[[], None]) -> None:
        with self._lock:
            if self._cancelled:
                try:
                    callback()
                except Exception:
                    pass
                return
            self._callbacks.append(callback)

    async def wait_cancelled(self) -> None:
        if self._cancelled:
            return
        await self._event.wait()
