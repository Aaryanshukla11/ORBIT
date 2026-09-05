"""Unit tests for session manager."""

import pytest

from orbit.contracts.sessions import DisconnectionPolicy, SessionState
from orbit.gateway.session_manager import SessionManager


@pytest.mark.asyncio
async def test_session_creation_and_registration():
    mgr = SessionManager()
    session = await mgr.create_session(session_id="sess_test_1", disconnection_policy=DisconnectionPolicy.PAUSE_ACTIVE_TASKS)
    assert session.session_id == "sess_test_1"
    assert session.state == SessionState.CREATED
    assert session.disconnection_policy == DisconnectionPolicy.PAUSE_ACTIVE_TASKS

    # Register connection
    updated = await mgr.register_connection(
        session_id="sess_test_1",
        connection_id="conn_01",
        client_ip="127.0.0.1",
        user_agent="TestRunner",
    )
    assert updated.state == SessionState.ACTIVE
    assert updated.connection is not None
    assert updated.connection.connection_id == "conn_01"


@pytest.mark.asyncio
async def test_session_disconnect_handling():
    mgr = SessionManager()
    await mgr.register_connection(session_id="sess_disc", connection_id="conn_disc")

    disc_info = await mgr.handle_disconnect("conn_disc")
    assert disc_info is not None
    session, policy = disc_info
    assert session.session_id == "sess_disc"
    assert session.state == SessionState.DISCONNECTED
    assert session.connection is None
    assert policy == DisconnectionPolicy.PAUSE_ACTIVE_TASKS


@pytest.mark.asyncio
async def test_session_heartbeat():
    mgr = SessionManager()
    await mgr.register_connection(session_id="sess_hb", connection_id="conn_hb")
    res = await mgr.record_heartbeat("conn_hb")
    assert res is True

    res_missing = await mgr.record_heartbeat("unknown_conn")
    assert res_missing is False
