"""Integration tests for FastAPI Gateway startup, health and status endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from orbit.gateway.app import create_app


@pytest.mark.asyncio
async def test_health_endpoint():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "HEALTHY"
        assert data["version"] == "0.1.0"
        assert "system_state" in data


@pytest.mark.asyncio
async def test_status_endpoint():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "0.1.0"
        assert "active_sessions_count" in data
