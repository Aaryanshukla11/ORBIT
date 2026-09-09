"""Unit tests for CompositeCapabilityExecutor and ImageGenerationProvider (M1.9 Components 7 & 8)."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from orbit.runtime.capabilities.execution.contracts import (
    CapabilityExecutionRequest,
    StageOutcomeStatus,
)
from orbit.runtime.capabilities.execution.executors.composite_executor import (
    CompositeCapabilityExecutor,
)
from orbit.runtime.capabilities.execution.image_gen_provider import (
    GeneratedImageResult,
    ImageGenerationProvider,
    NullImageGenerationProvider,
)


class MockActiveImageGenProvider(ImageGenerationProvider):
    def __init__(self, succeed: bool = True) -> None:
        self._succeed = succeed

    def is_available(self) -> bool:
        return True

    async def generate_image(self, prompt: str, constraints=None) -> GeneratedImageResult:
        if not self._succeed:
            return GeneratedImageResult(
                success=False,
                error="Model API rate limit or error",
            )
        return GeneratedImageResult(
            success=True,
            image_path="C:\\artifacts\\generated_portrait.png",
            model_id="mock_diffusion_v1",
        )


@pytest.mark.asyncio
async def test_composite_executor_unavailable_without_provider():
    """Null provider reports unavailable and execution fails closed."""
    null_provider = NullImageGenerationProvider()
    mock_keyboard = MagicMock()

    executor = CompositeCapabilityExecutor(
        image_gen_provider=null_provider,
        keyboard=mock_keyboard,
    )
    assert executor.is_available() is False

    req = CapabilityExecutionRequest(
        capability_id="IMAGE_GENERATE_AND_INSERT",
        parameters={"prompt": "portrait of a boy"},
    )
    res = await executor.execute(req)
    assert res.dispatch_success is False
    assert res.execution_success is False
    assert res.failure_code == "CAPABILITY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_composite_executor_sub_stage_failure_fails_closed():
    """Sub-stage 1 failure aborts the entire composite workflow."""
    failing_provider = MockActiveImageGenProvider(succeed=False)
    mock_keyboard = MagicMock()

    executor = CompositeCapabilityExecutor(
        image_gen_provider=failing_provider,
        keyboard=mock_keyboard,
    )
    assert executor.is_available() is True

    req = CapabilityExecutionRequest(
        capability_id="IMAGE_GENERATE_AND_INSERT",
        parameters={"prompt": "portrait of a boy"},
    )
    res = await executor.execute(req)
    assert res.dispatch_success is False
    assert res.execution_success is False
    assert res.failure_code == "IMAGE_GENERATION_FAILED"
    # Keyboard paste was never called
    mock_keyboard.press_key.assert_not_called()


@pytest.mark.asyncio
async def test_composite_executor_success_end_to_end():
    """Successful provider executes all 4 sub-stages and pastes into canvas."""
    active_provider = MockActiveImageGenProvider(succeed=True)
    mock_keyboard = MagicMock()
    mock_keyboard.press_key = AsyncMock()
    mock_keyboard.release_key = AsyncMock()

    executor = CompositeCapabilityExecutor(
        image_gen_provider=active_provider,
        keyboard=mock_keyboard,
    )
    assert executor.is_available() is True

    req = CapabilityExecutionRequest(
        capability_id="IMAGE_GENERATE_AND_INSERT",
        parameters={"prompt": "portrait of a boy"},
    )
    res = await executor.execute(req)
    assert res.dispatch_success is True
    assert res.execution_success is True
    assert res.stage_status == StageOutcomeStatus.DISPATCHED
    assert res.output["image_path"] == "C:\\artifacts\\generated_portrait.png"

    # Verify keyboard paste was executed (Ctrl+V)
    assert mock_keyboard.press_key.call_count >= 2
    assert mock_keyboard.release_key.call_count >= 2
