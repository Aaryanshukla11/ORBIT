"""Mock capability adapters for testing and synthetic execution."""

from orbit.adapters.mocks.mock_keyboard import MockKeyboardAdapter
from orbit.adapters.mocks.mock_observation import MockObservationAdapter
from orbit.adapters.mocks.mock_pointer import MockPointerAdapter
from orbit.adapters.mocks.mock_safety import MockSafetyCoordinator
from orbit.adapters.mocks.mock_takeover import MockHumanTakeoverAdapter
from orbit.adapters.mocks.mock_workspace import MockWorkspaceAdapter

__all__ = [
    "MockHumanTakeoverAdapter",
    "MockKeyboardAdapter",
    "MockObservationAdapter",
    "MockPointerAdapter",
    "MockSafetyCoordinator",
    "MockWorkspaceAdapter",
]
