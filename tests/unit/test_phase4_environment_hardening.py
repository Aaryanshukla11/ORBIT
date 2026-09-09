"""Unit tests for Phase 4: EnvironmentProvider Hardening, Zero Physical OS Bypass & Artifact Lifecycle."""

import asyncio
import os
from pathlib import Path
import tempfile
import pytest

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType
from orbit.runtime.environment.registry import (
    EnvironmentProviderRegistry,
    get_default_environment_registry,
)
from orbit.runtime.environment.shell_provider import (
    RestrictedShellPolicy,
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
    NullImageGenerationProvider,
)
from orbit.runtime.environment.environment_operation_verifier import (
    EnvironmentOperationRequest,
    EnvironmentOperationType,
    EnvironmentOperationVerifier,
    EnvironmentSafetyPolicy,
    EnvironmentVerificationResult,
)


# ==============================================================================
# TEST SUITE 1: Zero Physical OS Bypass & Restricted Shell
# ==============================================================================

@pytest.mark.asyncio
async def test_shell_zero_physical_bypass_blocks_gui_spawning():
    """Prove that shell provider strictly blocks GUI-spawning commands without invoking subprocess."""
    provider = ShellExecutionProvider()
    assert await provider.is_available() is True

    prohibited_gui_commands = [
        "notepad.exe",
        "notepad file.txt",
        "calc.exe",
        "mspaint",
        "cmd.exe /c start notepad",
        "start-process notepad",
        "explorer.exe .",
        "winword.exe report.docx",
    ]

    for cmd in prohibited_gui_commands:
        action = AbstractAction(
            action_type=AbstractActionType.SHELL_EXECUTE,
            parameters={"command": cmd},
            expected_effect="Attempt physical GUI launch",
        )
        # Permissions check must fail closed
        assert await provider.check_permissions(action) is False, f"Permission check should fail for {cmd}"

        # Execution must fail immediately without invoking subprocess
        result = await provider.execute(action)
        assert result.success is False
        assert "COMMAND_NOT_PERMITTED" in result.error
        assert "Physical OS bypass attempt" in result.error or "prohibited in environment shell" in result.error


@pytest.mark.asyncio
async def test_shell_blocks_ui_automation_and_sendkeys():
    """Prove that shell provider strictly blocks SendKeys and UI automation backdoors."""
    provider = ShellExecutionProvider()

    ui_backdoors = [
        '[System.Windows.Forms.SendKeys]::SendWait("hello")',
        "wscript.shell sendkeys {ENTER}",
        "mouse_event 0 100 100 0 0",
        "keybd_event 0x41 0 0 0",
    ]

    for cmd in ui_backdoors:
        action = AbstractAction(
            action_type=AbstractActionType.SHELL_EXECUTE,
            parameters={"command": cmd},
            expected_effect="Attempt UI automation bypass",
        )
        result = await provider.execute(action)
        assert result.success is False
        assert "COMMAND_NOT_PERMITTED" in result.error
        assert "UI automation pattern" in result.error


@pytest.mark.asyncio
async def test_shell_blocks_destructive_commands():
    """Prove that destructive system commands are blocked."""
    provider = ShellExecutionProvider()

    destructive_cmds = [
        "format C:",
        "diskpart",
        "shutdown /s /t 0",
        "rmdir /s /q C:\\Windows",
    ]

    for cmd in destructive_cmds:
        action = AbstractAction(
            action_type=AbstractActionType.SHELL_EXECUTE,
            parameters={"command": cmd},
            expected_effect="Attempt destructive command",
        )
        result = await provider.execute(action)
        assert result.success is False
        assert "COMMAND_NOT_PERMITTED" in result.error


@pytest.mark.asyncio
async def test_shell_executes_safe_non_physical_command():
    """Verify that safe non-physical commands execute successfully and capture stdout/stderr."""
    provider = ShellExecutionProvider()

    # Use python -c which works cross-platform
    action = AbstractAction(
        action_type=AbstractActionType.SHELL_EXECUTE,
        parameters={"command": 'python -c "print(\'orbit_non_physical_ok\')"', "timeout_seconds": 10},
        expected_effect="Run non-physical cli test",
    )

    assert await provider.check_permissions(action) is True
    result = await provider.execute(action)
    assert result.success is True
    assert "orbit_non_physical_ok" in result.output["stdout"]
    assert result.output["exit_code"] == 0
    assert result.metadata.get("zero_physical_bypass_enforced") is True


