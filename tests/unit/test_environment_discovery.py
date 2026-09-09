"""Unit tests for EnvironmentCapabilityDiscovery and non-hallucination invariants."""

import pytest
from unittest.mock import MagicMock

from orbit.runtime.capabilities.environment_discovery import EnvironmentCapabilityDiscovery
from orbit.runtime.capabilities.models import CapabilitySource


def test_environment_discovery_real_windows_apps():
    discovery = EnvironmentCapabilityDiscovery()
    caps = discovery.discover_capabilities()

    cap_ids = {c.capability_id for c in caps}
    # On Windows, Notepad, Paint, and Calc exist in System32
    assert "ENV_APP_NOTEPAD" in cap_ids or "ENV_APP_PAINT" in cap_ids
    for c in caps:
        assert c.source == CapabilitySource.ENVIRONMENT_APP
        assert "executable_path" in c.metadata


def test_non_hallucination_invariant_fake_apps():
    discovery = EnvironmentCapabilityDiscovery()

    # Must return False for non-existent apps
    assert discovery.is_app_installed("NonExistentPhotoshopPro9999") is False
    assert discovery.get_app_path("NonExistentPhotoshopPro9999") is None
    assert discovery.is_app_installed("FakeSuperArtGenerator") is False


def test_environment_discovery_ai_model_probing():
    # Mock ModelSessionManager without generative image capabilities
    mock_msm = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.capabilities = ["text_generation", "code_completion"]
    mock_msm.get_active_context.return_value = mock_ctx
    mock_msm.get_registered_providers.return_value = []

    discovery = EnvironmentCapabilityDiscovery(model_session_manager=mock_msm)
    assert discovery.has_generative_image_model() is False

    caps = discovery.discover_capabilities(force_refresh=True)
    assert not any(c.capability_id == "ENV_MODEL_IMAGE_GEN" for c in caps)

    # Now mock active context WITH image generation
    mock_ctx.capabilities = ["text_generation", "image_generation"]
    mock_msm.get_active_context.return_value = mock_ctx

    assert discovery.has_generative_image_model() is True
    caps = discovery.discover_capabilities(force_refresh=True)
    assert any(c.capability_id == "ENV_MODEL_IMAGE_GEN" for c in caps)
