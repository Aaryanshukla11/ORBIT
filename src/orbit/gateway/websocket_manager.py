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
    ModelActivatePayload,
    ModelActivePayload,
    ModelDiscoverPayload,
    ModelHealthPayload,
    ModelListPayload,
    ModelStatusPayload,
    ModelSwitchPayload,
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
    TaskHistoryClearPayload,
    TaskHistoryDetailPayload,
    TaskHistoryListPayload,
    DiagnosticsRunPayload,
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
from orbit.runtime.model_runtime.contracts import (
    ActiveModelContext,
    ModelActivationRequest,
    ModelActivationStatus,
    ModelRuntimeKind,
    ModelRuntimeStatus,
    ModelSwitchPolicy,
)
from orbit.runtime.models.models import (
    ModelCapability,
    ModelDescriptor,
    ModelStatus,
)
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
        elif cmd.command_type == CommandType.MODEL_LIST:
            await self._handle_model_list(conn, cmd, payload)
        elif cmd.command_type == CommandType.MODEL_STATUS:
            await self._handle_model_status(conn, cmd, payload)
        elif cmd.command_type == CommandType.MODEL_ACTIVE:
            await self._handle_model_active(conn, cmd, payload)
        elif cmd.command_type == CommandType.MODEL_DISCOVER:
            await self._handle_model_discover(conn, cmd, payload)
        elif cmd.command_type == CommandType.MODEL_ACTIVATE:
            await self._handle_model_activate(conn, cmd, payload)
        elif cmd.command_type == CommandType.MODEL_SWITCH:
            await self._handle_model_switch(conn, cmd, payload)
        elif cmd.command_type == CommandType.MODEL_HEALTH:
            await self._handle_model_health(conn, cmd, payload)
        elif cmd.command_type == CommandType.TASK_HISTORY_LIST:
            await self._handle_task_history_list(conn, cmd, payload)
        elif cmd.command_type == CommandType.TASK_HISTORY_DETAIL:
            await self._handle_task_history_detail(conn, cmd, payload)
        elif cmd.command_type == CommandType.TASK_HISTORY_CLEAR:
            await self._handle_task_history_clear(conn, cmd, payload)
        elif cmd.command_type == CommandType.DIAGNOSTICS_RUN:
            await self._handle_diagnostics_run(conn, cmd, payload)

    # =========================================================================
    # Task Execution History Handlers
    # =========================================================================

    async def _handle_task_history_list(
        self,
        conn: WebSocketConnection,
        cmd: BaseCommand,
        payload: TaskHistoryListPayload,
    ) -> None:
        """Return historical execution records matching optional filter/search."""
        records = await self._orchestrator.history_store.list_records(
            limit=payload.limit,
            status_filter=payload.status_filter,
            search_query=payload.search_query,
        )
        resp_payload = {
            "records": [r.model_dump(mode="json") for r in records],
            "total_count": len(records),
            "status_filter": payload.status_filter,
            "search_query": payload.search_query,
        }
        resp_event = RuntimeEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=EventType.TASK_HISTORY_LIST_RESPONSE,
            event_seq=self._event_bus.next_sequence(),
            timestamp=datetime.now(timezone.utc),
            session_id=conn.session_id,
            correlation_id=cmd.command_id,
            payload=resp_payload,
        )
        await conn.enqueue_message(serialize_outbound_event(resp_event))

    async def _handle_task_history_detail(
        self,
        conn: WebSocketConnection,
        cmd: BaseCommand,
        payload: TaskHistoryDetailPayload,
    ) -> None:
        """Return full detail for a specific historical execution record."""
        rec = None
        if payload.execution_id:
            rec = await self._orchestrator.history_store.get_record(payload.execution_id)
        elif payload.task_id:
            rec = await self._orchestrator.history_store.get_record_by_task_id(payload.task_id)

        resp_payload = {
            "record": rec.model_dump(mode="json") if rec else None,
            "found": rec is not None,
        }
        resp_event = RuntimeEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=EventType.TASK_HISTORY_DETAIL_RESPONSE,
            event_seq=self._event_bus.next_sequence(),
            timestamp=datetime.now(timezone.utc),
            session_id=conn.session_id,
            correlation_id=cmd.command_id,
            payload=resp_payload,
        )
        await conn.enqueue_message(serialize_outbound_event(resp_event))

    async def _handle_task_history_clear(
        self,
        conn: WebSocketConnection,
        cmd: BaseCommand,
        payload: TaskHistoryClearPayload,
    ) -> None:
        """Clear all historical execution records."""
        await self._orchestrator.history_store.clear_history()
        resp_event = RuntimeEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=EventType.TASK_HISTORY_LIST_RESPONSE,
            event_seq=self._event_bus.next_sequence(),
            timestamp=datetime.now(timezone.utc),
            session_id=conn.session_id,
            correlation_id=cmd.command_id,
            payload={"records": [], "total_count": 0, "cleared": True},
        )
        await conn.enqueue_message(serialize_outbound_event(resp_event))

    async def _handle_diagnostics_run(
        self,
        conn: WebSocketConnection,
        cmd: BaseCommand,
        payload: DiagnosticsRunPayload,
    ) -> None:
        """Run deep diagnostic probe across all subsystems and return structured report."""
        report = await self._orchestrator.diagnostic_service.run_diagnostics()
        resp_event = RuntimeEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=EventType.DIAGNOSTICS_RUN_RESPONSE,
            event_seq=self._event_bus.next_sequence(),
            timestamp=datetime.now(timezone.utc),
            session_id=conn.session_id,
            correlation_id=cmd.command_id,
            payload=report.model_dump(mode="json"),
        )
        await conn.enqueue_message(serialize_outbound_event(resp_event))

    # =========================================================================
    # Model Control Command Handlers (Milestone M1.9 Step 5)
    # =========================================================================

    async def _handle_model_list(
        self,
        conn: WebSocketConnection,
        cmd: BaseCommand,
        payload: ModelListPayload,
    ) -> None:
        """Return safe metadata for registered and discovered AI models."""
        models_list = []
        registry = self._orchestrator.model_session_manager._registry
        all_descriptors = await registry.list_models()

        inv_report = await self._orchestrator.model_manager.get_inventory_report()
        inv_map = {m.model_id: m for m in inv_report.models}

        for desc in all_descriptors:
            # Filter by provider if requested
            if payload.provider:
                prov_str = desc.provider.value if hasattr(desc.provider, "value") else str(desc.provider)
                if payload.provider.upper() not in prov_str.upper():
                    continue

            # Filter by capability if requested
            if payload.capability:
                cap_names = [c.value if hasattr(c, "value") else str(c) for c in desc.capabilities]
                if payload.capability.upper() not in [c.upper() for c in cap_names]:
                    continue

            inv_item = inv_map.get(desc.model_id)
            is_installed = getattr(desc, "installed", True)
            is_configured = getattr(desc, "configured", True)
            status_val = desc.status.value if hasattr(desc.status, "value") else str(desc.status)

            if inv_item:
                is_installed = inv_item.installed
                is_configured = inv_item.configured
                status_val = inv_item.status.value if hasattr(inv_item.status, "value") else str(inv_item.status)

            if not payload.include_all and not (is_installed and is_configured):
                continue

            runtime_kind_val = "LOCAL_OLLAMA"
            if hasattr(desc, "runtime_kind") and desc.runtime_kind:
                runtime_kind_val = desc.runtime_kind.value if hasattr(desc.runtime_kind, "value") else str(desc.runtime_kind)
            elif "OLLAMA" in str(desc.provider).upper():
                runtime_kind_val = "LOCAL_OLLAMA"
            elif "LM_STUDIO" in str(desc.provider).upper():
                runtime_kind_val = "LOCAL_LM_STUDIO"
            elif "LOCAL" in str(desc.provider).upper():
                runtime_kind_val = "LOCAL_FILE"
            elif "MOCK" in str(desc.provider).upper():
                runtime_kind_val = "MOCK"
            else:
                runtime_kind_val = "REMOTE_OPENAI_COMPATIBLE"

            safe_item = {
                "model_id": desc.model_id,
                "display_name": desc.display_name or desc.provider_model_name,
                "provider": desc.provider.value if hasattr(desc.provider, "value") else str(desc.provider),
                "runtime_kind": runtime_kind_val,
                "availability": status_val,
                "status": status_val,
                "installed": is_installed,
                "configured": is_configured,
                "capabilities": [c.value if hasattr(c, "value") else str(c) for c in desc.capabilities],
                "context_window": desc.context_window,
                "parameter_size": desc.parameter_size,
                "family": desc.family,
            }
            models_list.append(safe_item)

        active_ctx = self._orchestrator.model_session_manager.get_active_context()
        active_id = active_ctx.model_id if active_ctx else None

        resp_event = RuntimeEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=EventType.MODEL_LIST_RESPONSE,
            event_seq=self._event_bus.next_sequence(),
            timestamp=datetime.now(timezone.utc),
            session_id=conn.session_id,
            correlation_id=cmd.command_id,
            payload={
                "models": models_list,
                "total_count": len(models_list),
                "active_model_id": active_id,
            },
        )
        await conn.enqueue_message(serialize_outbound_event(resp_event))

    async def _handle_model_status(
        self,
        conn: WebSocketConnection,
        cmd: BaseCommand,
        payload: ModelStatusPayload,
    ) -> None:
        """Return comprehensive status of active model and model subsystem."""
        msm = self._orchestrator.model_session_manager
        active_ctx = msm.get_active_context()
        runtime_status = msm.get_runtime_status()
        is_active = msm.is_model_active()

        active_model_data = None
        if active_ctx is not None:
            active_model_data = {
                "model_id": active_ctx.model_id,
                "display_name": active_ctx.display_name,
                "provider": active_ctx.provider.value if hasattr(active_ctx.provider, "value") else str(active_ctx.provider),
                "runtime_kind": active_ctx.runtime_kind.value if hasattr(active_ctx.runtime_kind, "value") else str(active_ctx.runtime_kind),
                "runtime_status": active_ctx.runtime_status.value if hasattr(active_ctx.runtime_status, "value") else str(active_ctx.runtime_status),
                "capabilities": [c.value if hasattr(c, "value") else str(c) for c in active_ctx.capabilities],
                "context_window": active_ctx.context_window,
                "activated_at": active_ctx.activated_at.isoformat() if active_ctx.activated_at else None,
                "generation": active_ctx.generation,
            }

        all_models = await msm._registry.list_models()
        available_model_ids = [m.model_id for m in all_models]

        health_data = None
        if active_ctx and active_ctx.health:
            h = active_ctx.health
            health_data = {
                "status": h.status.value if hasattr(h.status, "value") else str(h.status),
                "is_healthy": h.is_healthy,
                "latency_ms": h.latency_ms,
                "diagnostic_message": h.diagnostic_message,
            }

        is_busy = self._orchestrator.is_task_executing or (
            msm.get_active_runtime() is not None and getattr(msm.get_active_runtime(), "status", None) == ModelRuntimeStatus.BUSY
        )

        resp_event = RuntimeEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=EventType.MODEL_STATUS_RESPONSE,
            event_seq=self._event_bus.next_sequence(),
            timestamp=datetime.now(timezone.utc),
            session_id=conn.session_id,
            correlation_id=cmd.command_id,
            payload={
                "active_model": active_model_data,
                "is_active": is_active,
                "runtime_status": runtime_status.value if hasattr(runtime_status, "value") else str(runtime_status),
                "runtime_health": health_data,
                "available_models": available_model_ids,
                "available_models_count": len(available_model_ids),
                "active_generation": msm.get_active_generation(),
                "busy": is_busy,
            },
        )
        await conn.enqueue_message(serialize_outbound_event(resp_event))

    async def _handle_model_active(
        self,
        conn: WebSocketConnection,
        cmd: BaseCommand,
        payload: ModelActivePayload,
    ) -> None:
        """Return current ActiveModelContext or honest inactive state."""
        msm = self._orchestrator.model_session_manager
        active_ctx = msm.get_active_context()

        if active_ctx is None:
            resp_payload = {
                "is_active": False,
                "active_model": None,
                "generation": msm.get_active_generation(),
                "status": "NO_ACTIVE_MODEL",
            }
        else:
            resp_payload = {
                "is_active": True,
                "generation": active_ctx.generation,
                "active_model": {
                    "model_id": active_ctx.model_id,
                    "display_name": active_ctx.display_name,
                    "provider": active_ctx.provider.value if hasattr(active_ctx.provider, "value") else str(active_ctx.provider),
                    "runtime_kind": active_ctx.runtime_kind.value if hasattr(active_ctx.runtime_kind, "value") else str(active_ctx.runtime_kind),
                    "runtime_status": active_ctx.runtime_status.value if hasattr(active_ctx.runtime_status, "value") else str(active_ctx.runtime_status),
                    "capabilities": [c.value if hasattr(c, "value") else str(c) for c in active_ctx.capabilities],
                    "context_window": active_ctx.context_window,
                    "activated_at": active_ctx.activated_at.isoformat() if active_ctx.activated_at else None,
                    "health": {
                        "status": active_ctx.health.status.value if hasattr(active_ctx.health.status, "value") else str(active_ctx.health.status),
                        "is_healthy": active_ctx.health.is_healthy,
                        "latency_ms": active_ctx.health.latency_ms,
                        "diagnostic_message": active_ctx.health.diagnostic_message,
                    } if active_ctx.health else None,
                },
            }

        resp_event = RuntimeEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=EventType.MODEL_ACTIVE_RESPONSE,
            event_seq=self._event_bus.next_sequence(),
            timestamp=datetime.now(timezone.utc),
            session_id=conn.session_id,
            correlation_id=cmd.command_id,
            payload=resp_payload,
        )
        await conn.enqueue_message(serialize_outbound_event(resp_event))

    async def _handle_model_discover(
        self,
        conn: WebSocketConnection,
        cmd: BaseCommand,
        payload: ModelDiscoverPayload,
    ) -> None:
        """Trigger safe model discovery refresh across configured providers."""
        inv_report = await self._orchestrator.model_manager.refresh_inventory(
            include_runtimes=payload.include_runtimes,
            include_cloud=payload.include_cloud,
            include_files=payload.include_files,
        )

        for desc in inv_report.models:
            await self._orchestrator.model_session_manager.register_descriptor(desc)
            await self._event_bus.publish(
                RuntimeEvent(
                    event_id=f"evt_{uuid4().hex[:12]}",
                    event_type=EventType.MODEL_DISCOVERED,
                    event_seq=self._event_bus.next_sequence(),
                    timestamp=datetime.now(timezone.utc),
                    session_id="system",
                    payload={
                        "model_id": desc.model_id,
                        "provider": desc.provider.value if hasattr(desc.provider, "value") else str(desc.provider),
                        "display_name": desc.display_name or desc.provider_model_name,
                        "capabilities": [c.value if hasattr(c, "value") else str(c) for c in desc.capabilities],
                    },
                )
            )

        resp_event = RuntimeEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=EventType.MODEL_DISCOVER_RESPONSE,
            event_seq=self._event_bus.next_sequence(),
            timestamp=datetime.now(timezone.utc),
            session_id=conn.session_id,
            correlation_id=cmd.command_id,
            payload={
                "discovered_count": len(inv_report.models),
                "models": [
                    {
                        "model_id": m.model_id,
                        "display_name": m.display_name or m.provider_model_name,
                        "provider": m.provider.value if hasattr(m.provider, "value") else str(m.provider),
                        "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                    }
                    for m in inv_report.models
                ],
                "scanned_runtimes": payload.include_runtimes,
                "scanned_cloud": payload.include_cloud,
                "scanned_files": payload.include_files,
            },
        )
        await conn.enqueue_message(serialize_outbound_event(resp_event))

    async def _handle_model_activate(
        self,
        conn: WebSocketConnection,
        cmd: BaseCommand,
        payload: ModelActivatePayload,
    ) -> None:
        """Route model activation through ModelSessionManager."""
        msm = self._orchestrator.model_session_manager

        policy_str = (payload.policy or "REJECT_DURING_ACTIVE_TASK").upper()
        try:
            policy_enum = ModelSwitchPolicy[policy_str]
        except KeyError:
            policy_enum = ModelSwitchPolicy.REJECT_DURING_ACTIVE_TASK

        req_caps: Set[ModelCapability] = set()
        if payload.required_capabilities:
            for cap_str in payload.required_capabilities:
                try:
                    req_caps.add(ModelCapability[cap_str.upper()])
                except KeyError:
                    pass

        activation_req = ModelActivationRequest(
            model_id=payload.model_id,
            timeout_seconds=payload.timeout_seconds,
            preload_weights=payload.preload_weights,
            required_capabilities=req_caps,
            policy=policy_enum,
        )

        result = await msm.activate_model(activation_req)

        if result.is_successful:
            resp_event = RuntimeEvent(
                event_id=f"evt_{uuid4().hex[:12]}",
                event_type=EventType.MODEL_ACTIVATED,
                event_seq=self._event_bus.next_sequence(),
                timestamp=datetime.now(timezone.utc),
                session_id=conn.session_id,
                correlation_id=cmd.command_id,
                payload={
                    "model_id": result.model_id,
                    "status": result.status.value if hasattr(result.status, "value") else str(result.status),
                    "generation": result.generation,
                    "duration_ms": result.duration_ms,
                    "is_successful": True,
                },
            )
            await conn.enqueue_message(serialize_outbound_event(resp_event))
        else:
            code_str = result.status.value if hasattr(result.status, "value") else str(result.status)
            if result.failure_reason in {"ACTIVE_TASK_CONFLICT", "MODEL_NOT_FOUND", "MODEL_UNAVAILABLE", "INITIALIZATION_FAILED", "SWITCH_REJECTED"}:
                code_str = result.failure_reason

            err_event = RuntimeEvent(
                event_id=f"evt_{uuid4().hex[:12]}",
                event_type=EventType.ERROR,
                event_seq=self._event_bus.next_sequence(),
                timestamp=datetime.now(timezone.utc),
                session_id=conn.session_id,
                correlation_id=cmd.command_id,
                payload=ErrorEventPayload(
                    code=code_str,
                    message=result.diagnostic_message or f"Activation failed for model '{payload.model_id}'",
                    recoverable=True,
                    details={
                        "model_id": payload.model_id,
                        "status": code_str,
                        "failure_reason": result.failure_reason,
                        "duration_ms": result.duration_ms,
                    },
                ).model_dump(),
            )
            await conn.enqueue_message(serialize_outbound_event(err_event))

    async def _handle_model_switch(
        self,
        conn: WebSocketConnection,
        cmd: BaseCommand,
        payload: ModelSwitchPayload,
    ) -> None:
        """Route model switching through ModelSessionManager."""
        msm = self._orchestrator.model_session_manager

        policy_str = (payload.policy or "REJECT_DURING_ACTIVE_TASK").upper()
        try:
            policy_enum = ModelSwitchPolicy[policy_str]
        except KeyError:
            policy_enum = ModelSwitchPolicy.REJECT_DURING_ACTIVE_TASK

        req_caps: Set[ModelCapability] = set()
        if payload.required_capabilities:
            for cap_str in payload.required_capabilities:
                try:
                    req_caps.add(ModelCapability[cap_str.upper()])
                except KeyError:
                    pass

        result = await msm.switch_model(
            new_model_id=payload.model_id,
            policy=policy_enum,
            timeout_seconds=payload.timeout_seconds,
            preload_weights=payload.preload_weights,
            required_capabilities=req_caps,
        )

        if result.is_successful:
            resp_event = RuntimeEvent(
                event_id=f"evt_{uuid4().hex[:12]}",
                event_type=EventType.MODEL_SWITCHED,
                event_seq=self._event_bus.next_sequence(),
                timestamp=datetime.now(timezone.utc),
                session_id=conn.session_id,
                correlation_id=cmd.command_id,
                payload={
                    "previous_model_id": result.previous_model_id,
                    "active_model_id": result.active_model_id,
                    "generation": result.generation,
                    "switched": result.switched,
                    "duration_ms": result.duration_ms,
                    "is_successful": True,
                },
            )
            await conn.enqueue_message(serialize_outbound_event(resp_event))
        else:
            code_str = result.status.value if hasattr(result.status, "value") else str(result.status)
            if result.failure_reason in {"ACTIVE_TASK_CONFLICT", "MODEL_NOT_FOUND", "MODEL_UNAVAILABLE", "INITIALIZATION_FAILED", "SWITCH_REJECTED"}:
                code_str = result.failure_reason

            err_event = RuntimeEvent(
                event_id=f"evt_{uuid4().hex[:12]}",
                event_type=EventType.ERROR,
                event_seq=self._event_bus.next_sequence(),
                timestamp=datetime.now(timezone.utc),
                session_id=conn.session_id,
                correlation_id=cmd.command_id,
                payload=ErrorEventPayload(
                    code=code_str,
                    message=result.diagnostic_message or f"Switch failed to model '{payload.model_id}'",
                    recoverable=True,
                    details={
                        "target_model_id": payload.model_id,
                        "previous_model_id": result.previous_model_id,
                        "status": code_str,
                        "failure_reason": result.failure_reason,
                        "duration_ms": result.duration_ms,
                    },
                ).model_dump(),
            )
            await conn.enqueue_message(serialize_outbound_event(err_event))

    async def _handle_model_health(
        self,
        conn: WebSocketConnection,
        cmd: BaseCommand,
        payload: ModelHealthPayload,
    ) -> None:
        """Query model health information for active model or target model."""
        msm = self._orchestrator.model_session_manager
        active_ctx = msm.get_active_context()
        target_id = payload.model_id

        if target_id is None or (active_ctx and active_ctx.model_id == target_id):
            if active_ctx is None:
                resp_payload = {
                    "model_id": None,
                    "status": "UNKNOWN",
                    "is_healthy": False,
                    "latency_ms": None,
                    "diagnostic_message": "No model runtime currently active",
                }
            else:
                health = await msm.get_runtime_health()
                if health is None:
                    resp_payload = {
                        "model_id": active_ctx.model_id,
                        "status": "UNKNOWN",
                        "is_healthy": False,
                        "latency_ms": None,
                        "diagnostic_message": "Health probe unavailable",
                    }
                else:
                    if health.is_healthy:
                        status_str = "HEALTHY"
                    elif health.status == ModelRuntimeStatus.FAILED:
                        status_str = "FAILED"
                    elif health.status in {ModelRuntimeStatus.STOPPED, ModelRuntimeStatus.UNINITIALIZED}:
                        status_str = "UNAVAILABLE"
                    else:
                        status_str = "DEGRADED"

                    resp_payload = {
                        "model_id": active_ctx.model_id,
                        "status": status_str,
                        "is_healthy": health.is_healthy,
                        "latency_ms": health.latency_ms,
                        "diagnostic_message": health.diagnostic_message,
                    }
        else:
            desc = await msm._registry.get_model(target_id)
            if desc is None:
                resp_payload = {
                    "model_id": target_id,
                    "status": "UNAVAILABLE",
                    "is_healthy": False,
                    "latency_ms": None,
                    "diagnostic_message": f"Model '{target_id}' not found in registry",
                }
            else:
                prov = self._orchestrator.model_manager.get_provider(desc.provider)
                if prov and prov.is_available:
                    resp_payload = {
                        "model_id": target_id,
                        "status": "UNKNOWN",
                        "is_healthy": False,
                        "latency_ms": None,
                        "diagnostic_message": f"Model registered via {desc.provider.value}; inactive (health unknown until activation)",
                    }
                else:
                    resp_payload = {
                        "model_id": target_id,
                        "status": "UNAVAILABLE",
                        "is_healthy": False,
                        "latency_ms": None,
                        "diagnostic_message": f"Provider {desc.provider.value} is unavailable or offline",
                    }

        resp_event = RuntimeEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=EventType.MODEL_HEALTH_RESPONSE,
            event_seq=self._event_bus.next_sequence(),
            timestamp=datetime.now(timezone.utc),
            session_id=conn.session_id,
            correlation_id=cmd.command_id,
            payload=resp_payload,
        )
        await conn.enqueue_message(serialize_outbound_event(resp_event))

    async def _on_bus_event(self, event: RuntimeEvent) -> None:
        """Forward an event from EventBus to the relevant connected client."""
        # Check if event is broadcast, system, model_session, or model lifecycle event
        async with self._lock:
            if (
                event.session_id in {"system", "broadcast", "model_session"}
                or event.event_type.value.startswith("MODEL_")
            ):
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

