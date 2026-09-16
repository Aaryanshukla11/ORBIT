"""Unit tests verifying strict fail-closed action dispatch (M1.9 Component 5).

Verifies that unknown actions and missing adapters NEVER return dispatch_success=True.
"""

from unittest.mock import MagicMock
import pytest

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.models import CurrentStateObservation


@pytest.mark.asyncio
async def test_dispatch_missing_pointer_fails_closed():
    """Click action without a PointerCapability fails with REQUIRED_ADAPTER_MISSING."""
    # Loop initialized without pointer adapter
    loop = AgentExecutionLoop(pointer=None, keyboard=None)

    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        parameters={},
    )
    pre_obs = CurrentStateObservation(observation_id="obs_001")

    success, err = await loop._dispatch_physical_action(action, pre_obs)
    assert success is False
    assert "REQUIRED_ADAPTER_MISSING" in err
    assert "PointerCapability" in err


@pytest.mark.asyncio
async def test_dispatch_missing_keyboard_fails_closed():
    """Hotkey action without a KeyboardCapability fails with REQUIRED_ADAPTER_MISSING."""
    loop = AgentExecutionLoop(pointer=None, keyboard=None)

    action = AbstractAction(
        action_type=AbstractActionType.SEND_HOTKEY,
        parameters={"combination": "ctrl+c"},
    )
    pre_obs = CurrentStateObservation(observation_id="obs_001")

    success, err = await loop._dispatch_physical_action(action, pre_obs)
    assert success is False
    assert "REQUIRED_ADAPTER_MISSING" in err
    assert "KeyboardCapability" in err


@pytest.mark.asyncio
async def test_dispatch_unknown_action_type_fails_closed():
    """An unknown action type fails closed with UNKNOWN_ACTION_TYPE."""
    loop = AgentExecutionLoop()

    # Pass an unknown action type value
    mock_action = MagicMock()
    mock_action.action_type = "HYPOTHETICAL_TELEPATHIC_INPUT"
    mock_action.parameters = {}
    mock_action.target = None

    pre_obs = CurrentStateObservation(observation_id="obs_001")

    success, err = await loop._dispatch_physical_action(mock_action, pre_obs)
    assert success is False
    assert "UNKNOWN_ACTION_TYPE" in err
