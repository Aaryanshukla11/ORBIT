"""FastAPI application factory and Gateway server endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from typing import Optional
from fastapi import FastAPI, WebSocket, Query
from fastapi.responses import JSONResponse

from orbit import __version__
from orbit.adapters.factory import create_capability_registry
from orbit.adapters.registry import CapabilityRegistry
from orbit.config import RuntimeConfig
from orbit.gateway.session_manager import SessionManager
from orbit.gateway.websocket_manager import WebSocketManager
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator

logger = logging.getLogger(__name__)


def create_app(
    orchestrator: Optional[OrbitOrchestrator] = None,
    registry: Optional[CapabilityRegistry] = None,
    config: Optional[RuntimeConfig] = None,
    session_manager: Optional[SessionManager] = None,
    event_bus: Optional[EventBus] = None,
) -> FastAPI:
    """Create and configure the FastAPI Gateway application."""

    cfg = config or RuntimeConfig()
    bus = event_bus or EventBus()
    sess_mgr = session_manager or SessionManager()

    if orchestrator is None:
        reg = registry or create_capability_registry(cfg)
        orch = OrbitOrchestrator(
            event_bus=bus,
            registry=reg,
            clock=SystemClock(),
            human_takeover_enabled=cfg.human_takeover_enabled,
        )
    else:
        orch = orchestrator

    ws_mgr = WebSocketManager(
        orchestrator=orch,
        session_manager=sess_mgr,
        event_bus=bus,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("ORBIT Gateway starting up (Adapter Mode: %s)...", cfg.adapter_mode.value)
        await orch.initialize()
        ws_mgr.initialize()
        yield
        logger.info("ORBIT Gateway shutting down...")
        await ws_mgr.shutdown()
        await orch.shutdown()
        await bus.close()

    app = FastAPI(
        title="ORBIT Gateway API",
        version=__version__,
        lifespan=lifespan,
    )

    # Store references on app state for easy inspection/testing
    app.state.config = cfg
    app.state.orchestrator = orch
    app.state.registry = orch.registry
    app.state.session_manager = sess_mgr
    app.state.event_bus = bus
    app.state.websocket_manager = ws_mgr

    @app.get("/health")
    async def health_check() -> JSONResponse:
        """Lightweight readiness and liveness probe."""
        return JSONResponse(
            content={
                "status": "HEALTHY",
                "version": __version__,
                "system_state": orch.system_state.value,
            }
        )

    @app.get("/status")
    async def get_status() -> JSONResponse:
        """Detailed runtime diagnostic report including capability health."""
        active_sessions = await sess_mgr.list_active_sessions()
        capability_healths = await orch.registry.get_health_all()
        active_model = orch.model_session_manager.get_active_context()

        return JSONResponse(
            content={
                "version": __version__,
                "system_state": orch.system_state.value,
                "active_sessions_count": len(active_sessions),
                "adapter_mode": cfg.adapter_mode.value,
                "active_model_id": active_model.model_id if active_model else None,
                "capabilities": {
                    cap_type.value: health.model_dump()
                    for cap_type, health in capability_healths.items()
                },
            }
        )

    @app.get("/api/history")
    async def get_execution_history(
        limit: int = Query(default=50, ge=1, le=500),
        status: Optional[str] = Query(default=None),
        search: Optional[str] = Query(default=None),
    ) -> JSONResponse:
        """Fetch historical execution records."""
        records = await orch.history_store.list_records(limit=limit, status_filter=status, search_query=search)
        return JSONResponse(
            content={
                "records": [r.model_dump(mode="json") for r in records],
                "total_count": len(records),
            }
        )

    @app.get("/api/history/{execution_id}")
    async def get_execution_record(execution_id: str) -> JSONResponse:
        """Fetch a specific execution record."""
        record = await orch.history_store.get_record(execution_id)
        if record is None:
            return JSONResponse(status_code=404, content={"error": "Record not found"})
        return JSONResponse(content={"record": record.model_dump(mode="json")})

    @app.delete("/api/history")
    async def clear_execution_history() -> JSONResponse:
        """Clear all historical execution records."""
        await orch.history_store.clear_history()
        return JSONResponse(content={"status": "CLEARED"})

    @app.get("/api/diagnostics")
    async def get_diagnostics() -> JSONResponse:
        """Fetch latest cached or evaluated system diagnostic report."""
        report = await orch.diagnostic_service.get_cached_or_fresh_report()
        return JSONResponse(content=report.model_dump(mode="json"))

    @app.post("/api/diagnostics/run")
    async def run_diagnostics() -> JSONResponse:
        """Trigger an on-demand real-time system diagnostic probe."""
        report = await orch.diagnostic_service.run_diagnostics()
        return JSONResponse(content=report.model_dump(mode="json"))

    @app.websocket("/ws")
    async def websocket_endpoint_default(websocket: WebSocket) -> None:
        """WebSocket connection endpoint with automatic session assignment."""
        await ws_mgr.handle_connection(websocket)

    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint_session(websocket: WebSocket, session_id: str) -> None:
        """WebSocket connection endpoint with explicit session binding."""
        await ws_mgr.handle_connection(websocket, session_id=session_id)

    return app
