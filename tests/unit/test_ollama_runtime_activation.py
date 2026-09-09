"""Unit regression tests for Ollama model activation chain, timeout budget, and LOCAL classification.

Covers:
1. Ollama preload respecting activation timeout (propagated from activation request).
2. Preload failure preserving actual failure reasons (timeout, connection refused, 404, HTTP error).
3. Ollama and LM Studio classified as LOCAL (case-insensitive, regardless of localhost/127.0.0.1).
4. Successful model activation followed by inference execution.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.model_providers.ollama import (
    OllamaModelNotFoundError,
    OllamaProvider,
    OllamaProviderError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from orbit.runtime.model_runtime.contracts import (
    ModelActivationRequest,
    ModelRuntimeKind,
    ModelRuntimeStatus,
)
from orbit.runtime.model_runtime.providers.local import OllamaRuntimeAdapter
from orbit.runtime.model_runtime.router import ModelRouter
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models.capabilities import ModelCapabilityProfile
from orbit.runtime.models.models import (
    ModelCapability,
    ModelChatMessage,
    ModelChatRequest,
    ModelDescriptor,
    ModelProviderKind,
    ModelSourceType,
    ProviderHealth,
    ProviderHealthStatus,
)


def _make_mock_client():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.is_closed = False
    return client


class TestOllamaRuntimeActivationRegression(unittest.IsolatedAsyncioTestCase):
    """Regression tests for production runtime activation chain fixes."""

    def setUp(self):
        self.descriptor = ModelDescriptor(
            model_id="ollama:qwen2.5:latest",
            provider=ModelProviderKind.OLLAMA,
            provider_model_name="qwen2.5:latest",
            display_name="Qwen 2.5 Latest",
            capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT},
            source_type=ModelSourceType.LOCAL_RUNTIME,
            endpoint="http://127.0.0.1:11434",
        )
        self.healthy_provider_health = ProviderHealth(
            provider=ModelProviderKind.OLLAMA,
            endpoint="http://127.0.0.1:11434",
            status=ProviderHealthStatus.HEALTHY,
            latency_ms=5.0,
            diagnostic_message="Ollama runtime is reachable and responsive",
        )

    # -------------------------------------------------------------------------
    # 1. Ollama Preload Respecting Activation Timeout
    # -------------------------------------------------------------------------
    async def test_ollama_preload_respects_activation_timeout(self):
        """Verify load_model passes explicit timeout_seconds to HTTP client and does not hardcode 3.0s."""
        mock_client = _make_mock_client()
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response

        provider = OllamaProvider(endpoint="http://127.0.0.1:11434", client=mock_client)

        # Call load_model with 45.0s timeout
        result = await provider.load_model("qwen2.5:latest", timeout_seconds=45.0)
        self.assertTrue(result)

        # Verify client.post was called with timeout=45.0
        mock_client.post.assert_called_once()
        _, kwargs = mock_client.post.call_args
        self.assertEqual(kwargs.get("timeout"), 45.0)

        # Verify adapter propagates timeout_seconds to load_model
        adapter = OllamaRuntimeAdapter(descriptor=self.descriptor, provider=provider)
        with patch.object(provider, "health_check", return_value=self.healthy_provider_health), \
             patch.object(provider, "discover_models", return_value=[self.descriptor]), \
             patch.object(provider, "load_model", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = True

            init_res = await adapter.initialize(timeout_seconds=75.0, preload_weights=True)
            self.assertTrue(init_res.is_success)
            mock_load.assert_called_once_with("qwen2.5:latest", timeout_seconds=75.0)

    # -------------------------------------------------------------------------
    # 2. Preload Failure Preserving Actual Failure Reason
    # -------------------------------------------------------------------------
    async def test_preload_failure_preserves_timeout_reason(self):
        """Verify ReadTimeout raises OllamaTimeoutError and adapter returns descriptive failure."""
        mock_client = _make_mock_client()
        mock_client.post.side_effect = httpx.ReadTimeout("Read timed out after 30s")

        provider = OllamaProvider(endpoint="http://127.0.0.1:11434", client=mock_client)

        with self.assertRaises(OllamaTimeoutError) as ctx:
            await provider.load_model("qwen2.5:latest", timeout_seconds=30.0)
        self.assertIn("30.0s", str(ctx.exception))

        adapter = OllamaRuntimeAdapter(descriptor=self.descriptor, provider=provider)
        with patch.object(provider, "health_check", return_value=self.healthy_provider_health), \
             patch.object(provider, "discover_models", return_value=[self.descriptor]):
            init_res = await adapter.initialize(timeout_seconds=30.0, preload_weights=True)
            self.assertFalse(init_res.is_success)
            self.assertEqual(init_res.status, ModelRuntimeStatus.FAILED)
            self.assertIn("Preload timeout", init_res.error_message)

    async def test_preload_failure_preserves_connection_refused_reason(self):
        """Verify ConnectError raises OllamaUnavailableError and adapter reports connection refused."""
        mock_client = _make_mock_client()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused to 127.0.0.1:11434")

        provider = OllamaProvider(endpoint="http://127.0.0.1:11434", client=mock_client)

        with self.assertRaises(OllamaUnavailableError) as ctx:
            await provider.load_model("qwen2.5:latest", timeout_seconds=10.0)
        self.assertIn("unreachable", str(ctx.exception).lower())

        adapter = OllamaRuntimeAdapter(descriptor=self.descriptor, provider=provider)
        with patch.object(provider, "health_check", return_value=self.healthy_provider_health), \
             patch.object(provider, "discover_models", return_value=[self.descriptor]):
            init_res = await adapter.initialize(timeout_seconds=10.0, preload_weights=True)
            self.assertFalse(init_res.is_success)
            self.assertEqual(init_res.status, ModelRuntimeStatus.UNAVAILABLE)
            self.assertIn("Connection refused", init_res.error_message)

    async def test_preload_failure_preserves_http_404_model_not_found(self):
        """Verify HTTP 404 raises OllamaModelNotFoundError and adapter reports model not found."""
        mock_client = _make_mock_client()
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        mock_response.text = "model 'non_existent' not found"
        mock_client.post.return_value = mock_response

        provider = OllamaProvider(endpoint="http://127.0.0.1:11434", client=mock_client)

        with self.assertRaises(OllamaModelNotFoundError) as ctx:
            await provider.load_model("non_existent", timeout_seconds=10.0)
        self.assertIn("not found", str(ctx.exception).lower())

        adapter = OllamaRuntimeAdapter(descriptor=self.descriptor, provider=provider)
        with patch.object(provider, "health_check", return_value=self.healthy_provider_health), \
             patch.object(provider, "discover_models", return_value=[self.descriptor]):
            init_res = await adapter.initialize(timeout_seconds=10.0, preload_weights=True)
            self.assertFalse(init_res.is_success)
            self.assertEqual(init_res.status, ModelRuntimeStatus.UNAVAILABLE)
            self.assertIn("Model not found", init_res.error_message)

    async def test_preload_failure_preserves_http_500_status(self):
        """Verify non-200/404 HTTP status raises OllamaProviderError with status code."""
        mock_client = _make_mock_client()
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.text = "CUDA out of memory"
        mock_client.post.return_value = mock_response

        provider = OllamaProvider(endpoint="http://127.0.0.1:11434", client=mock_client)

        with self.assertRaises(OllamaProviderError) as ctx:
            await provider.load_model("qwen2.5:latest", timeout_seconds=10.0)
        self.assertIn("HTTP 500", str(ctx.exception))
        self.assertIn("CUDA out of memory", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 3. Ollama Classified as LOCAL
    # -------------------------------------------------------------------------
    def test_ollama_and_lmstudio_classified_as_local(self):
        """Verify Ollama and LM Studio are always classified as LOCAL across router, profile, and diagnostics."""
        # 1. Router classification
        self.assertTrue(ModelRouter.is_local_descriptor(self.descriptor))

        lm_desc = ModelDescriptor(
            model_id="lm_studio:qwen2.5-7b",
            provider=ModelProviderKind.LM_STUDIO,
            provider_model_name="qwen2.5-7b",
            display_name="Qwen 2.5 7B LM Studio",
            capabilities={ModelCapability.CHAT},
            source_type=ModelSourceType.LOCAL_RUNTIME,
            endpoint="http://localhost:1234",
        )
        self.assertTrue(ModelRouter.is_local_descriptor(lm_desc))

        # Cloud descriptor must be False
        cloud_desc = ModelDescriptor(
            model_id="cloud:openai:gpt-4o",
            provider=ModelProviderKind.CLOUD_OPENAI,
            provider_model_name="gpt-4o",
            display_name="GPT-4o",
            capabilities={ModelCapability.CHAT},
            source_type=ModelSourceType.CLOUD_PROVIDER,
            endpoint="https://api.openai.com/v1",
        )
        self.assertFalse(ModelRouter.is_local_descriptor(cloud_desc))

        # 2. ModelCapabilityProfile classification
        ollama_profile = ModelCapabilityProfile.from_descriptor(self.descriptor)
        self.assertTrue(ollama_profile.is_local)

        lm_profile = ModelCapabilityProfile.from_descriptor(lm_desc)
        self.assertTrue(lm_profile.is_local)

        cloud_profile = ModelCapabilityProfile.from_descriptor(cloud_desc)
        self.assertFalse(cloud_profile.is_local)

        # 3. OllamaRuntimeAdapter kind
        adapter = OllamaRuntimeAdapter(descriptor=self.descriptor)
        self.assertEqual(adapter.runtime_kind, ModelRuntimeKind.LOCAL)

    # -------------------------------------------------------------------------
    # 4. Successful Model Activation Followed by Inference Flow
    # -------------------------------------------------------------------------
    async def test_successful_model_activation_and_inference_flow(self):
        """Verify full chain from SessionManager activation to genuine inference dispatch."""
        mock_client = _make_mock_client()
        # Mock health check response
        health_resp = MagicMock(spec=httpx.Response)
        health_resp.status_code = 200
        health_resp.json.return_value = {"status": "ok"}

        # Mock discover models response
        models_resp = MagicMock(spec=httpx.Response)
        models_resp.status_code = 200
        models_resp.json.return_value = {
            "models": [
                {
                    "name": "qwen2.5:latest",
                    "model": "qwen2.5:latest",
                    "details": {"family": "qwen2", "parameter_size": "7.6B"},
                }
            ]
        }

        # Mock generate preload response
        preload_resp = MagicMock(spec=httpx.Response)
        preload_resp.status_code = 200
        preload_resp.json.return_value = {"done": True, "done_reason": "load"}

        # Mock chat response
        chat_resp = MagicMock(spec=httpx.Response)
        chat_resp.status_code = 200
        chat_resp.json.return_value = {
            "message": {"role": "assistant", "content": "ORBIT MODEL RUNTIME ACTIVE"},
            "done": True,
            "total_duration": 150000000,
            "prompt_eval_count": 12,
            "eval_count": 8,
        }

        async def mock_get(url, *args, **kwargs):
            if "/api/version" in url or "/api/tags" in url:
                return models_resp
            return health_resp

        async def mock_post(url, *args, **kwargs):
            if "/api/chat" in url:
                return chat_resp
            return preload_resp

        mock_client.get.side_effect = mock_get
        mock_client.post.side_effect = mock_post

        provider = OllamaProvider(endpoint="http://127.0.0.1:11434", client=mock_client)
        event_bus = EventBus()
        session_mgr = ModelSessionManager(providers=[provider], event_bus=event_bus)
        await session_mgr.register_descriptor(self.descriptor)

        # 1. Activate
        act_req = ModelActivationRequest(
            model_id="ollama:qwen2.5:latest",
            timeout_seconds=45.0,
            preload_weights=True,
        )
        act_res = await session_mgr.activate_model(act_req)
        self.assertTrue(act_res.is_successful)
        self.assertEqual(session_mgr.get_active_model().model_id, "ollama:qwen2.5:latest")

        # 2. Inference
        active_rt = session_mgr.get_active_runtime()
        self.assertIsNotNone(active_rt)
        self.assertEqual(active_rt.runtime_kind, ModelRuntimeKind.LOCAL)

        chat_req = ModelChatRequest(
            messages=[ModelChatMessage(role="user", content="Hello")],
        )
        gen_resp = await active_rt.chat(chat_req)
        self.assertEqual(gen_resp.content, "ORBIT MODEL RUNTIME ACTIVE")
        self.assertTrue(gen_resp.done)
        self.assertEqual(gen_resp.model_id, "ollama:qwen2.5:latest")

        await session_mgr.shutdown()


if __name__ == "__main__":
    unittest.main()
