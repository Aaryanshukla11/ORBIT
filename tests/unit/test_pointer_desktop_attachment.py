"""Unit and diagnostic tests for desktop thread attachment in ORBIT M1.2B."""

import asyncio
import concurrent.futures
import sys
import pytest

from orbit.adapters.pointer.movement import get_live_cursor_position
from orbit.adapters.pointer.safety import ensure_thread_input_desktop


def test_ensure_thread_input_desktop_idempotency():
    """Verify that calling ensure_thread_input_desktop multiple times is safe and idempotent."""
    if sys.platform != "win32":
        pytest.skip("Desktop thread attachment tests require Windows platform")

    # First call attaches thread and closes handle
    res1 = ensure_thread_input_desktop()
    assert res1 is True

    # Second call is idempotent
    res2 = ensure_thread_input_desktop()
    assert res2 is True


def test_threadpool_worker_desktop_attachment():
    """Verify that background ThreadPoolExecutor worker threads attach cleanly."""
    if sys.platform != "win32":
        pytest.skip("Desktop thread attachment tests require Windows platform")

    def worker_task():
        # Ensure thread is attached
        attached = ensure_thread_input_desktop()
        assert attached is True
        x, y = get_live_cursor_position()
        return x, y

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker_task)
        x1, y1 = f1.result()
        assert isinstance(x1, int)
        assert isinstance(y1, int)

        f2 = executor.submit(worker_task)
        x2, y2 = f2.result()
        assert isinstance(x2, int)
        assert isinstance(y2, int)


@pytest.mark.asyncio
async def test_asyncio_to_thread_cursor_readback():
    """Verify that get_live_cursor_position executes cleanly via asyncio.to_thread."""
    if sys.platform != "win32":
        pytest.skip("Desktop thread attachment tests require Windows platform")

    x, y = await asyncio.to_thread(get_live_cursor_position)
    assert isinstance(x, int)
    assert isinstance(y, int)
