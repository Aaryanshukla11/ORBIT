"""Unit tests for TaskManager."""

import pytest

from orbit.contracts.runtime import ExecutionPlan, TaskStatus
from orbit.runtime.task_manager import TaskManager


@pytest.mark.asyncio
async def test_task_manager_create_and_query():
    tm = TaskManager()
    task = await tm.create_task(session_id="sess_01", prompt="Click login button")
    assert task.session_id == "sess_01"
    assert task.prompt == "Click login button"
    assert task.status == TaskStatus.CREATED

    fetched = await tm.get_task(task.task_id)
    assert fetched is not None
    assert fetched.task_id == task.task_id


@pytest.mark.asyncio
async def test_task_manager_status_updates():
    tm = TaskManager()
    task = await tm.create_task(session_id="sess_01", prompt="Open notepad")

    t1 = await tm.update_status(task.task_id, TaskStatus.VALIDATING)
    assert t1.status == TaskStatus.VALIDATING

    t2 = await tm.update_status(task.task_id, TaskStatus.READY)
    assert t2.status == TaskStatus.READY

    t3 = await tm.update_status(task.task_id, TaskStatus.RUNNING)
    assert t3.status == TaskStatus.RUNNING
    assert t3.started_at is not None

    t4 = await tm.update_status(task.task_id, TaskStatus.COMPLETED)
    assert t4.status == TaskStatus.COMPLETED
    assert t4.completed_at is not None


@pytest.mark.asyncio
async def test_task_manager_active_task():
    tm = TaskManager()
    task = await tm.create_task(session_id="sess_active", prompt="Active task")
    await tm.update_status(task.task_id, TaskStatus.VALIDATING)
    await tm.update_status(task.task_id, TaskStatus.READY)
    await tm.update_status(task.task_id, TaskStatus.RUNNING)

    active = await tm.get_active_task_for_session("sess_active")
    assert active is not None
    assert active.task_id == task.task_id

    await tm.update_status(task.task_id, TaskStatus.COMPLETED)
    active_after = await tm.get_active_task_for_session("sess_active")
    assert active_after is None
