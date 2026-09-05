"""Deterministic clock interfaces and implementations."""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Protocol


class Clock(Protocol):
    """Protocol for system time and monotonic timing."""

    def now_utc(self) -> datetime:
        """Return current datetime in UTC timezone."""
        ...

    def monotonic(self) -> float:
        """Return monotonic clock value in seconds."""
        ...

    def monotonic_ns(self) -> int:
        """Return monotonic clock value in nanoseconds."""
        ...


class SystemClock:
    """Standard production clock using host system clocks."""

    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()


class FrozenClock:
    """Test clock that can be stepped deterministically."""

    def __init__(self, initial_utc: datetime | None = None, initial_monotonic: float = 1000.0):
        self._current_utc = initial_utc or datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
        self._current_monotonic = initial_monotonic

    def now_utc(self) -> datetime:
        return self._current_utc

    def monotonic(self) -> float:
        return self._current_monotonic

    def monotonic_ns(self) -> int:
        return int(self._current_monotonic * 1_000_000_000)

    def advance(self, seconds: float) -> None:
        self._current_monotonic += seconds
        # Also advance UTC accordingly
        from datetime import timedelta
        self._current_utc += timedelta(seconds=seconds)
