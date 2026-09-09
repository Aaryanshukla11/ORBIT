"""Integration tests for Phase 4: EnvironmentProvider Hardening and Artifact Lifecycle Integration."""

import asyncio
import os
from pathlib import Path
import tempfile
import pytest

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionOutcomeContract,
    SemanticTarget,
)
from orbit.runtime.cognitive.models import (
    CurrentStateObservation,
    StructuredObjective,
)
from orbit.runtime.cognitive.primitive_validator import PrimitiveValidator
from orbit.runtime.cognitive.primitive_execution_controller import (
    PrimitiveExecutionController,
)
from orbit.runtime.environment.registry import (
    EnvironmentProviderRegistry,
    get_default_environment_registry,
)
from orbit.runtime.environment.shell_provider import (
    ShellExecutionProvider,
)
from orbit.runtime.environment.file_providers import (
    LocalFileProvider,
)
from orbit.runtime.environment.image_providers import (
    ArtifactImageGenProvider,
)
from orbit.runtime.capabilities.execution.image_gen_provider import (
    ImageGenerationProvider,
    GeneratedImageResult,
)
from orbit.runtime.environment.environment_operation_verifier import (
    EnvironmentOperationRequest,
    EnvironmentOperationType,
    EnvironmentOperationVerifier,
    EnvironmentSafetyPolicy,
)


class MockGenImageBackend(ImageGenerationProvider):
    def is_available(self) -> bool:
        return True

    async def generate_image(self, prompt: str, constraints=None) -> GeneratedImageResult:
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        return GeneratedImageResult(
            success=True,
            image_bytes=png_bytes,
            width=1,
            height=1,
            model_id="mock-stable-diffusion",
            mime_type="image/png",
        )


@pytest.mark.asyncio
async def test_end_to_end_file_operations_lifecycle():
    """Verify end-to-end FILE_WRITE and FILE_READ through provider and verifier lifecycle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = EnvironmentProviderRegistry()
        file_provider = LocalFileProvider(allowed_directories=[tmpdir])
        registry.register(AbstractActionType.FILE_WRITE, file_provider)
        registry.register(AbstractActionType.FILE_READ, file_provider)

        safety_policy = EnvironmentSafetyPolicy(allowed_directories=[tmpdir])
        verifier = EnvironmentOperationVerifier()

        target_path = os.path.join(tmpdir, "reports", "q4_metrics.json")
        json_payload = '{"q4_revenue": 1500000, "status": "verified"}'

        # Step 1: Pre-execution safety validation
        write_req = EnvironmentOperationRequest(
            operation_type=EnvironmentOperationType.FILE_WRITE,
            parameters={"path": target_path, "content": json_payload},
        )
        is_safe, safety_err = safety_policy.validate_request(write_req)
        assert is_safe is True
        assert safety_err is None

        # Step 2: Resolve provider and execute
        provider = await registry.resolve_provider(AbstractActionType.FILE_WRITE)
        assert provider is not None
        action = AbstractAction(
            action_type=AbstractActionType.FILE_WRITE,
            parameters={"path": target_path, "content": json_payload},
            expected_effect="Write Q4 metrics JSON file",
        )
        exec_res = await provider.execute(action)
        assert exec_res.success is True

        # Step 3: Post-execution artifact verification
        verif_res = verifier.verify_operation(write_req, exec_res)
        assert verif_res.verified is True
        assert verif_res.artifact_exists is True
        assert verif_res.artifact_size_bytes == len(json_payload.encode("utf-8"))

        # Step 4: Verify read lifecycle
        read_req = EnvironmentOperationRequest(
            operation_type=EnvironmentOperationType.FILE_READ,
            parameters={"path": target_path},
        )
        assert safety_policy.validate_request(read_req)[0] is True
        read_action = AbstractAction(
            action_type=AbstractActionType.FILE_READ,
            parameters={"path": target_path},
            expected_effect="Read Q4 metrics",
        )
        read_provider = await registry.resolve_provider(AbstractActionType.FILE_READ)
        assert read_provider is not None
        read_res = await read_provider.execute(read_action)
        assert read_res.success is True
        read_verif = verifier.verify_operation(read_req, read_res)
        assert read_verif.verified is True
        assert read_res.output["content"] == json_payload


@pytest.mark.asyncio
async def test_end_to_end_zero_physical_bypass_shell_defense():
    """Verify that any physical GUI spawn or UI automation attempt via shell is intercepted."""
    registry = EnvironmentProviderRegistry()
    shell_provider = ShellExecutionProvider()
    registry.register(AbstractActionType.SHELL_EXECUTE, shell_provider)

    safety_policy = EnvironmentSafetyPolicy()
    verifier = EnvironmentOperationVerifier()

    # Case A: Attack via GUI process spawn
    bypass_attempts = [
        "powershell -c Start-Process notepad.exe",
        "calc.exe",
        "cmd.exe /c start mspaint.exe",
        "powershell -c [System.Windows.Forms.SendKeys]::SendWait('hack')",
    ]

    for attack_cmd in bypass_attempts:
        req = EnvironmentOperationRequest(
            operation_type=EnvironmentOperationType.SHELL_EXECUTE,
            parameters={"command": attack_cmd},
        )
        # 1. Intercepted at pre-flight safety policy
        is_safe, reason = safety_policy.validate_request(req)
        assert is_safe is False
        assert reason is not None

        # 2. Intercepted if dispatched to provider
        action = AbstractAction(
            action_type=AbstractActionType.SHELL_EXECUTE,
            parameters={"command": attack_cmd},
            expected_effect="Attempt physical OS bypass",
        )
        res = await shell_provider.execute(action)
        assert res.success is False
        assert "COMMAND_NOT_PERMITTED" in res.error

        # 3. Verifier fails closed on failed provider execution
        v_res = verifier.verify_operation(req, res)
        assert v_res.verified is False


@pytest.mark.asyncio
async def test_end_to_end_generative_image_artifact_lifecycle():
    """Verify that generative image requests produce verified file artifacts without OS dispatch."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = EnvironmentProviderRegistry()
        backend = MockGenImageBackend()
        image_provider = ArtifactImageGenProvider(
            image_gen_backend=backend,
            default_output_dir=tmpdir,
        )
        registry.register(AbstractActionType.IMAGE_GENERATE, image_provider)

        safety_policy = EnvironmentSafetyPolicy()
        verifier = EnvironmentOperationVerifier()

        req = EnvironmentOperationRequest(
            operation_type=EnvironmentOperationType.IMAGE_GENERATE,
            parameters={"prompt": "Diagram of an autonomous agent architecture"},
        )
        assert safety_policy.validate_request(req)[0] is True

        provider = await registry.resolve_provider(AbstractActionType.IMAGE_GENERATE)
        assert provider is not None

        action = AbstractAction(
            action_type=AbstractActionType.IMAGE_GENERATE,
            parameters={"prompt": "Diagram of an autonomous agent architecture"},
            expected_effect="Synthesize architectural diagram artifact",
        )
        exec_res = await provider.execute(action)
        assert exec_res.success is True
        saved_path = exec_res.output["image_path"]

        # Post-execution verification proves physical file existence and PNG magic bytes
        v_res = verifier.verify_operation(req, exec_res)
        assert v_res.verified is True
        assert v_res.artifact_exists is True
        assert v_res.artifact_size_bytes > 0
        assert v_res.verification_details.get("magic_bytes_verified") is True
