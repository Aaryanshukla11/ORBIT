"""WebSocket connection manager with backpressure-aware outbound queues."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import inspect
import logging
from typing import Any, Dict, Optional, Union
from uuid import uuid4
from fastapi import WebSocket, WebSocketDisconnect

from orbit.contracts.commands import (
    AuthorizeActionPayload,
    BaseCommand,
    CancelTaskPayload,
    ClickPointerPayload,
    CommandType,
    HeartbeatPayload,
    KeyboardEmergencyReleasePayload,
    KeyboardKeyPayload,
    MovePointerPayload,
    PauseTaskPayload,
    PointerButtonPayload,
    PointerEmergencyReleasePayload,
    PressShortcutPayload,
    RecoverKeyboardLockoutPayload,
    RecoverLockedPayload,
    RecoverPointerLockoutPayload,
    ReleaseTakeoverPayload,
    RequestFramePayload,
    ResumeTaskPayload,
    SubmitTaskPayload,
    TriggerTakeoverPayload,
    TypeTextPayload,
)
from orbit.contracts.capabilities import (
    CapabilityType,
    KeyboardCapability,
    PointerCapability,
    WorkspaceCapability,
)
from orbit.contracts.runtime import SystemState

from orbit.contracts.events import (
    ErrorEventPayload,
    EventType,
    RuntimeEvent,
)
from orbit.contracts.sessions import DisconnectionPolicy
from orbit.gateway.protocol import (
    ProtocolError,
    pack_binary_frame,
    parse_inbound_message,
    serialize_outbound_event,
)
from orbit.gateway.session_manager import SessionManager
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator

logger = logging.getLogger(__name__)


class CommandSafetyError(RuntimeError):
    """Raised when an inbound gateway command violates safety boundaries or workspace geometry."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class WebSocketConnection:
    """Represents a single active client WebSocket connection with outbound FIFO queue."""

    def __init__(
        self,
        connection_id: str,
        session_id: str,
        websocket: WebSocket,
        max_queue_size: int = 1000,
    ) -> None:
        self.connection_id = connection_id
        self.session_id = session_id
        self.websocket = websocket
        self.outbound_queue: asyncio.Queue[Union[str, bytes]] = asyncio.Queue(maxsize=max_queue_size)
        self.send_task: Optional[asyncio.Task] = None
        self.closed = False

    async def start_sender(self) -> None:
        """Background task sending queued messages over the WebSocket."""
        try:
            while not self.closed:
                msg = await self.outbound_queue.get()
                if self.closed:
                    break
                if isinstance(msg, bytes):
                    await self.websocket.send_bytes(msg)
                else:
                    await self.websocket.send_text(msg)
                self.outbound_queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Error in WebSocket outbound sender (%s): %s", self.connection_id, e)
        finally:
            self.closed = True

    async def enqueue_message(self, msg: Union[str, bytes]) -> None:
        if self.closed:
            return
        try:
            self.outbound_queue.put_nowait(msg)
        except asyncio.QueueFull:
            logger.error("Outbound queue full for connection %s; dropping event", self.connection_id)


