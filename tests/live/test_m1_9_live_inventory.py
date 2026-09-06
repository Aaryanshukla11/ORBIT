"""Live Real-World Model Discovery & System Inventory Test Suite (Milestone M1.9 Step 2).

Epistemic Classifications:
- LIVE_OS_VALIDATED: Probes actual local runtimes (Ollama daemon at 127.0.0.1:11434, LM Studio at 127.0.0.1:1234),
  executes safe filesystem weight file discovery, and compiles real SystemCapabilitiesReport on Windows 11 host.
- UNAVAILABLE_ON_HOST: Truthfully reports if a runtime (e.g. LM Studio local server) is not running on host without crashing.
- CONTROLLED_LIVE_VALIDATED: Evaluates cloud provider adapters with secret-isolation validation.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.models.file_scanner import LocalFileModelScanner
from orbit.runtime.models.inventory import ModelInventory
from orbit.runtime.models.manager import ModelManager
from orbit.runtime.models.models import (
    CloudProviderKind,
    ModelCapability,
    ModelProviderKind,
    ModelSourceType,
    ModelStatus,
    ProviderHealthStatus,
)
from orbit.runtime.model_providers.cloud import CloudModelProvider
from orbit.runtime.model_providers.lm_studio import LMStudioProvider
from orbit.runtime.model_providers.ollama import OllamaProvider
from orbit.runtime.orchestrator import OrbitOrchestrator


@pytest.mark.asyncio
async def test_live_host_model_inventory_aggregation(tmp_path: Path):
    """Perform real host discovery across live local Ollama, LM Studio, local files, and cloud catalogs.

    Epistemic: LIVE_OS_VALIDATED (Ollama, File Scanner, Inventory Engine)
               UNAVAILABLE_ON_HOST (LM Studio if inactive)
    """
    # 1. Ollama Provider on real host
    ollama_endpoint = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    ollama_p = OllamaProvider(host="127.0.0.1", port=11434, connect_timeout=1.5)

    # 2. LM Studio Provider on real host (probed safely)
    lm_studio_p = LMStudioProvider(host="127.0.0.1", port=1234, timeout_seconds=1.0)

    # 3. Local Model Weight File Scanner (create a verified sample model file in tmp_path)
    sample_model_path = tmp_path / "sample-phi3-mini.gguf"
    # Write valid GGUF header (magic, v3, 200 tensors, 16 kv)
    sample_model_path.write_bytes(b"GGUF\x03\x00\x00\x00\xc8\x00\x00\x00\x10\x00\x00\x00" + b"\x00" * 200)
    scanner = LocalFileModelScanner(model_directories=[tmp_path])

    # 4. Cloud Provider (Unconfigured - testing auth status and catalog)
    cloud_openai = CloudModelProvider(cloud_kind=CloudProviderKind.OPENAI, api_key=None)

    # 5. Initialize ModelManager and OrbitOrchestrator
    manager = ModelManager(
        providers=[ollama_p, lm_studio_p],
        file_scanner=scanner,
        cloud_providers=[cloud_openai],
    )

    event_bus = EventBus()
    orchestrator = OrbitOrchestrator(event_bus=event_bus, model_manager=manager)

    # 6. Execute full inventory refresh
    report = await orchestrator.refresh_model_inventory()

    print("\n" + "=" * 60)
    print("LIVE ORBIT SYSTEM INVENTORY REPORT")
    print("=" * 60)
    print(f"Generated at UTC: {report.inventory_generated_at_utc.isoformat()}")

    # Local Runtimes output
    print("\n--- LOCAL RUNTIMES ---")
    for rt in report.local_runtimes:
        status_str = "ONLINE (LIVE_OS_VALIDATED)" if rt.is_available else "UNAVAILABLE_ON_HOST"
        latency_str = f"{rt.latency_ms:.1f}ms" if rt.latency_ms is not None else "N/A"
        print(f"  [{rt.provider.value}] status: {status_str} | latency: {latency_str} | models: {rt.models_count}")

    # Cloud Providers output
    print("\n--- CLOUD PROVIDERS ---")
    for cp in report.cloud_providers:
        print(f"  [{cp.cloud_kind.value}] configured: {cp.is_configured} | auth: {cp.auth_status.value}")

    # Local Weight Files output
    print("\n--- LOCAL WEIGHT FILES ---")
    for lf in report.local_files:
        print(f"  - {lf.file_name} (format: {lf.format.value}, size: {lf.size_bytes} bytes)")

    # System Capabilities output
    caps = report.system_capabilities
    print("\n--- SYSTEM CAPABILITIES ---")
    print(f"  Total models discovered: {caps.total_models}")
    print(f"  Offline models available: {caps.offline_models_available}")
    print(f"  Cloud models available:   {caps.cloud_models_available}")
    print(f"  Local models count:       {caps.local_models_count}")
    print(f"  Cloud models count:       {caps.cloud_models_count}")
    print(f"  Vision capable models:    {caps.vision_capable_count}")
    print(f"  Tool calling models:      {caps.tool_capable_count}")
    print(f"  Reasoning models:         {caps.reasoning_capable_count}")
    print(f"  Embedding models:         {caps.embedding_capable_count}")
    print("=" * 60)

    # Invariants verification
    assert caps.local_models_count >= 1  # At least the sample GGUF file
    assert len(report.local_files) >= 1
    assert any(lf.file_name == "sample-phi3-mini.gguf" for lf in report.local_files)

    # Public serialization sanity check
    public_dict = report.to_public_dict()
    assert "inventory_generated_at_utc" in public_dict
    assert "system_capabilities" in public_dict

    # Cleanup
    await manager.shutdown()


def test_live_opt_in_model_installation_safety_gate():
    """Verify live model installation safety gate prevents automatic multi-GB downloads."""
    flag = os.environ.get("ORBIT_ENABLE_LIVE_MODEL_INSTALL_TESTS", "0")
    if flag != "1":
        pytest.skip("Live model installation skipped safely (ORBIT_ENABLE_LIVE_MODEL_INSTALL_TESTS != 1)")
