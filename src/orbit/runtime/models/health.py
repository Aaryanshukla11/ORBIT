"""Health check evaluation and latency tracking for model runtimes (Milestone M1.9 Step 1).

Measures true network roundtrip latency with microsecond precision and
classifies provider status according to response integrity.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import time
from typing import AsyncGenerator, Optional, Tuple

from orbit.runtime.models.models import (
    ModelProviderKind,
    ProviderHealth,
    ProviderHealthStatus,
)


@asynccontextmanager
async def measure_roundtrip_latency() -> AsyncGenerator[dict, None]:
    """Context manager for measuring true roundtrip latency in milliseconds."""
    timing = {"start_ns": time.perf_counter_ns(), "elapsed_ms": None}
    try:
        yield timing
    finally:
        elapsed_ns = time.perf_counter_ns() - timing["start_ns"]
        timing["elapsed_ms"] = round(elapsed_ns / 1_000_000.0, 3)


class HealthEvaluator:
    """Evaluator that translates raw ping/version responses into typed ProviderHealth."""

    @staticmethod
    def create_healthy(
        provider: ModelProviderKind,
        endpoint: str,
        latency_ms: float,
        version_info: Optional[str] = None,
        diagnostic_message: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> ProviderHealth:
        """Create a HEALTHY or DEGRADED health report based on latency threshold."""
        status = ProviderHealthStatus.HEALTHY
        msg = diagnostic_message or "Provider runtime is healthy and responsive"
        
        # High latency (> 5000ms) marks health as DEGRADED
        if latency_ms > 5000.0:
            status = ProviderHealthStatus.DEGRADED
            msg = f"Elevated latency ({latency_ms:.1f}ms) detected"

        return ProviderHealth(
            provider=provider,
            status=status,
            endpoint=endpoint,
            checked_at_utc=datetime.now(timezone.utc),
            latency_ms=latency_ms,
            diagnostic_message=msg,
            version_info=version_info,
            metadata=metadata or {},
        )

    @staticmethod
    def create_unavailable(
        provider: ModelProviderKind,
        endpoint: str,
        reason: str,
        metadata: Optional[dict] = None,
    ) -> ProviderHealth:
        """Create an UNAVAILABLE health report when connection cannot be established."""
        return ProviderHealth(
            provider=provider,
            status=ProviderHealthStatus.UNAVAILABLE,
            endpoint=endpoint,
            checked_at_utc=datetime.now(timezone.utc),
            latency_ms=None,
            diagnostic_message=reason,
            version_info=None,
            metadata=metadata or {},
        )

    @staticmethod
    def create_error(
        provider: ModelProviderKind,
        endpoint: str,
        error_message: str,
        metadata: Optional[dict] = None,
    ) -> ProviderHealth:
        """Create an ERROR health report when an internal or protocol error occurs."""
        return ProviderHealth(
            provider=provider,
            status=ProviderHealthStatus.ERROR,
            endpoint=endpoint,
            checked_at_utc=datetime.now(timezone.utc),
            latency_ms=None,
            diagnostic_message=error_message,
            version_info=None,
            metadata=metadata or {},
        )