@pytest.mark.asyncio
async def test_shell_enforces_allowlist():
    """Verify that configured allowlist blocks unlisted commands."""
    policy = RestrictedShellPolicy(allowlist=["python", "git status"])
    provider = ShellExecutionProvider(policy=policy)

    # Allowed command prefix
    allowed_action = AbstractAction(
        action_type=AbstractActionType.SHELL_EXECUTE,
        parameters={"command": 'python -c "print(42)"'},
        expected_effect="Run allowlisted command",
    )
    assert await provider.check_permissions(allowed_action) is True

    # Disallowed command
    disallowed_action = AbstractAction(
        action_type=AbstractActionType.SHELL_EXECUTE,
        parameters={"command": "dir"},
        expected_effect="Run non-allowlisted command",
    )
    assert await provider.check_permissions(disallowed_action) is False
    res = await provider.execute(disallowed_action)
    assert res.success is False
    assert "not in the approved allowlist" in res.error


# ==============================================================================
# TEST SUITE 2: LocalFileProvider Non-Physical Filesystem Operations
# ==============================================================================

@pytest.mark.asyncio
async def test_local_file_provider_read_and_write():
    """Verify safe FILE_WRITE and FILE_READ through LocalFileProvider."""
    with tempfile.TemporaryDirectory() as tmpdir:
        provider = LocalFileProvider(allowed_directories=[tmpdir])
        assert await provider.is_available() is True

        test_file = os.path.join(tmpdir, "subdir", "hello.txt")

        # 1. Test FILE_WRITE with automatic parent directory creation
        write_action = AbstractAction(
            action_type=AbstractActionType.FILE_WRITE,
            parameters={
                "path": test_file,
                "content": "Line 1: Hello Orbit\nLine 2: Autonomous Desktop Agent",
                "create_parents": True,
            },
            expected_effect="Write text to file",
        )
        assert await provider.check_permissions(write_action) is True
        write_res = await provider.execute(write_action)
        assert write_res.success is True
        assert os.path.exists(test_file)

        # 2. Test FILE_READ
        read_action = AbstractAction(
            action_type=AbstractActionType.FILE_READ,
            parameters={"path": test_file},
            expected_effect="Read written file",
        )
        assert await provider.check_permissions(read_action) is True
        read_res = await provider.execute(read_action)
        assert read_res.success is True
        assert "Hello Orbit" in read_res.output["content"]
        assert read_res.output["lines_count"] == 2
        assert read_res.output["is_binary"] is False


@pytest.mark.asyncio
async def test_local_file_provider_sandbox_enforcement():
    """Verify that path outside allowed sandbox directory is rejected."""
    with tempfile.TemporaryDirectory() as allowed_dir:
        with tempfile.TemporaryDirectory() as outside_dir:
            provider = LocalFileProvider(allowed_directories=[allowed_dir])

            outside_file = os.path.join(outside_dir, "secret.txt")
            action = AbstractAction(
                action_type=AbstractActionType.FILE_READ,
                parameters={"path": outside_file},
                expected_effect="Attempt unauthorized read outside sandbox",
            )

            assert await provider.check_permissions(action) is False
            res = await provider.execute(action)
            assert res.success is False
            assert "FILE_PERMISSION_DENIED" in res.error


# ==============================================================================
# TEST SUITE 3: Artifact-Only Image Generation
# ==============================================================================

class MockImageGenBackend(ImageGenerationProvider):
    """Mock generative model that produces valid PNG artifacts on disk."""

    def is_available(self) -> bool:
        return True

    async def generate_image(self, prompt: str, constraints=None) -> GeneratedImageResult:
        # Minimal valid 1x1 PNG bytes
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
            model_id="mock-diffusion-v1",
            mime_type="image/png",
        )


