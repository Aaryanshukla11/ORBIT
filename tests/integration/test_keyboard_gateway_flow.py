"""Integration tests for WebSocket Gateway keyboard command routing in ORBIT M1.3."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from orbit.adapters.registry import CapabilityRegistry
from orbit.contracts.capabilities import CapabilityHealth, CapabilityHealthStatus, CapabilityType, KeyboardCapability
from orbit.contracts.commands import BaseCommand, CommandType, KeyboardEmergencyReleasePayload, KeyboardKeyPayload, PressShortcutPayload, RecoverKeyboardLockoutPayload, TypeTextPayload
from orbit.contracts.events import EventType, RuntimeEvent
from orbit.gateway.session_manager import SessionManager
from orbit.gateway.websocket_manager import WebSocketConnection, WebSocketManager
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator


from orbit.adapters.base import BaseCapabilityAdapter
from orbit.contracts.capabilities import AdapterMode, CapabilityHealth, CapabilityHealthStatus, CapabilityLifecycleState, CapabilityType, KeyboardCapability

class MockKeyboardCapabilityForGateway(BaseCapabilityAdapter, KeyboardCapability):
    """In-memory test double for KeyboardCapability in gateway routing tests."""

    def __init__(self):
        super().__init__(
            capability_name="MockKeyboard",
            capability_type=CapabilityType.KEYBOARD,
            adapter_mode=AdapterMode.MOCK,
        )
        self._lifecycle_state = CapabilityLifecycleState.READY
        self.typed_text = []
        self.shortcuts = []
        self.keys_down = []
        self.keys_up = []
        self.lockout = "NORMAL"

    async def type_text(self, text: str, delay_ms: float = 2.0, target_hwnd=None):
        self.typed_text.append(text)
        return True

    async def press_shortcut(self, combination: str, target_hwnd=None):
        self.shortcuts.append(combination)
        return True

    async def press_key(self, key_code: str):
        self.keys_down.append(key_code)
        return True

    async def release_key(self, key_code: str):
        self.keys_up.append(key_code)
        return True

    async def emergency_release_all(self):
        self.keys_down.clear()
        return True

    async def get_lockout_state(self):
        return self.lockout

    def recover_locked_state(self, token: str):
        if token == "VALID_TOKEN":
            self.lockout = "NORMAL"
            return True
        return False

    async def get_health(self):
        return CapabilityHealth(
            capability_name="MockKeyboard",
            capability_type=CapabilityType.KEYBOARD,
            adapter_mode=AdapterMode.MOCK,
            lifecycle_state=CapabilityLifecycleState.READY,
            status=CapabilityHealthStatus.HEALTHY,
            message="OK",
        )


@pytest.mark.asyncio
async def test_websocket_gateway_keyboard_command_routing():
    event_bus = EventBus()
    registry = CapabilityRegistry()
    mock_kbd = MockKeyboardCapabilityForGateway()

    registry.register(CapabilityType.KEYBOARD, mock_kbd)
    orchestrator = OrbitOrchestrator(event_bus=event_bus, registry=registry)
    session_manager = SessionManager()
    manager = WebSocketManager(orchestrator=orchestrator, session_manager=session_manager, event_bus=event_bus)

    published_events = []
    event_bus.subscribe(None, lambda evt: published_events.append(evt))

    ws_mock = AsyncMock()
    conn = WebSocketConnection(connection_id="conn-1", session_id="sess-1", websocket=ws_mock)

    # 1. Test TYPE_TEXT
    cmd_type = BaseCommand(command_id="c1", command_type=CommandType.TYPE_TEXT, session_id="sess-1")
    payload_type = TypeTextPayload(text="Hello World", delay_ms=0.0)
    await manager._dispatch_command(conn, cmd_type, payload_type)

    assert mock_kbd.typed_text == ["Hello World"]
    type_evts = [e for e in published_events if e.event_type == EventType.KEYBOARD_TYPED]
    assert len(type_evts) == 1
    assert type_evts[0].payload["char_count"] == 11

    # 2. Test PRESS_SHORTCUT
    cmd_sc = BaseCommand(command_id="c2", command_type=CommandType.PRESS_SHORTCUT, session_id="sess-1")
    payload_sc = PressShortcutPayload(combination="ctrl+s")
    await manager._dispatch_command(conn, cmd_sc, payload_sc)

    assert mock_kbd.shortcuts == ["ctrl+s"]
    sc_evts = [e for e in published_events if e.event_type == EventType.SHORTCUT_EXECUTED]
    assert len(sc_evts) == 1

    # 3. Test KEYBOARD_KEY_DOWN
    cmd_down = BaseCommand(command_id="c3", command_type=CommandType.KEYBOARD_KEY_DOWN, session_id="sess-1")
    payload_down = KeyboardKeyPayload(key_code="shift")
    await manager._dispatch_command(conn, cmd_down, payload_down)

    assert mock_kbd.keys_down == ["shift"]
    down_evts = [e for e in published_events if e.event_type == EventType.KEYBOARD_KEY_STATE_CHANGED and e.payload.get("state") == "DOWN"]
    assert len(down_evts) == 1

    # 4. Test KEYBOARD_KEY_UP
    cmd_up = BaseCommand(command_id="c4", command_type=CommandType.KEYBOARD_KEY_UP, session_id="sess-1")
    payload_up = KeyboardKeyPayload(key_code="shift")
    await manager._dispatch_command(conn, cmd_up, payload_up)

    assert mock_kbd.keys_up == ["shift"]
    up_evts = [e for e in published_events if e.event_type == EventType.KEYBOARD_KEY_STATE_CHANGED and e.payload.get("state") == "UP"]
    assert len(up_evts) == 1

    # 5. Test KEYBOARD_EMERGENCY_RELEASE
    cmd_rel = BaseCommand(command_id="c5", command_type=CommandType.KEYBOARD_EMERGENCY_RELEASE, session_id="sess-1")
    payload_rel = KeyboardEmergencyReleasePayload()
    await manager._dispatch_command(conn, cmd_rel, payload_rel)

    rel_evts = [e for e in published_events if e.event_type == EventType.KEYBOARD_KEY_STATE_CHANGED and e.payload.get("state") == "ALL_RELEASED"]
    assert len(rel_evts) == 1

    # 6. Test RECOVER_KEYBOARD_LOCKOUT
    cmd_rec = BaseCommand(command_id="c6", command_type=CommandType.RECOVER_KEYBOARD_LOCKOUT, session_id="sess-1")
    payload_rec = RecoverKeyboardLockoutPayload(recovery_token="VALID_TOKEN")
    await manager._dispatch_command(conn, cmd_rec, payload_rec)

    rec_evts = [e for e in published_events if e.event_type == EventType.KEYBOARD_LOCKOUT_CHANGED]
    assert len(rec_evts) == 1
    assert rec_evts[0].payload["recovered"] is True
