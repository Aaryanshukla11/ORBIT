"""Unit tests for ExecutionHistoryStore and persistence lifecycle."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import pytest
import tempfile

from orbit.runtime.history.models import (
    CompletionEvidenceRecord,
    ExecutionRecord,
    ExecutionStatus,
    ExecutionStepRecord,
    ReplanAuditRecord,
)
from orbit.runtime.history.store import ExecutionHistoryStore


@pytest.mark.asyncio
async def test_history_store_crud():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "test_history.json"
        store = ExecutionHistoryStore(storage_path=storage_file)

        # 1. Initially empty
        records = await store.list_records()
        assert len(records) == 0

        # 2. Save record
        rec1 = ExecutionRecord(
            task_id="task_123",
            session_id="sess_1",
            goal="Open VS Code and analyze codebase",
            status=ExecutionStatus.RUNNING,
            active_model="qwen2.5-coder:7b",
            model_provider="OLLAMA",
            applications_involved=["Visual Studio Code"],
            steps=[
                ExecutionStepRecord(step_id="s1", name="Locate application", status="COMPLETED"),
                ExecutionStepRecord(step_id="s2", name="Read files", status="ACTIVE"),
            ],
            total_steps=2,
            steps_completed=1,
        )
        await store.save_record(rec1)

        # Verify in-memory and disk
        saved = await store.get_record(rec1.execution_id)
        assert saved is not None
        assert saved.goal == "Open VS Code and analyze codebase"
        assert saved.status == ExecutionStatus.RUNNING

        # Fetch by task ID
        by_task = await store.get_record_by_task_id("task_123")
        assert by_task is not None
        assert by_task.execution_id == rec1.execution_id

        # Update to COMPLETED
        saved.status = ExecutionStatus.COMPLETED
        saved.completed_at = datetime.now(timezone.utc)
        saved.duration_ms = 4500.0
        saved.steps_completed = 2
        await store.save_record(saved)

        # Reload new store instance from disk to verify persistence
        store2 = ExecutionHistoryStore(storage_path=storage_file)
        reloaded = await store2.get_record(rec1.execution_id)
        assert reloaded is not None
        assert reloaded.status == ExecutionStatus.COMPLETED
        assert reloaded.duration_ms == 4500.0


@pytest.mark.asyncio
async def test_history_store_filtering_and_search():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "test_history_filter.json"
        store = ExecutionHistoryStore(storage_path=storage_file)

        rec1 = ExecutionRecord(
            task_id="task_1",
            goal="Open Notepad and write summary",
            status=ExecutionStatus.COMPLETED,
            active_model="qwen2.5-coder:7b",
            applications_involved=["Notepad"],
        )
        rec2 = ExecutionRecord(
            task_id="task_2",
            goal="Search web for Python docs",
            status=ExecutionStatus.FAILED,
            failure_reason="Network timeout",
            active_model="gpt-4o",
            applications_involved=["Microsoft Edge"],
        )
        rec3 = ExecutionRecord(
            task_id="task_3",
            goal="Compile C++ module",
            status=ExecutionStatus.CANCELLED,
            cancellation_reason="Cancelled by operator",
        )

        await store.save_record(rec1)
        await store.save_record(rec2)
        await store.save_record(rec3)

        # Filter by status
        completed = await store.list_records(status_filter="COMPLETED")
        assert len(completed) == 1
        assert completed[0].task_id == "task_1"

        failed = await store.list_records(status_filter="FAILED")
        assert len(failed) == 1
        assert failed[0].task_id == "task_2"

        # Search query
        notepad_match = await store.list_records(search_query="notepad")
        assert len(notepad_match) == 1
        assert notepad_match[0].task_id == "task_1"

        model_match = await store.list_records(search_query="gpt-4o")
        assert len(model_match) == 1
        assert model_match[0].task_id == "task_2"
