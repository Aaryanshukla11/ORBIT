"""Session lifecycle and connection registry manager."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from orbit.contracts.sessions import (
    ClientConnectionInfo,
    DisconnectionPolicy,
    Session,
    SessionState,
)

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages active operator sessions and client connection tracking."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}
        self._connection_map: Dict[str, str] = {}  # connection_id -> session_id
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        session_id: Optional[str] = None,
        disconnection_policy: DisconnectionPolicy = DisconnectionPolicy.PAUSE_ACTIVE_TASKS,
    ) -> Session:
        """Create a new operator session record."""
        sid = session_id or f"sess_{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        session = Session(
            session_id=sid,
            state=SessionState.CREATED,
            created_at=now,
            updated_at=now,
            disconnection_policy=disconnection_policy,
        )
        async with self._lock:
            self._sessions[sid] = session
        logger.info("Session created: %s (Policy: %s)", sid, disconnection_policy)
        return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Fetch session by ID."""
        async with self._lock:
            session = self._sessions.get(session_id)
            return session.model_copy() if session else None

    async def get_session_by_connection(self, connection_id: str) -> Optional[Session]:
        """Fetch session by connection ID."""
        async with self._lock:
            sid = self._connection_map.get(connection_id)
            if not sid:
                return None
            session = self._sessions.get(sid)
            return session.model_copy() if session else None

    async def register_connection(
        self,
        session_id: str,
        connection_id: str,
        client_ip: str = "127.0.0.1",
        user_agent: str = "ORBIT-Client/1.0",
    ) -> Session:
        """Associate an active WebSocket connection with a session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                # Auto-create if not exists
                now = datetime.now(timezone.utc)
                session = Session(
                    session_id=session_id,
                    state=SessionState.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
                self._sessions[session_id] = session

            now = datetime.now(timezone.utc)
            conn_info = ClientConnectionInfo(
                connection_id=connection_id,
                client_ip=client_ip,
                user_agent=user_agent,
                connected_at=now,
                last_heartbeat_at=now,
            )
            session.connection = conn_info
            session.state = SessionState.ACTIVE
            session.updated_at = now
            self._connection_map[connection_id] = session_id

            logger.info("Connection %s registered for session %s", connection_id, session_id)
            return session.model_copy()

    async def handle_disconnect(self, connection_id: str) -> Optional[Tuple[Session, DisconnectionPolicy]]:
        """Handle client WebSocket disconnection and determine policy action."""
        async with self._lock:
            sid = self._connection_map.pop(connection_id, None)
            if not sid:
                return None

            session = self._sessions.get(sid)
            if not session:
                return None

            now = datetime.now(timezone.utc)
            session.connection = None
            session.state = SessionState.DISCONNECTED
            session.updated_at = now

            logger.info("Session %s disconnected (Connection: %s)", sid, connection_id)
            return session.model_copy(), session.disconnection_policy

    async def record_heartbeat(self, connection_id: str) -> bool:
        """Update last heartbeat timestamp for a connection."""
        async with self._lock:
            sid = self._connection_map.get(connection_id)
            if not sid:
                return False
            session = self._sessions.get(sid)
            if session and session.connection:
                session.connection.last_heartbeat_at = datetime.now(timezone.utc)
                return True
            return False

    async def list_active_sessions(self) -> List[Session]:
        """List all currently active sessions."""
        async with self._lock:
            return [s.model_copy() for s in self._sessions.values() if s.state == SessionState.ACTIVE]