class WebSocketManager:
    """Manages active WebSockets, routes events from EventBus, and dispatches commands."""

    def __init__(
        self,
        orchestrator: OrbitOrchestrator,
        session_manager: SessionManager,
        event_bus: EventBus,
    ) -> None:
        self._orchestrator = orchestrator
        self._session_manager = session_manager
        self._event_bus = event_bus
        self._connections: Dict[str, WebSocketConnection] = {}
        self._session_to_conn: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._unsubscribe_bus = None

    def initialize(self) -> None:
        """Subscribe to runtime event bus to forward events to connected clients."""
        self._unsubscribe_bus = self._event_bus.subscribe(None, self._on_bus_event)

    async def shutdown(self) -> None:
        """Close all active WebSocket connections."""
        if self._unsubscribe_bus:
            self._unsubscribe_bus()

        async with self._lock:
            for conn in list(self._connections.values()):
                conn.closed = True
                if conn.send_task:
                    conn.send_task.cancel()
                try:
                    await conn.websocket.close(code=1001, reason="Server shutting down")
                except Exception:
                    pass
            self._connections.clear()
            self._session_to_conn.clear()

    async def handle_connection(self, websocket: WebSocket, session_id: Optional[str] = None) -> None:
        """Handle full lifecycle of an incoming WebSocket connection."""
        await websocket.accept()

        conn_id = f"conn_{uuid4().hex[:12]}"
        sid = session_id or f"sess_{uuid4().hex[:12]}"

        conn = WebSocketConnection(conn_id, sid, websocket)
        conn.send_task = asyncio.create_task(conn.start_sender())

        async with self._lock:
            self._connections[conn_id] = conn
            self._session_to_conn[sid] = conn_id

        await self._session_manager.register_connection(
            session_id=sid,
            connection_id=conn_id,
            client_ip=websocket.client.host if websocket.client else "127.0.0.1",
        )

        # Send initial Runtime Status
        status_event = RuntimeEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=EventType.RUNTIME_STATUS,
            event_seq=self._event_bus.next_sequence(),
            timestamp=datetime.now(timezone.utc),
            session_id=sid,
            payload={
                "system_state": self._orchestrator.system_state.value,
                "session_id": sid,
                "connection_id": conn_id,
            },
        )
        await conn.enqueue_message(serialize_outbound_event(status_event))

        logger.info("WebSocket client connected: %s (Session: %s)", conn_id, sid)

        try:
            while not conn.closed:
                # Receive text or bytes
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break

                if "text" in message and message["text"]:
                    await self._process_inbound_text(conn, message["text"])
                elif "bytes" in message and message["bytes"]:
                    await self._process_inbound_bytes(conn, message["bytes"])

        except WebSocketDisconnect:
            logger.info("WebSocket disconnected normally: %s", conn_id)
        except Exception as e:
            logger.warning("WebSocket error for %s: %s", conn_id, e)
        finally:
            await self._cleanup_connection(conn)

    async def _process_inbound_text(self, conn: WebSocketConnection, text: str) -> None:
        """Parse and route inbound text command with safe error isolation."""
        try:
            base_cmd, payload = parse_inbound_message(text)
        except ProtocolError as pe:
            logger.warning("Protocol error from %s: %s", conn.connection_id, pe)
            err_event = RuntimeEvent(
                event_id=f"evt_{uuid4().hex[:12]}",
                event_type=EventType.ERROR,
                event_seq=self._event_bus.next_sequence(),
                timestamp=datetime.now(timezone.utc),
                session_id=conn.session_id,
                payload=ErrorEventPayload(
                    code=pe.code,
                    message=str(pe),
                    recoverable=True,
                    details=pe.details if isinstance(pe.details, dict) else None,
                ).model_dump(),
            )
            await conn.enqueue_message(serialize_outbound_event(err_event))
            return

        # Dispatch command to orchestrator
        try:
            await self._dispatch_command(conn, base_cmd, payload)
        except CommandSafetyError as cse:
            logger.warning("Safety boundary rejected command %s: [%s] %s", base_cmd.command_type, cse.code, cse.message)
            err_event = RuntimeEvent(
                event_id=f"evt_{uuid4().hex[:12]}",
                event_type=EventType.ERROR,
                event_seq=self._event_bus.next_sequence(),
                timestamp=datetime.now(timezone.utc),
                session_id=conn.session_id,
                correlation_id=base_cmd.command_id,
                payload=ErrorEventPayload(
                    code=cse.code,
                    message=cse.message,
                    recoverable=False,
                    details=cse.details,
                ).model_dump(),
            )
            await conn.enqueue_message(serialize_outbound_event(err_event))
        except Exception as ex:
            logger.exception("Error executing command %s: %s", base_cmd.command_type, ex)
            err_code = "COMMAND_EXECUTION_ERROR"
            if "REJECTED_OUT_OF_BOUNDS" in str(ex) or "OUT_OF_BOUNDS" in str(ex):
                err_code = "OUT_OF_BOUNDS"
            elif "HUMAN_TAKEOVER_ACTIVE" in str(ex):
                err_code = "HUMAN_TAKEOVER_ACTIVE"
            err_event = RuntimeEvent(
                event_id=f"evt_{uuid4().hex[:12]}",
                event_type=EventType.ERROR,
                event_seq=self._event_bus.next_sequence(),
                timestamp=datetime.now(timezone.utc),
                session_id=conn.session_id,
                correlation_id=base_cmd.command_id,
                payload=ErrorEventPayload(
                    code=err_code,
                    message=str(ex),
                    recoverable=True,
                ).model_dump(),
            )
            await conn.enqueue_message(serialize_outbound_event(err_event))

    async def _process_inbound_bytes(self, conn: WebSocketConnection, raw_bytes: bytes) -> None:
        """Handle binary inbound messages if needed."""
        pass

    async def _validate_pointer_action(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        expected_generation: Optional[int] = None,
    ) -> None:
        """Validate human takeover status, desktop generation, and workspace coordinate geometry.

        Zero OS pointer events are dispatched if any validation check fails.
        """
        # 1. Human Takeover Check
        if self._orchestrator.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
            raise CommandSafetyError(
                code="HUMAN_TAKEOVER_ACTIVE",
                message="Pointer command blocked: Human takeover is currently active",
            )
        if hasattr(self._orchestrator, "is_human_takeover_active"):
            res = self._orchestrator.is_human_takeover_active()
            if inspect.isawaitable(res):
                is_active = await res
            else:
                is_active = bool(res)
            if is_active:
                raise CommandSafetyError(
                    code="HUMAN_TAKEOVER_ACTIVE",
                    message="Pointer command blocked: Human takeover is currently active",
                )

        # 2. Workspace Coordinate Validation
        wsp = self._orchestrator.workspace
        if wsp is None and self._orchestrator.registry and self._orchestrator.registry.has(CapabilityType.WORKSPACE):
            wsp = self._orchestrator.registry.resolve_typed(CapabilityType.WORKSPACE, WorkspaceCapability)

        if wsp is not None and hasattr(wsp, "validate_coordinate"):
            target_x = x
            target_y = y
            if target_x is None or target_y is None:
                if self._orchestrator.registry.is_ready(CapabilityType.POINTER):
                    ptr = self._orchestrator.registry.resolve_typed(CapabilityType.POINTER, PointerCapability)
                    cur_pos = await ptr.get_cursor_position()
                    target_x = cur_pos.x
                    target_y = cur_pos.y

            if target_x is not None and target_y is not None:
                val_res = wsp.validate_coordinate(int(target_x), int(target_y), expected_generation=expected_generation)
                if not val_res.is_valid:
                    status_code = getattr(val_res.status, "value", str(val_res.status))
                    tag = f"REJECTED_{status_code}" if not status_code.startswith("REJECTED_") else status_code
                    err_msg = (
                        f"Workspace coordinate validation blocked pointer dispatch to ({target_x}, {target_y}): "
                        f"[{tag}] {val_res.error_message}"
                    )
                    logger.error(err_msg)
                    raise CommandSafetyError(
                        code=status_code,
                        message=err_msg,
                        details={
                            "x": target_x,
                            "y": target_y,
                            "status": status_code,
                            "active_generation": getattr(val_res, "active_generation_id", None),
                            "tested_generation": expected_generation,
                        },
                    )

    async def _validate_keyboard_action(self) -> None:
        """Validate human takeover preemption before dispatching direct keyboard commands."""
        if self._orchestrator.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
            raise CommandSafetyError(
                code="HUMAN_TAKEOVER_ACTIVE",
                message="Keyboard command blocked: Human takeover is currently active",
            )
        if hasattr(self._orchestrator, "is_human_takeover_active"):
            res = self._orchestrator.is_human_takeover_active()
            if inspect.isawaitable(res):
                is_active = await res
            else:
                is_active = bool(res)
            if is_active:
                raise CommandSafetyError(
                    code="HUMAN_TAKEOVER_ACTIVE",
                    message="Keyboard command blocked: Human takeover is currently active",
                )

    async def _dispatch_command(self, conn: WebSocketConnection, cmd: BaseCommand, payload: Any) -> None:
        """Route validated command to the orchestrator with mandatory safety boundaries."""
        if cmd.command_type == CommandType.SUBMIT_TASK:
            submit_payload: SubmitTaskPayload = payload
            await self._orchestrator.submit_task(
                session_id=conn.session_id,
                prompt=submit_payload.prompt,
                context=submit_payload.context,
            )
        elif cmd.command_type == CommandType.CANCEL_TASK:
            cancel_payload: CancelTaskPayload = payload
            await self._orchestrator.cancel_task(task_id=cancel_payload.task_id, reason=cancel_payload.reason or "Cancelled by user")
        elif cmd.command_type == CommandType.TRIGGER_TAKEOVER:
            takeover_payload: TriggerTakeoverPayload = payload
            await self._orchestrator.handle_human_takeover(takeover_payload.reason or "Manual takeover triggered")
        elif cmd.command_type == CommandType.RELEASE_TAKEOVER:
            await self._orchestrator.release_takeover()
        elif cmd.command_type == CommandType.RECOVER_LOCKED:
            recover_payload: RecoverLockedPayload = payload
            await self._orchestrator.recover_locked_state(recover_payload.recovery_token)
        elif cmd.command_type == CommandType.MOVE_POINTER:
            move_payload: MovePointerPayload = payload
            await self._validate_pointer_action(
                x=move_payload.x,
                y=move_payload.y,
                expected_generation=getattr(move_payload, "expected_generation", None),
            )
            if self._orchestrator.registry.is_ready(CapabilityType.POINTER):
                ptr = self._orchestrator.registry.resolve_typed(CapabilityType.POINTER, PointerCapability)
                await ptr.move_to(move_payload.x, move_payload.y)
                cur_pos = await ptr.get_cursor_position()
                await self._event_bus.publish(
                    RuntimeEvent(
                        event_id=f"evt_{uuid4().hex[:12]}",
                        event_type=EventType.POINTER_MOVED,
                        event_seq=self._event_bus.next_sequence(),
                        timestamp=datetime.now(timezone.utc),
                        session_id=conn.session_id,
                        correlation_id=cmd.command_id,
                        payload={"x": cur_pos.x, "y": cur_pos.y, "status": "VERIFIED"},
                    )
                )
            else:
                raise RuntimeError("Pointer capability is not ready")
        elif cmd.command_type == CommandType.CLICK_POINTER:
            click_payload: ClickPointerPayload = payload
            await self._validate_pointer_action(
                x=click_payload.x,
                y=click_payload.y,
                expected_generation=getattr(click_payload, "expected_generation", None),
            )
            if self._orchestrator.registry.is_ready(CapabilityType.POINTER):
                ptr = self._orchestrator.registry.resolve_typed(CapabilityType.POINTER, PointerCapability)
                await ptr.click(
                    x=click_payload.x,
                    y=click_payload.y,
                    button=click_payload.button,
                    count=click_payload.count,
                    dwell_ms=click_payload.dwell_ms,
                )
                cur_pos = await ptr.get_cursor_position()
                await self._event_bus.publish(
                    RuntimeEvent(
                        event_id=f"evt_{uuid4().hex[:12]}",
                        event_type=EventType.POINTER_CLICKED,
                        event_seq=self._event_bus.next_sequence(),
                        timestamp=datetime.now(timezone.utc),
                        session_id=conn.session_id,
                        correlation_id=cmd.command_id,
                        payload={
                            "x": cur_pos.x,
                            "y": cur_pos.y,
                            "button": click_payload.button,
                            "count": click_payload.count,
                            "status": "CLICK_VERIFIED",
                        },
                    )
                )
            else:
                raise RuntimeError("Pointer capability is not ready")
        elif cmd.command_type == CommandType.POINTER_BUTTON_DOWN:
            btn_down_payload: PointerButtonPayload = payload
            await self._validate_pointer_action()
            if self._orchestrator.registry.is_ready(CapabilityType.POINTER):
                ptr = self._orchestrator.registry.resolve_typed(CapabilityType.POINTER, PointerCapability)
                await ptr.press_down(button=btn_down_payload.button)
                await self._event_bus.publish(
                    RuntimeEvent(
                        event_id=f"evt_{uuid4().hex[:12]}",
                        event_type=EventType.POINTER_BUTTON_STATE_CHANGED,
                        event_seq=self._event_bus.next_sequence(),
                        timestamp=datetime.now(timezone.utc),
                        session_id=conn.session_id,
                        correlation_id=cmd.command_id,
                        payload={"button": btn_down_payload.button, "state": "DOWN"},
                    )
                )
            else:
                raise RuntimeError("Pointer capability is not ready")
        elif cmd.command_type == CommandType.POINTER_BUTTON_UP:
            btn_up_payload: PointerButtonPayload = payload
            await self._validate_pointer_action()
            if self._orchestrator.registry.is_ready(CapabilityType.POINTER):
                ptr = self._orchestrator.registry.resolve_typed(CapabilityType.POINTER, PointerCapability)
                await ptr.release_up(button=btn_up_payload.button)
                await self._event_bus.publish(
                    RuntimeEvent(
                        event_id=f"evt_{uuid4().hex[:12]}",
                        event_type=EventType.POINTER_BUTTON_STATE_CHANGED,
                        event_seq=self._event_bus.next_sequence(),
                        timestamp=datetime.now(timezone.utc),
                        session_id=conn.session_id,
                        correlation_id=cmd.command_id,
                        payload={"button": btn_up_payload.button, "state": "UP"},
                    )
                )
            else:
                raise RuntimeError("Pointer capability is not ready")
        elif cmd.command_type == CommandType.POINTER_EMERGENCY_RELEASE:
            if self._orchestrator.registry.is_ready(CapabilityType.POINTER):
                ptr = self._orchestrator.registry.resolve_typed(CapabilityType.POINTER, PointerCapability)
                success = await ptr.emergency_release_all()
                await self._event_bus.publish(
                    RuntimeEvent(
                        event_id=f"evt_{uuid4().hex[:12]}",
                        event_type=EventType.POINTER_BUTTON_STATE_CHANGED,
                        event_seq=self._event_bus.next_sequence(),
                        timestamp=datetime.now(timezone.utc),
                        session_id=conn.session_id,
                        correlation_id=cmd.command_id,
                        payload={"state": "ALL_RELEASED", "success": success},
                    )
                )
            else:
                raise RuntimeError("Pointer capability is not ready")
        elif cmd.command_type == CommandType.RECOVER_POINTER_LOCKOUT:
            recover_lockout_payload: RecoverPointerLockoutPayload = payload
            if self._orchestrator.registry.is_ready(CapabilityType.POINTER):
                ptr = self._orchestrator.registry.resolve_typed(CapabilityType.POINTER, PointerCapability)
                if hasattr(ptr, "recover_locked_state"):
                    recovered = ptr.recover_locked_state(recover_lockout_payload.recovery_token)
                    await self._event_bus.publish(
                        RuntimeEvent(
                            event_id=f"evt_{uuid4().hex[:12]}",
                            event_type=EventType.POINTER_LOCKOUT_CHANGED,
                            event_seq=self._event_bus.next_sequence(),
                            timestamp=datetime.now(timezone.utc),
                            session_id=conn.session_id,
                            correlation_id=cmd.command_id,
                            payload={"is_locked": not recovered, "recovered": recovered},
                        )
                    )
                else:
                    raise RuntimeError("Pointer capability does not support lockout recovery")
            else:
                raise RuntimeError("Pointer capability is not ready")
        elif cmd.command_type == CommandType.TYPE_TEXT:
            type_payload: TypeTextPayload = payload
            await self._validate_keyboard_action()
            if self._orchestrator.registry.is_ready(CapabilityType.KEYBOARD):
                kbd = self._orchestrator.registry.resolve_typed(CapabilityType.KEYBOARD, KeyboardCapability)
                success = await kbd.type_text(
                    text=type_payload.text,
                    delay_ms=type_payload.delay_ms,
                    target_hwnd=type_payload.target_hwnd,
                )
                await self._event_bus.publish(
                    RuntimeEvent(
                        event_id=f"evt_{uuid4().hex[:12]}",
                        event_type=EventType.KEYBOARD_TYPED,
                        event_seq=self._event_bus.next_sequence(),
                        timestamp=datetime.now(timezone.utc),
                        session_id=conn.session_id,
                        correlation_id=cmd.command_id,
                        payload={"char_count": len(type_payload.text), "success": success},
                    )
                )
            else:
                raise RuntimeError("Keyboard capability is not ready")
        elif cmd.command_type == CommandType.PRESS_SHORTCUT:
            shortcut_payload: PressShortcutPayload = payload
            await self._validate_keyboard_action()
            if self._orchestrator.registry.is_ready(CapabilityType.KEYBOARD):
                kbd = self._orchestrator.registry.resolve_typed(CapabilityType.KEYBOARD, KeyboardCapability)
                success = await kbd.press_shortcut(
                    combination=shortcut_payload.combination,
                    target_hwnd=shortcut_payload.target_hwnd,
                )
                await self._event_bus.publish(
                    RuntimeEvent(
                        event_id=f"evt_{uuid4().hex[:12]}",
                        event_type=EventType.SHORTCUT_EXECUTED,
                        event_seq=self._event_bus.next_sequence(),
                        timestamp=datetime.now(timezone.utc),
                        session_id=conn.session_id,
                        correlation_id=cmd.command_id,
                        payload={"combination": shortcut_payload.combination, "success": success},
                    )
                )
            else:
                raise RuntimeError("Keyboard capability is not ready")
        elif cmd.command_type == CommandType.KEYBOARD_KEY_DOWN:
            key_down_payload: KeyboardKeyPayload = payload
            await self._validate_keyboard_action()
            if self._orchestrator.registry.is_ready(CapabilityType.KEYBOARD):
                kbd = self._orchestrator.registry.resolve_typed(CapabilityType.KEYBOARD, KeyboardCapability)
                success = await kbd.press_key(key_code=key_down_payload.key_code)
                await self._event_bus.publish(
                    RuntimeEvent(
                        event_id=f"evt_{uuid4().hex[:12]}",
                        event_type=EventType.KEYBOARD_KEY_STATE_CHANGED,
                        event_seq=self._event_bus.next_sequence(),
                        timestamp=datetime.now(timezone.utc),
                        session_id=conn.session_id,
                        correlation_id=cmd.command_id,
                        payload={"key_code": key_down_payload.key_code, "state": "DOWN", "success": success},
                    )
                )
            else:
                raise RuntimeError("Keyboard capability is not ready")
        elif cmd.command_type == CommandType.KEYBOARD_KEY_UP:
            key_up_payload: KeyboardKeyPayload = payload
            await self._validate_keyboard_action()
            if self._orchestrator.registry.is_ready(CapabilityType.KEYBOARD):
                kbd = self._orchestrator.registry.resolve_typed(CapabilityType.KEYBOARD, KeyboardCapability)
                success = await kbd.release_key(key_code=key_up_payload.key_code)
                await self._event_bus.publish(
                    RuntimeEvent(
                        event_id=f"evt_{uuid4().hex[:12]}",
                        event_type=EventType.KEYBOARD_KEY_STATE_CHANGED,
                        event_seq=self._event_bus.next_sequence(),
                        timestamp=datetime.now(timezone.utc),
                        session_id=conn.session_id,
                        correlation_id=cmd.command_id,
                        payload={"key_code": key_up_payload.key_code, "state": "UP", "success": success},
                    )
                )
            else:
                raise RuntimeError("Keyboard capability is not ready")
        elif cmd.command_type == CommandType.KEYBOARD_EMERGENCY_RELEASE:
            if self._orchestrator.registry.is_ready(CapabilityType.KEYBOARD):
                kbd = self._orchestrator.registry.resolve_typed(CapabilityType.KEYBOARD, KeyboardCapability)
                success = await kbd.emergency_release_all()
                await self._event_bus.publish(
                    RuntimeEvent(
                        event_id=f"evt_{uuid4().hex[:12]}",
                        event_type=EventType.KEYBOARD_KEY_STATE_CHANGED,
                        event_seq=self._event_bus.next_sequence(),
                        timestamp=datetime.now(timezone.utc),
                        session_id=conn.session_id,
                        correlation_id=cmd.command_id,
                        payload={"state": "ALL_RELEASED", "success": success},
                    )
                )
            else:
                raise RuntimeError("Keyboard capability is not ready")
        elif cmd.command_type == CommandType.RECOVER_KEYBOARD_LOCKOUT:
            recover_kbd_payload: RecoverKeyboardLockoutPayload = payload
            if self._orchestrator.registry.is_ready(CapabilityType.KEYBOARD):
                kbd = self._orchestrator.registry.resolve_typed(CapabilityType.KEYBOARD, KeyboardCapability)
                if hasattr(kbd, "recover_locked_state"):
                    recovered = kbd.recover_locked_state(recover_kbd_payload.recovery_token)
                    await self._event_bus.publish(
                        RuntimeEvent(
                            event_id=f"evt_{uuid4().hex[:12]}",
                            event_type=EventType.KEYBOARD_LOCKOUT_CHANGED,
                            event_seq=self._event_bus.next_sequence(),
                            timestamp=datetime.now(timezone.utc),
                            session_id=conn.session_id,
                            correlation_id=cmd.command_id,
                            payload={"is_locked": not recovered, "recovered": recovered},
                        )
                    )
                else:
                    raise RuntimeError("Keyboard capability does not support lockout recovery")
            else:
                raise RuntimeError("Keyboard capability is not ready")
        elif cmd.command_type == CommandType.HEARTBEAT:
            await self._session_manager.record_heartbeat(conn.connection_id)

            ack_event = RuntimeEvent(
                event_id=f"evt_{uuid4().hex[:12]}",
                event_type=EventType.HEARTBEAT_ACK,
                event_seq=self._event_bus.next_sequence(),
                timestamp=datetime.now(timezone.utc),
                session_id=conn.session_id,
                correlation_id=cmd.command_id,
                payload={"status": "OK"},
            )
            await conn.enqueue_message(serialize_outbound_event(ack_event))

    async def _on_bus_event(self, event: RuntimeEvent) -> None:
        """Forward an event from EventBus to the relevant connected client."""
        # Check if event is broadcast or session-specific
        async with self._lock:
            if event.session_id in {"system", "broadcast"}:
                targets = list(self._connections.values())
            else:
                conn_id = self._session_to_conn.get(event.session_id)
                targets = [self._connections[conn_id]] if conn_id and conn_id in self._connections else []

        json_str = serialize_outbound_event(event)
        for target in targets:
            await target.enqueue_message(json_str)

    async def _cleanup_connection(self, conn: WebSocketConnection) -> None:
        """Clean up connection and enforce disconnection policy."""
        conn.closed = True
        if conn.send_task:
            conn.send_task.cancel()

        # Sanitize any held pointer or keyboard state
        if self._orchestrator.registry.is_ready(CapabilityType.POINTER):
            try:
                ptr = self._orchestrator.registry.resolve_typed(CapabilityType.POINTER, PointerCapability)
                await ptr.emergency_release_all()
            except Exception:
                pass
        if self._orchestrator.registry.is_ready(CapabilityType.KEYBOARD):
            try:
                kbd = self._orchestrator.registry.resolve_typed(CapabilityType.KEYBOARD, KeyboardCapability)
                await kbd.emergency_release_all()
            except Exception:
                pass

        async with self._lock:
            self._connections.pop(conn.connection_id, None)
            self._session_to_conn.pop(conn.session_id, None)

        disc_info = await self._session_manager.handle_disconnect(conn.connection_id)
        if disc_info:
            session, policy = disc_info
            # Enforce disconnection policy
            if policy == DisconnectionPolicy.CANCEL_ACTIVE_TASKS and session.active_task_id:
                await self._orchestrator.cancel_task(session.active_task_id, "Client disconnected")
            elif policy == DisconnectionPolicy.PAUSE_ACTIVE_TASKS and session.active_task_id:
                # Pause active task if supported
                pass

