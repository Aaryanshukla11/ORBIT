"""
Standalone, decoupled cancellation interface contract for ORBIT keyboard interaction.
Provides versioned cancellation abstractions without runtime coupling to Prototype B or main Core.
"""

import threading
import time
from typing import List, Callable, Optional
from app_types import CancellationSource, CancellationRequest


class ICancellationSink:
    """
    Interface implemented by keyboard execution engines to receive cancellation signals.
    """

    def request_cancellation(self, request: CancellationRequest) -> bool:
        """
        Signals immediate cancellation of the active keyboard operation.
        Returns True if a session was actively running and cancellation was posted; False otherwise.
        """
        raise NotImplementedError


class CancellationCoordinator(ICancellationSink):
    """
    Thread-safe cancellation dispatcher coordinating cancellation sources and sinks.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._sinks: List[ICancellationSink] = []
        self._cancel_event = threading.Event()
        self._active_request: Optional[CancellationRequest] = None
        self._callbacks: List[Callable[[CancellationRequest], None]] = []

    def register_sink(self, sink: ICancellationSink):
        with self._lock:
            if sink not in self._sinks:
                self._sinks.append(sink)

    def unregister_sink(self, sink: ICancellationSink):
        with self._lock:
            if sink in self._sinks:
                self._sinks.remove(sink)

    def subscribe_cancellation(self, callback: Callable[[CancellationRequest], None]):
        with self._lock:
            self._callbacks.append(callback)

    def request_cancellation(self, request: CancellationRequest) -> bool:
        with self._lock:
            self._active_request = request
            self._cancel_event.set()
            sinks_copy = list(self._sinks)
            callbacks_copy = list(self._callbacks)

        dispatched_any = False
        for sink in sinks_copy:
            try:
                if sink.request_cancellation(request):
                    dispatched_any = True
            except Exception as e:
                print(f"[CancellationCoordinator] Sink error: {e}")

        for cb in callbacks_copy:
            try:
                cb(request)
            except Exception as e:
                print(f"[CancellationCoordinator] Callback error: {e}")

        return dispatched_any

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @property
    def active_request(self) -> Optional[CancellationRequest]:
        with self._lock:
            return self._active_request

    def reset(self):
        with self._lock:
            self._cancel_event.clear()
            self._active_request = None
