"""Thread-safe persistent execution history store backed by JSON."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from orbit.runtime.history.models import (
    ExecutionRecord,
    ExecutionStatus,
    ExecutionStepRecord,
    ReplanAuditRecord,
    CompletionEvidenceRecord,
)

logger = logging.getLogger(__name__)


class ExecutionHistoryStore:
    """Persistent storage for ORBIT task execution records."""

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        max_records: int = 500,
    ) -> None:
        if storage_path is None:
            orbit_dir = Path.home() / ".orbit"
            orbit_dir.mkdir(parents=True, exist_ok=True)
            self._storage_path = orbit_dir / "execution_history.json"
        else:
            self._storage_path = storage_path
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        self._max_records = max_records
        self._records: Dict[str, ExecutionRecord] = {}  # execution_id -> ExecutionRecord
        self._task_id_to_exec_id: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._load_from_disk()

    @property
    def storage_path(self) -> Path:
        return self._storage_path

    def _load_from_disk(self) -> None:
        """Synchronously load persisted records from disk at initialization."""
        if not self._storage_path.exists():
            return

        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        try:
                            rec = ExecutionRecord.model_validate(item)
                            self._records[rec.execution_id] = rec
                            self._task_id_to_exec_id[rec.task_id] = rec.execution_id
                        except Exception as parse_err:
                            logger.warning("Skipping corrupted execution record: %s", parse_err)
            logger.info("Loaded %d historical execution records from %s", len(self._records), self._storage_path)
        except Exception as e:
            logger.error("Failed to load execution history from %s: %s", self._storage_path, e)

    def _save_to_disk_sync(self) -> None:
        """Atomic write to disk using temporary file replacement."""
        try:
            tmp_path = self._storage_path.with_suffix(".tmp")
            records_list = [
                rec.model_dump(mode="json")
                for rec in sorted(self._records.values(), key=lambda r: r.started_at, reverse=True)
            ][:self._max_records]

            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(records_list, f, indent=2, default=str)

            os.replace(tmp_path, self._storage_path)
        except Exception as e:
            logger.error("Failed to save execution history to %s: %s", self._storage_path, e)

    async def save_record(self, record: ExecutionRecord) -> None:
        """Upsert an execution record and persist to disk asynchronously."""
        async with self._lock:
            # Enforce max record count
            self._records[record.execution_id] = record
            self._task_id_to_exec_id[record.task_id] = record.execution_id

            if len(self._records) > self._max_records:
                sorted_keys = sorted(
                    self._records.keys(),
                    key=lambda k: self._records[k].started_at,
                )
                to_remove = sorted_keys[: len(self._records) - self._max_records]
                for k in to_remove:
                    rec = self._records.pop(k, None)
                    if rec:
                        self._task_id_to_exec_id.pop(rec.task_id, None)

            # Persist in worker thread to avoid blocking event loop
            await asyncio.to_thread(self._save_to_disk_sync)

    async def get_record(self, execution_id: str) -> Optional[ExecutionRecord]:
        """Fetch record by execution ID."""
        async with self._lock:
            rec = self._records.get(execution_id)
            return rec.model_copy() if rec else None

    async def get_record_by_task_id(self, task_id: str) -> Optional[ExecutionRecord]:
        """Fetch record by associated task ID."""
        async with self._lock:
            exec_id = self._task_id_to_exec_id.get(task_id)
            if exec_id and exec_id in self._records:
                return self._records[exec_id].model_copy()
            return None

    async def list_records(
        self,
        limit: int = 50,
        status_filter: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> List[ExecutionRecord]:
        """Query historical execution records with filtering and search."""
        async with self._lock:
            records = list(self._records.values())

        # Sort newest first
        records.sort(key=lambda r: r.started_at, reverse=True)

        if status_filter and status_filter.upper() != "ALL":
            records = [r for r in records if r.status.value.upper() == status_filter.upper()]

        if search_query and search_query.strip():
            q = search_query.strip().lower()
            filtered = []
            for r in records:
                in_goal = q in r.goal.lower()
                in_model = bool(r.active_model and q in r.active_model.lower())
                in_apps = any(q in app.lower() for app in r.applications_involved)
                in_status = q in r.status.value.lower()
                if in_goal or in_model or in_apps or in_status:
                    filtered.append(r)
            records = filtered

        return [r.model_copy() for r in records[:limit]]

    async def clear_history(self) -> None:
        """Clear all historical records."""
        async with self._lock:
            self._records.clear()
            self._task_id_to_exec_id.clear()
            await asyncio.to_thread(self._save_to_disk_sync)
