"""Model Installation and Weight Ingestion Subsystem (Milestone M1.9 Step 2).

Provides asynchronous model installation, progress streaming, and provider-specific pull execution.

SAFETY INVARIANT:
Live download of multi-gigabyte models is strictly guarded by the ORBIT_ENABLE_LIVE_MODEL_INSTALL_TESTS
environment variable. Automated test suites use mocked/injected streams.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from typing import Any, AsyncIterator, Callable, Dict, List, Optional
import httpx

from orbit.runtime.models.models import (
    InstallationProgress,
    InstallationRequest,
    InstallationResult,
    InstallationStage,
    ModelDescriptor,
    ModelProviderKind,
)
from orbit.runtime.model_providers.ollama import OllamaProvider

logger = logging.getLogger(__name__)


class ModelInstallationError(Exception):
    """Base exception for model installation failures."""
    pass


class InstallationProvider(ABC):
    """Abstract installer backend for a specific model runtime."""

    @property
    def target_runtime(self) -> ModelProviderKind:
        """Alias for provider_kind."""
        return self.provider_kind

    @property
    @abstractmethod
    def provider_kind(self) -> ModelProviderKind:
        ...

    @abstractmethod
    async def install_model(
        self,
        request: InstallationRequest,
    ) -> AsyncIterator[InstallationProgress]:
        """Execute installation / pull of the requested model and yield progress."""
        ...


class OllamaInstallationProvider(InstallationProvider):
    """Installer backend executing pulls against the local Ollama daemon."""

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:11434",
        client: Optional[httpx.AsyncClient] = None,
        timeout: float = 300.0,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=3.0))
        self._own_client = client is None

    @property
    def provider_kind(self) -> ModelProviderKind:
        return ModelProviderKind.OLLAMA

    async def install_model(
        self,
        request: InstallationRequest,
    ) -> AsyncIterator[InstallationProgress]:
        url = f"{self._endpoint}/api/pull"
        payload = {
            "name": request.model_name,
            "insecure": request.insecure,
            "stream": True,
        }

        yield InstallationProgress(
            model_name=request.model_name,
            target_runtime=self.provider_kind,
            stage=InstallationStage.INITIALIZING,
            percent=0.0,
            percent_complete=0.0,
            status_message="Connecting to Ollama daemon...",
        )

        try:
            async with self._client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    err_text = await response.aread()
                    yield InstallationProgress(
                        model_name=request.model_name,
                        target_runtime=self.provider_kind,
                        stage=InstallationStage.FAILED,
                        percent=0.0,
                        percent_complete=0.0,
                        error_message=f"Ollama pull failed (HTTP {response.status_code}): {err_text.decode('utf-8', errors='ignore')}",
                    )
                    return

                total_bytes: Optional[int] = None
                downloaded_bytes = 0

                async for line in response.aiter_lines():
                    if not line or not line.strip():
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    status_msg = data.get("status", "")
                    total = data.get("total")
                    completed = data.get("completed", 0)

                    if total:
                        total_bytes = total
                        downloaded_bytes = completed

                    pct = (downloaded_bytes / total_bytes * 100.0) if total_bytes and total_bytes > 0 else 0.0

                    stage = InstallationStage.DOWNLOADING
                    if "verifying" in status_msg.lower():
                        stage = InstallationStage.VERIFYING
                    elif "writing" in status_msg.lower():
                        stage = InstallationStage.WRITING
                    elif "success" in status_msg.lower():
                        stage = InstallationStage.COMPLETED
                        pct = 100.0

                    yield InstallationProgress(
                        model_name=request.model_name,
                        target_runtime=self.provider_kind,
                        stage=stage,
                        percent=round(min(100.0, max(0.0, pct)), 2),
                        percent_complete=round(min(100.0, max(0.0, pct)), 2),
                        downloaded_bytes=downloaded_bytes,
                        bytes_completed=downloaded_bytes,
                        total_bytes=total_bytes,
                        status_message=status_msg,
                    )

        except (httpx.ConnectError, httpx.ConnectTimeout) as ex:
            yield InstallationProgress(
                model_name=request.model_name,
                target_runtime=self.provider_kind,
                stage=InstallationStage.FAILED,
                percent=0.0,
                percent_complete=0.0,
                error_message=f"Cannot connect to Ollama daemon at {self._endpoint}: {ex}",
            )
        except Exception as ex:
            yield InstallationProgress(
                model_name=request.model_name,
                target_runtime=self.provider_kind,
                stage=InstallationStage.FAILED,
                percent=0.0,
                percent_complete=0.0,
                error_message=f"Model installation error: {ex}",
            )

    async def shutdown(self) -> None:
        if self._own_client and not self._client.is_closed:
            await self._client.aclose()


class ModelInstaller:
    """Central coordinator for model installation operations."""

    def __init__(self, providers: Optional[List[InstallationProvider]] = None) -> None:
        self._providers: Dict[ModelProviderKind, InstallationProvider] = {}
        if providers:
            for p in providers:
                self.register_provider(p)

    def register_provider(self, provider: InstallationProvider) -> None:
        self._providers[provider.provider_kind] = provider

    def get_provider(self, provider_kind: ModelProviderKind) -> Optional[InstallationProvider]:
        return self._providers.get(provider_kind)

    async def install(
        self,
        request: InstallationRequest,
    ) -> AsyncIterator[InstallationProgress]:
        """Dispatch installation request to the appropriate runtime provider as a progress stream."""
        provider = self.get_provider(request.provider_kind)
        if provider is None:
            yield InstallationProgress(
                model_name=request.model_name,
                target_runtime=request.provider_kind,
                stage=InstallationStage.FAILED,
                percent=0.0,
                percent_complete=0.0,
                error_message=f"No installation provider registered for '{request.provider_kind.value}'",
            )
            return

        logger.info("Starting model install: %s via %s", request.model_name, request.provider_kind.value)
        async for progress in provider.install_model(request):
            yield progress

    async def install_and_wait(
        self,
        request: InstallationRequest,
    ) -> InstallationResult:
        """Run installation to completion and return final InstallationResult."""
        start_ns = asyncio.get_event_loop().time()
        last_progress: Optional[InstallationProgress] = None

        async for progress in self.install(request):
            last_progress = progress

        duration_ms = (asyncio.get_event_loop().time() - start_ns) * 1000.0

        if last_progress and last_progress.stage in (InstallationStage.COMPLETED, InstallationStage.COMPLETE):
            return InstallationResult(
                is_success=True,
                model_name=request.model_name,
                model_id=f"{request.provider_kind.value.lower()}:{request.model_name}",
                duration_ms=round(duration_ms, 2),
            )
        else:
            err_msg = last_progress.error_message if last_progress else "Installation ended prematurely"
            return InstallationResult(
                is_success=False,
                model_name=request.model_name,
                duration_ms=round(duration_ms, 2),
                error_message=err_msg,
            )
