"""Unit tests for CapabilityExecutorRegistry (M1.9 Component 2)."""

from unittest.mock import MagicMock
import pytest

from orbit.runtime.capabilities.execution.contracts import (
    CapabilityExecutionRequest,
    CapabilityExecutionResult,
    CapabilityExecutor,
    StageOutcomeStatus,
)
from orbit.runtime.capabilities.execution.executor_registry import CapabilityExecutorRegistry
from orbit.runtime.capabilities.models import Capability, CapabilityCategory
from orbit.runtime.capabilities.registry import CapabilityRegistry


class DummyMockExecutor(CapabilityExecutor):
    def __init__(self, cid: str, available: bool = True) -> None:
        super().__init__(capability_id=cid)
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def validate_inputs(self, parameters):
        return True, None

    async def execute(self, request):
        return CapabilityExecutionResult(
            capability_id=self.capability_id,
            stage_index=request.stage_index,
            dispatch_success=True,
            execution_success=True,
            stage_status=StageOutcomeStatus.EFFECT_VERIFIED,
        )


def test_executor_registry_registration_and_lookup():
    """Registering an executor maps directly to the capability ID."""
    reg = CapabilityExecutorRegistry()
    executor = DummyMockExecutor("TEST_CAPABILITY", available=True)
    reg.register_executor(executor)

    resolved = reg.get_executor("TEST_CAPABILITY")
    assert resolved is executor
    assert reg.get_executor("NON_EXISTENT") is None


def test_executor_registry_is_executable_requires_all_prerequisites():
    """is_executable returns True only when metadata exists, is available, and executor is operational."""
    cap_registry = CapabilityRegistry(register_defaults=False)
    # 1. Register capability in metadata
    cap_registry.register(
        Capability(
            capability_id="DUMMY_CAP",
            name="Dummy",
            description="Dummy",
            category=CapabilityCategory.DESKTOP_CONTROL,
            is_available=True,
        )
    )

    exec_registry = CapabilityExecutorRegistry(capability_registry=cap_registry)

    # Missing executor -> NOT executable
    assert exec_registry.is_executable("DUMMY_CAP") is False

    # Unavailable executor (e.g. missing adapter) -> NOT executable
    unavailable_exec = DummyMockExecutor("DUMMY_CAP", available=False)
    exec_registry.register_executor(unavailable_exec)
    assert exec_registry.is_executable("DUMMY_CAP") is False

    # Available executor -> IS executable
    available_exec = DummyMockExecutor("DUMMY_CAP", available=True)
    exec_registry.register_executor(available_exec)
    assert exec_registry.is_executable("DUMMY_CAP") is True


def test_default_executor_registry_wiring():
    """Factory create_default wires standard production executors."""
    mock_pointer = MagicMock()
    mock_keyboard = MagicMock()
    mock_workspace = MagicMock()

    reg = CapabilityExecutorRegistry.create_default(
        workspace=mock_workspace,
        pointer=mock_pointer,
        keyboard=mock_keyboard,
    )

    # Core capabilities must have registered executors
    assert reg.get_executor("LAUNCH_APPLICATION") is not None
    assert reg.get_executor("FOCUS_WINDOW") is not None
    assert reg.get_executor("CLICK_ELEMENT") is not None
    assert reg.get_executor("TYPE_TEXT") is not None
    assert reg.get_executor("DRAW_BASIC_GEOMETRY") is not None
    assert reg.get_executor("CLIPBOARD_PASTE") is not None
    assert reg.get_executor("IMAGE_GENERATE_AND_INSERT") is not None

    # Availability reflects adapter presence
    assert reg.get_executor("TYPE_TEXT").is_available() is True
    assert reg.get_executor("CLICK_ELEMENT").is_available() is True

    # Image gen has no active provider by default -> reports unavailable
    assert reg.get_executor("IMAGE_GENERATE_AND_INSERT").is_available() is False