@pytest.mark.asyncio
async def test_artifact_image_gen_provider_produces_file_artifact():
    """Prove ArtifactImageGenProvider produces verified file artifacts on disk without OS dispatch."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backend = MockImageGenBackend()
        provider = ArtifactImageGenProvider(
            image_gen_backend=backend,
            default_output_dir=tmpdir,
        )
        assert await provider.is_available() is True

        action = AbstractAction(
            action_type=AbstractActionType.IMAGE_GENERATE,
            parameters={"prompt": "A scenic sunset over a cybernetic metropolis"},
            expected_effect="Generate image artifact",
        )
        assert await provider.check_permissions(action) is True

        res = await provider.execute(action)
        assert res.success is True
        saved_path = res.output["image_path"]
        assert os.path.exists(saved_path)
        assert os.path.getsize(saved_path) > 0
        assert res.metadata.get("zero_physical_authority") is True


# ==============================================================================
# TEST SUITE 4: Environment Safety Policy & Operation Verifier Lifecycle
# ==============================================================================

def test_environment_safety_policy_validation():
    """Verify that EnvironmentSafetyPolicy catches dangerous requests pre-execution."""
    policy = EnvironmentSafetyPolicy()

    # Prohibited shell attempt
    dangerous_req = EnvironmentOperationRequest(
        operation_type=EnvironmentOperationType.SHELL_EXECUTE,
        parameters={"command": "start-process notepad.exe"},
    )
    is_safe, reason = policy.validate_request(dangerous_req)
    assert is_safe is False
    assert "notepad" in reason or "start-process" in reason

    # Safe file read request
    safe_req = EnvironmentOperationRequest(
        operation_type=EnvironmentOperationType.FILE_READ,
        parameters={"path": "valid_file.txt"},
    )
    is_safe, _ = policy.validate_request(safe_req)
    assert is_safe is True


def test_environment_operation_verifier_file_write_verification():
    """Verify that EnvironmentOperationVerifier validates file existence and non-zero size."""
    verifier = EnvironmentOperationVerifier()

    with tempfile.TemporaryDirectory() as tmpdir:
        real_file = os.path.join(tmpdir, "verified.txt")
        Path(real_file).write_text("content", encoding="utf-8")

        req = EnvironmentOperationRequest(
            operation_type=EnvironmentOperationType.FILE_WRITE,
            parameters={"path": real_file, "content": "content"},
        )

        from orbit.runtime.environment.registry import ProviderExecutionResult
        provider_res = ProviderExecutionResult(
            success=True,
            output={"path": real_file, "bytes_written": 7},
        )

        v_res = verifier.verify_operation(req, provider_res)
        assert v_res.verified is True
        assert v_res.artifact_exists is True
        assert v_res.artifact_size_bytes == 7

        # Test failure case: file missing on disk
        missing_file = os.path.join(tmpdir, "nonexistent.txt")
        req_missing = EnvironmentOperationRequest(
            operation_type=EnvironmentOperationType.FILE_WRITE,
            parameters={"path": missing_file, "content": "content"},
        )
        fake_res = ProviderExecutionResult(
            success=True,
            output={"path": missing_file},
        )
        v_fail = verifier.verify_operation(req_missing, fake_res)
        assert v_fail.verified is False
        assert "was not found on disk" in v_fail.error_message


def test_environment_operation_verifier_image_magic_bytes():
    """Verify that EnvironmentOperationVerifier checks image magic bytes."""
    verifier = EnvironmentOperationVerifier()

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Valid PNG artifact
        valid_png = os.path.join(tmpdir, "valid.png")
        Path(valid_png).write_bytes(b"\x89PNG\r\n\x1a\n\x00fake_png_data")

        req = EnvironmentOperationRequest(
            operation_type=EnvironmentOperationType.IMAGE_GENERATE,
            parameters={"prompt": "test"},
        )
        from orbit.runtime.environment.registry import ProviderExecutionResult
        res = ProviderExecutionResult(
            success=True,
            output={"image_path": valid_png},
        )
        v_ok = verifier.verify_operation(req, res)
        assert v_ok.verified is True
        assert v_ok.verification_details.get("magic_bytes_verified") is True

        # 2. Corrupted / non-image artifact
        corrupt_img = os.path.join(tmpdir, "corrupted.png")
        Path(corrupt_img).write_text("This is plain text not an image", encoding="utf-8")
        res_corrupt = ProviderExecutionResult(
            success=True,
            output={"image_path": corrupt_img},
        )
        v_corrupt = verifier.verify_operation(req, res_corrupt)
        assert v_corrupt.verified is False
        assert "lacks valid image header magic bytes" in v_corrupt.error_message


# ==============================================================================
# TEST SUITE 5: Default Environment Provider Registry Resolution
# ==============================================================================

@pytest.mark.asyncio
async def test_default_environment_registry_resolves_all_non_physical_providers():
    """Verify that get_default_environment_registry resolves all canonical environment interfaces."""
    registry = get_default_environment_registry()

    # File providers
    assert await registry.resolve_provider(AbstractActionType.FILE_READ) is not None
    assert await registry.resolve_provider(AbstractActionType.FILE_WRITE) is not None

    # Shell provider
    shell_p = await registry.resolve_provider(AbstractActionType.SHELL_EXECUTE)
    assert shell_p is not None
    assert shell_p.provider_id == "restricted_shell_provider"

    # Image provider (null backend by default when unconfigured, so registered but not operational)
    # The provider instance exists in the registry
    img_providers = registry.get_all_registered_providers(AbstractActionType.IMAGE_GENERATE)
    assert len(img_providers) > 0
    assert img_providers[0].provider_id == "artifact_image_gen_provider"

    # Spreadsheet & Browser
    assert await registry.resolve_provider(AbstractActionType.SPREADSHEET_WRITE) is not None
    assert await registry.resolve_provider(AbstractActionType.BROWSER_NAVIGATE) is not None
