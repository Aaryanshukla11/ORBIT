"""
Provider Worker Health & Circuit Breaker Manager for ORBIT Prototype D.
Tracks worker thread lifecycles, detects hung COM/UIA operations, manages soft timeouts,
and enforces circuit-breaker quarantine to prevent runaway background worker accumulation.
"""

import threading
import time
from typing import Dict, List, Optional, Tuple, Any
from app_types import ProviderHealthState, WorkerLifecycleRecord


class ProviderWorkerHealthManager:
    """
    Manages provider worker thread health, circuit breakers, and post-timeout exit lifecycles.
    """

    def __init__(self, quarantine_threshold: int = 3):
        self._lock = threading.RLock()
        self.quarantine_threshold = quarantine_threshold

        # Per-provider stats
        self._active_workers: Dict[str, int] = {}
        self._workers_still_active: Dict[str, int] = {}
        self._timed_out_workers: Dict[str, int] = {}
        self._workers_exit_confirmed: Dict[str, int] = {}
        self._consecutive_timeouts: Dict[str, int] = {}
        self._total_timeouts: Dict[str, int] = {}
        self._health_states: Dict[str, ProviderHealthState] = {}

        # Worker lifecycle records: worker_id -> WorkerLifecycleRecord
        self._worker_records: Dict[str, WorkerLifecycleRecord] = {}
        self._worker_counter = 0

    def _ensure_provider(self, provider_name: str):
        if provider_name not in self._health_states:
            self._active_workers[provider_name] = 0
            self._workers_still_active[provider_name] = 0
            self._timed_out_workers[provider_name] = 0
            self._workers_exit_confirmed[provider_name] = 0
            self._consecutive_timeouts[provider_name] = 0
            self._total_timeouts[provider_name] = 0
            self._health_states[provider_name] = ProviderHealthState.HEALTHY

    def is_provider_allowed(self, provider_name: str) -> bool:
        """Returns True if provider is healthy or degraded; False if QUARANTINED."""
        with self._lock:
            self._ensure_provider(provider_name)
            return self._health_states[provider_name] != ProviderHealthState.QUARANTINED

    def get_health_state(self, provider_name: str) -> ProviderHealthState:
        """Returns current health state for the given provider."""
        with self._lock:
            self._ensure_provider(provider_name)
            return self._health_states[provider_name]

    def record_worker_start(self, provider_name: str) -> str:
        """Records that a new worker thread has been spawned."""
        with self._lock:
            self._ensure_provider(provider_name)
            self._worker_counter += 1
            worker_id = f"{provider_name}_w_{self._worker_counter}_{time.perf_counter_ns()}"
            self._active_workers[provider_name] += 1

            self._worker_records[worker_id] = WorkerLifecycleRecord(
                provider_name=provider_name,
                worker_started_ns=time.perf_counter_ns(),
                worker_still_active=True,
                worker_exit_confirmed=False,
            )
            return worker_id

    def record_worker_success(self, provider_name: str, worker_id: str, duration_ms: float):
        """Records clean worker completion."""
        with self._lock:
            self._ensure_provider(provider_name)
            self._active_workers[provider_name] = max(0, self._active_workers[provider_name] - 1)
            self._consecutive_timeouts[provider_name] = 0
            self._health_states[provider_name] = ProviderHealthState.HEALTHY

            rec = self._worker_records.get(worker_id)
            if rec:
                self._worker_records[worker_id] = WorkerLifecycleRecord(
                    provider_name=rec.provider_name,
                    worker_started_ns=rec.worker_started_ns,
                    worker_timeout_declared_ns=rec.worker_timeout_declared_ns,
                    worker_abandoned_ns=rec.worker_abandoned_ns,
                    worker_still_active=False,
                    worker_exit_confirmed=True,
                    worker_exit_after_timeout_ns=rec.worker_exit_after_timeout_ns,
                    provider_quarantine_entered_ns=rec.provider_quarantine_entered_ns,
                    provider_quarantine_released_ns=rec.provider_quarantine_released_ns,
                )

    def record_worker_timeout(self, provider_name: str, worker_id: str, duration_ms: float):
        """Records that a worker exceeded soft timeout and was abandoned."""
        with self._lock:
            self._ensure_provider(provider_name)
            self._active_workers[provider_name] = max(0, self._active_workers[provider_name] - 1)
            self._workers_still_active[provider_name] += 1
            self._timed_out_workers[provider_name] += 1
            self._consecutive_timeouts[provider_name] += 1
            self._total_timeouts[provider_name] += 1

            t_now = time.perf_counter_ns()
            quarantine_entered = None

            if self._consecutive_timeouts[provider_name] >= self.quarantine_threshold:
                self._health_states[provider_name] = ProviderHealthState.QUARANTINED
                quarantine_entered = t_now
            else:
                self._health_states[provider_name] = ProviderHealthState.DEGRADED

            rec = self._worker_records.get(worker_id)
            if rec:
                self._worker_records[worker_id] = WorkerLifecycleRecord(
                    provider_name=rec.provider_name,
                    worker_started_ns=rec.worker_started_ns,
                    worker_timeout_declared_ns=t_now,
                    worker_abandoned_ns=t_now,
                    worker_still_active=True,
                    worker_exit_confirmed=False,
                    provider_quarantine_entered_ns=quarantine_entered,
                )

    def record_worker_exit_after_timeout(self, provider_name: str, worker_id: str):
        """Records that an abandoned worker thread has finally exited."""
        with self._lock:
            self._ensure_provider(provider_name)
            self._workers_still_active[provider_name] = max(0, self._workers_still_active[provider_name] - 1)
            self._workers_exit_confirmed[provider_name] += 1

            t_now = time.perf_counter_ns()
            rec = self._worker_records.get(worker_id)
            quarantine_released = None

            if self._health_states[provider_name] == ProviderHealthState.QUARANTINED:
                # Lifting quarantine conditionally to RECOVERING
                self._health_states[provider_name] = ProviderHealthState.RECOVERING
                self._consecutive_timeouts[provider_name] = 0
                quarantine_released = t_now
            elif self._workers_still_active[provider_name] == 0:
                self._health_states[provider_name] = ProviderHealthState.HEALTHY

            if rec:
                self._worker_records[worker_id] = WorkerLifecycleRecord(
                    provider_name=rec.provider_name,
                    worker_started_ns=rec.worker_started_ns,
                    worker_timeout_declared_ns=rec.worker_timeout_declared_ns,
                    worker_abandoned_ns=rec.worker_abandoned_ns,
                    worker_still_active=False,
                    worker_exit_confirmed=True,
                    worker_exit_after_timeout_ns=t_now,
                    provider_quarantine_entered_ns=rec.provider_quarantine_entered_ns,
                    provider_quarantine_released_ns=quarantine_released,
                )

    def get_summary(self) -> Dict[str, Any]:
        """Returns health summary metrics for all providers."""
        with self._lock:
            summary = {}
            for name, state in self._health_states.items():
                summary[name] = {
                    "health_state": state.value,
                    "active_workers": self._active_workers[name],
                    "workers_still_active": self._workers_still_active[name],
                    "timed_out_workers": self._timed_out_workers[name],
                    "workers_exit_confirmed": self._workers_exit_confirmed[name],
                    "consecutive_timeouts": self._consecutive_timeouts[name],
                    "total_timeouts": self._total_timeouts[name],
                }
            return summary
