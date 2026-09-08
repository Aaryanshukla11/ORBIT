"""In-memory task registry and lifecycle coordinator."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional
from uuid import uuid4

from orbit.contracts.runtime import (
    ErrorDetail,
    ExecutionPlan,
    Task,
    TaskStatus,
)
from orbit.runtime.state_machine import TaskStateMachine

logger = logging.getLogger(__name__)


class TaskManager:
    """Thread-safe task state tracking and lifecycle registry."""

    def __init__(self) -> None:
        self._tasks: Dict[str, Task] = {}
        self._state_machines: Dict[str, TaskStateMachine] = {}
        self._lock = asyncio.Lock()

    async def create_task(
        self,
        session_id: str,
        prompt: str,
        task_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Task:
        """Create and register a new task in CREATED status."""
        tid = task_id or f"task_{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        task = Task(
            task_id=tid,
            session_id=session_id,
            prompt=prompt,
            status=TaskStatus.CREATED,
            created_at=now,
            metadata=metadata or {},
        )
        async with self._lock:
            self._tasks[tid] = task
            self._state_machines[tid] = TaskStateMachine(TaskStatus.CREATED)
        return task

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Fetch task by ID."""
        async with self._lock:
            task = self._tasks.get(task_id)
            return task.model_copy() if task else None

    async def get_active_task_for_session(self, session_id: str) -> Optional[Task]:
        """Fetch the currently active (running/queued/validating) task for a session."""
        active_statuses = {
            TaskStatus.CREATED,
            TaskStatus.QUEUED,
            TaskStatus.VALIDATING,
            TaskStatus.READY,
            TaskStatus.RUNNING,
            TaskStatus.VERIFYING,
            TaskStatus.PAUSED,
        }
        async with self._lock:
            for task in self._tasks.values():
                if task.session_id == session_id and task.status in active_statuses:
                    return task.model_copy()
        return None

    async def list_tasks_for_session(self, session_id: str) -> List[Task]:
        """List all tasks associated with a session."""
        async with self._lock:
            return [
                task.model_copy()
                for task in self._tasks.values()
                if task.session_id == session_id
            ]

    async def update_status(
        self,
        task_id: str,
        target_status: TaskStatus,
        error: Optional[ErrorDetail] = None,
        metadata: Optional[Dict] = None,
    ) -> Task:
        """Update task status via state machine validation."""
        async with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"Task with ID {task_id} not found")

            task = self._tasks[task_id]
            sm = self._state_machines[task_id]
            new_status = sm.transition_to(target_status)
            task.status = new_status

            now = datetime.now(timezone.utc)
            if new_status == TaskStatus.RUNNING and not task.started_at:
                task.started_at = now
            elif new_status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
                task.completed_at = now

            if error:
                task.error = error

            if metadata:
                task.metadata.update(metadata)

            return task.model_copy()

    async def update_metadata(self, task_id: str, metadata: Dict) -> Task:
        """Update metadata on a task."""
        async with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"Task with ID {task_id} not found")
            self._tasks[task_id].metadata.update(metadata)
            return self._tasks[task_id].model_copy()

    async def set_plan(self, task_id: str, plan: ExecutionPlan) -> Task:
        """Attach an execution plan to a task."""
        async with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"Task with ID {task_id} not found")
            task = self._tasks[task_id]
            task.plan = plan
            return task.model_copy()

    async def set_current_step(self, task_id: str, step_index: int) -> Task:
        """Advance active step index."""
        async with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"Task with ID {task_id} not found")
            task = self._tasks[task_id]
            task.current_step_index = step_index
            return task.model_copy()
