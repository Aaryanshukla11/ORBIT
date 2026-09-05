"""Unit tests for cancellation tokens and sources."""

import asyncio
import pytest

from orbit.runtime.cancellation import CancellationSource, CancellationToken


def test_cancellation_source_direct():
    source = CancellationSource()
    token = source.token

    assert not token.is_cancelled
    assert token.reason is None

    source.cancel("Test reason")

    assert token.is_cancelled
    assert token.reason == "Test reason"


def test_cancellation_callback_fired():
    source = CancellationSource()
    token = source.token
    fired = []

    token.register_callback(lambda: fired.append(True))
    assert len(fired) == 0

    source.cancel("Abort")
    assert len(fired) == 1

    # Registering after cancellation should immediately fire
    token.register_callback(lambda: fired.append(True))
    assert len(fired) == 2


def test_hierarchical_cancellation_propagation():
    parent_source = CancellationSource()
    parent_token = parent_source.token

    child_source = CancellationSource(parent=parent_token)
    child_token = child_source.token

    assert not child_token.is_cancelled

    parent_source.cancel("Parent cancelled")
    assert child_token.is_cancelled
    assert "Parent cancellation" in child_token.reason


@pytest.mark.asyncio
async def test_wait_cancelled_async():
    source = CancellationSource()
    token = source.token

    async def cancel_later():
        await asyncio.sleep(0.02)
        source.cancel("Delayed cancel")

    asyncio.create_task(cancel_later())
    await token.wait_cancelled()
    assert token.is_cancelled
