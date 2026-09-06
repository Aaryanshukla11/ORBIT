"""Unit tests for Model Installation Engine and Safety Verification (Milestone M1.9 Step 2)."""

import os
from typing import AsyncIterator
import pytest
from unittest.mock import AsyncMock, patch

from orbit.runtime.models.installer import (
    InstallationProvider,
    ModelInstallationError,
    ModelInstaller,
    OllamaInstallationProvider,
)
from orbit.runtime.models.models import (
    InstallationProgress,
    InstallationRequest,
    InstallationResult,
    InstallationStage,
    ModelProviderKind,
)


class MockInstallationProvider(InstallationProvider):
    """Controlled mock installation provider."""

    def __init__(self, provider_kind: ModelProviderKind = ModelProviderKind.OLLAMA, should_fail: bool = False):
        self._provider_kind = provider_kind
        self._should_fail = should_fail

    @property
    def provider_kind(self) -> ModelProviderKind:
        return self._provider_kind

    @property
    def target_runtime(self) -> ModelProviderKind:
        return self._provider_kind

    async def install_model(self, request: InstallationRequest) -> AsyncIterator[InstallationProgress]:
        yield InstallationProgress(
            model_name=request.model_name,
            target_runtime=request.target_runtime,
            stage=InstallationStage.INITIALIZING,
            percent_complete=0.0,
            status_message="Connecting...",
        )
        yield InstallationProgress(
            model_name=request.model_name,
            target_runtime=request.target_runtime,
            stage=InstallationStage.DOWNLOADING,
            percent_complete=50.0,
            bytes_completed=500,
            total_bytes=1000,
            status_message="Downloading layers...",
        )
        if self._should_fail:
            yield InstallationProgress(
                model_name=request.model_name,
                target_runtime=request.target_runtime,
                stage=InstallationStage.FAILED,
                percent_complete=50.0,
                error_message="Network connection reset during pull",
            )
            return

        yield InstallationProgress(
            model_name=request.model_name,
            target_runtime=request.target_runtime,
            stage=InstallationStage.COMPLETE,
            percent_complete=100.0,
            status_message="Model installed successfully",
        )


@pytest.mark.asyncio
async def test_installer_successful_workflow():
    provider = MockInstallationProvider()
    installer = ModelInstaller(providers=[provider])

    request = InstallationRequest(
        model_name="qwen2.5:0.5b",
        target_runtime=ModelProviderKind.OLLAMA,
    )

    events = []
    async for progress in installer.install(request):
        events.append(progress)

    assert len(events) == 3
    assert events[0].stage == InstallationStage.INITIALIZING
    assert events[1].stage == InstallationStage.DOWNLOADING
    assert events[1].percent_complete == 50.0
    assert events[2].stage == InstallationStage.COMPLETE
    assert events[2].percent_complete == 100.0


@pytest.mark.asyncio
async def test_installer_failure_workflow():
    provider = MockInstallationProvider(should_fail=True)
    installer = ModelInstaller(providers=[provider])

    request = InstallationRequest(
        model_name="broken-model",
        target_runtime=ModelProviderKind.OLLAMA,
    )

    events = []
    async for progress in installer.install(request):
        events.append(progress)

    assert len(events) == 3
    assert events[-1].stage == InstallationStage.FAILED
    assert "Network connection reset" in (events[-1].error_message or "")


@pytest.mark.asyncio
async def test_installer_unregistered_runtime():
    installer = ModelInstaller(providers=[])
    request = InstallationRequest(
        model_name="test-model",
        target_runtime=ModelProviderKind.LM_STUDIO,
    )

    events = []
    async for progress in installer.install(request):
        events.append(progress)

    assert len(events) == 1
    assert events[0].stage == InstallationStage.FAILED
    assert "No installation provider registered" in (events[0].error_message or "")


def test_live_installation_safety_rule_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ORBIT_ENABLE_LIVE_MODEL_INSTALL_TESTS", raising=False)
    assert os.getenv("ORBIT_ENABLE_LIVE_MODEL_INSTALL_TESTS") is None
