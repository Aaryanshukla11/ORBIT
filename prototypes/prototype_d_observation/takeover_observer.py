"""
Human Takeover Observation Invalidation Contract for ORBIT Prototype D v1.2.1.
Enforces the Prototype B integration invariant:
HUMAN TAKEOVER -> PAUSE -> INVALIDATE ACTIVE OBSERVATIONS -> FORCED RE-OBSERVATION
"""

import threading
import time
from typing import List, Callable, Optional

from app_types import InvalidationReason
from freshness_tracker import FreshnessTracker


class TakeoverObserver:
    """
    Observes human takeover events and invalidates active desktop observations.
    """

    def __init__(self, freshness_tracker: FreshnessTracker):
        self._lock = threading.RLock()
        self.freshness_tracker = freshness_tracker
        self._takeover_count = 0
        self._last_takeover_ns = 0
        self._listeners: List[Callable[[int, InvalidationReason], None]] = []

    def subscribe(self, listener: Callable[[int, InvalidationReason], None]):
        with self._lock:
            self._listeners.append(listener)

    def on_human_takeover(self, reason: str = "Physical input observed via low-level hook"):
        """
        Invoked when human takeover is signaled by Prototype B or global input hook.
        Immediately increments generation and notifies listeners.
        """
        with self._lock:
            self._takeover_count += 1
            self._last_takeover_ns = time.perf_counter_ns()
            new_gen = self.freshness_tracker.increment_generation(reason=InvalidationReason.USER_TAKEOVER)
            listeners_copy = list(self._listeners)

        for listener in listeners_copy:
            try:
                listener(new_gen, InvalidationReason.USER_TAKEOVER)
            except Exception as e:
                print(f"[TakeoverObserver] Listener exception: {e}")

    @property
    def takeover_count(self) -> int:
        with self._lock:
            return self._takeover_count

    @property
    def last_takeover_ns(self) -> int:
        with self._lock:
            return self._last_takeover_ns
