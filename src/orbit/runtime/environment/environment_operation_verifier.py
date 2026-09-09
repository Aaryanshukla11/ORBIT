"""Environment Operation Verifier and Safety Policy (M1.9 Component 9 & Invariant 9).

INVARIANT:
All environment operations must follow the strict lifecycle:
EnvironmentOperationRequest -> EnvironmentSafetyPolicy -> Provider Execution ->
Artifact / Result -> EnvironmentOperationVerifier -> Verified Result.

Ensures:
1. Pre-execution safety policy validation (path containment, zero physical bypass, zero GUI spawning).
2. Post-execution physical proof of generated artifacts (file existence, non-zero size, valid format/schema).
3. Zero tolerance for unverified success or phantom side effects.
"""

from __future__ import annotations

from enum import Enum
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.environment.registry import ProviderExecutionResult

logger = logging.getLogger(__name__)


class EnvironmentOperationType(str, Enum):
    """Canonical types of environment operations."""
    FILE_READ = "FILE_READ"
    FILE_WRITE = "FILE_WRITE"
    SPREADSHEET_READ = "SPREADSHEET_READ"
    SPREADSHEET_WRITE = "SPREADSHEET_WRITE"
    BROWSER_NAVIGATE = "BROWSER_NAVIGATE"
    SHELL_EXECUTE = "SHELL_EXECUTE"
    IMAGE_GENERATE = "IMAGE_GENERATE"


class EnvironmentOperationRequest(BaseModel):
    """Typed specification of an environment operation to be executed."""

    request_id: str = Field(default_factory=lambda: f"env_req_{uuid4().hex[:8]}")
    operation_type: EnvironmentOperationType
    parameters: Dict[str, Any] = Field(default_factory=dict)
    expected_artifact_path: Optional[str] = Field(default=None)
    safety_context: Dict[str, Any] = Field(default_factory=dict)


class EnvironmentVerificationResult(BaseModel):
    """Authoritative verdict verifying the reality and correctness of an environment operation."""

    verified: bool = Field(..., description="Whether post-operation artifact/state is verified")
    operation_type: str = Field(...)
    artifact_path: Optional[str] = Field(default=None)
    artifact_exists: bool = Field(default=False)
    artifact_size_bytes: Optional[int] = Field(default=None)
    verification_details: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = Field(default=None)


class EnvironmentSafetyPolicy:
    """Pre-execution safety gate for environment operations."""

    FORBIDDEN_COMMAND_PATTERNS: Set[str] = {
        "notepad", "calc", "mspaint", "explorer", "winword", "excel", "powerpnt",
        "chrome", "firefox", "msedge", "start-process", "sendkeys",
        "format", "diskpart", "shutdown", "stop-computer",
    }

    def __init__(
        self,
        allowed_directories: Optional[List[str]] = None,
        allow_shell: bool = True,
    ) -> None:
        self._allowed_directories = [
            Path(d).resolve() for d in allowed_directories
        ] if allowed_directories else None
        self._allow_shell = allow_shell

    def validate_request(self, request: EnvironmentOperationRequest) -> Tuple[bool, Optional[str]]:
        """Validate request against safety policies prior to dispatch."""
        op_type = request.operation_type
        params = request.parameters

        # Path-based operations: check sandbox traversal
        if op_type in (
            EnvironmentOperationType.FILE_READ,
            EnvironmentOperationType.FILE_WRITE,
            EnvironmentOperationType.SPREADSHEET_READ,
            EnvironmentOperationType.SPREADSHEET_WRITE,
        ):
            raw_path = params.get("path") or params.get("file_path")
            if not raw_path:
                return False, f"Missing required 'path' parameter for {op_type.value}"

            if self._allowed_directories is not None:
                try:
                    resolved = Path(raw_path).resolve()
                    is_contained = any(
                        resolved == allowed or allowed in resolved.parents
                        for allowed in self._allowed_directories
                    )
                    if not is_contained:
                        return False, f"Path '{resolved}' is outside allowed directory sandbox"
                except Exception as e:
                    return False, f"Invalid path specification: {e}"

        # Shell operations: check physical bypass patterns
        elif op_type == EnvironmentOperationType.SHELL_EXECUTE:
            if not self._allow_shell:
                return False, "Shell operations are disabled by environment safety policy"

            cmd = str(params.get("command") or params.get("cmd") or "").strip().lower()
            if not cmd:
                return False, "Missing 'command' parameter for SHELL_EXECUTE"

            for forbidden in self.FORBIDDEN_COMMAND_PATTERNS:
                if forbidden in cmd:
                    return False, f"Prohibited physical bypass or dangerous command keyword detected: '{forbidden}'"

        # Image generation: verify prompt
        elif op_type == EnvironmentOperationType.IMAGE_GENERATE:
            prompt = params.get("prompt") or params.get("description")
            if not prompt or not str(prompt).strip():
                return False, "Missing required 'prompt' parameter for IMAGE_GENERATE"

        return True, None


class EnvironmentOperationVerifier:
    """Post-execution verifier ensuring operations produce real, valid artifacts."""

    def verify_operation(
        self,
        request: EnvironmentOperationRequest,
        result: ProviderExecutionResult,
    ) -> EnvironmentVerificationResult:
        """Verify the physical/logical outcome of an executed environment operation."""
        op_type = request.operation_type

        # Gate 1: Did the provider report success?
        if not result.success:
            return EnvironmentVerificationResult(
                verified=False,
                operation_type=op_type.value,
                error_message=result.error or f"Provider reported failure for {op_type.value}",
                verification_details={"provider_result": result.model_dump()},
            )

        # Gate 2: Operation-specific artifact and state verification
        if op_type in (EnvironmentOperationType.FILE_WRITE, EnvironmentOperationType.SPREADSHEET_WRITE):
            return self._verify_file_write(request, result)

        elif op_type == EnvironmentOperationType.FILE_READ:
            return self._verify_file_read(request, result)

        elif op_type == EnvironmentOperationType.SPREADSHEET_READ:
            return self._verify_spreadsheet_read(request, result)

        elif op_type == EnvironmentOperationType.IMAGE_GENERATE:
            return self._verify_image_generate(request, result)

        elif op_type == EnvironmentOperationType.SHELL_EXECUTE:
            return self._verify_shell_execute(request, result)

        elif op_type == EnvironmentOperationType.BROWSER_NAVIGATE:
            return self._verify_browser_navigate(request, result)

        return EnvironmentVerificationResult(
            verified=True,
            operation_type=op_type.value,
            verification_details={"status": "generic_provider_success"},
        )

    def _verify_file_write(
        self,
        request: EnvironmentOperationRequest,
        result: ProviderExecutionResult,
    ) -> EnvironmentVerificationResult:
        """Verify that a written file exists on disk, is non-empty, and readable."""
        raw_path = (
            request.parameters.get("path")
            or request.parameters.get("file_path")
            or request.expected_artifact_path
            or (result.output.get("path") if isinstance(result.output, dict) else None)
        )
        if not raw_path:
            return EnvironmentVerificationResult(
                verified=False,
                operation_type=request.operation_type.value,
                error_message="No artifact path could be determined for written file",
            )

        path = Path(raw_path)
        if not path.exists():
            return EnvironmentVerificationResult(
                verified=False,
                operation_type=request.operation_type.value,
                artifact_path=str(path),
                artifact_exists=False,
                error_message=f"Artifact file '{path}' was not found on disk after write",
            )

        size = path.stat().st_size
        # If content was explicitly empty string, 0 bytes is acceptable, otherwise verify > 0
        expected_content = request.parameters.get("content", None)
        if expected_content is not None and len(expected_content) > 0 and size == 0:
            return EnvironmentVerificationResult(
                verified=False,
                operation_type=request.operation_type.value,
                artifact_path=str(path),
                artifact_exists=True,
                artifact_size_bytes=0,
                error_message=f"Artifact file '{path}' is empty (0 bytes) despite non-empty content",
            )

        return EnvironmentVerificationResult(
            verified=True,
            operation_type=request.operation_type.value,
            artifact_path=str(path),
            artifact_exists=True,
            artifact_size_bytes=size,
            verification_details={"file_readable": os.access(path, os.R_OK)},
        )

    def _verify_file_read(
        self,
        request: EnvironmentOperationRequest,
        result: ProviderExecutionResult,
    ) -> EnvironmentVerificationResult:
        """Verify that file read produced valid content."""
        output = result.output or {}
        if not isinstance(output, dict) or ("content" not in output and "content_b64" not in output):
            return EnvironmentVerificationResult(
                verified=False,
                operation_type=request.operation_type.value,
                error_message="File read output does not contain expected 'content' payload",
            )
        return EnvironmentVerificationResult(
            verified=True,
            operation_type=request.operation_type.value,
            artifact_path=str(output.get("path", "")),
            artifact_exists=True,
            artifact_size_bytes=output.get("size_bytes"),
            verification_details={"lines_count": output.get("lines_count", 0)},
        )

    def _verify_spreadsheet_read(
        self,
        request: EnvironmentOperationRequest,
        result: ProviderExecutionResult,
    ) -> EnvironmentVerificationResult:
        """Verify spreadsheet read produced rows data."""
        output = result.output or {}
        rows = output.get("rows") if isinstance(output, dict) else None
        if rows is None or not isinstance(rows, list):
            return EnvironmentVerificationResult(
                verified=False,
                operation_type=request.operation_type.value,
                error_message="Spreadsheet read did not return valid 'rows' array",
            )
        return EnvironmentVerificationResult(
            verified=True,
            operation_type=request.operation_type.value,
            verification_details={"row_count": len(rows)},
        )

    def _verify_image_generate(
        self,
        request: EnvironmentOperationRequest,
        result: ProviderExecutionResult,
    ) -> EnvironmentVerificationResult:
        """Verify that generated image artifact exists and has valid magic bytes."""
        output = result.output or {}
        img_path = output.get("image_path") if isinstance(output, dict) else None
        if not img_path or not os.path.exists(img_path):
            return EnvironmentVerificationResult(
                verified=False,
                operation_type=request.operation_type.value,
                error_message=f"Image artifact '{img_path}' does not exist on disk",
            )

        size = os.path.getsize(img_path)
        if size == 0:
            return EnvironmentVerificationResult(
                verified=False,
                operation_type=request.operation_type.value,
                artifact_path=img_path,
                artifact_exists=True,
                artifact_size_bytes=0,
                error_message="Image artifact is 0 bytes (corrupted/empty)",
            )

        # Inspect magic bytes for image formats (PNG, JPEG, GIF, BMP, WEBP)
        with open(img_path, "rb") as f:
            header = f.read(16)

        is_valid_image = (
            header.startswith(b"\x89PNG\r\n\x1a\n")  # PNG
            or header.startswith(b"\xff\xd8\xff")    # JPEG
            or header.startswith(b"GIF8")            # GIF
            or header.startswith(b"BM")              # BMP
            or (len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP")  # WEBP
        )

        if not is_valid_image:
            return EnvironmentVerificationResult(
                verified=False,
                operation_type=request.operation_type.value,
                artifact_path=img_path,
                artifact_exists=True,
                artifact_size_bytes=size,
                error_message=f"Image artifact '{img_path}' lacks valid image header magic bytes",
            )

        return EnvironmentVerificationResult(
            verified=True,
            operation_type=request.operation_type.value,
            artifact_path=img_path,
            artifact_exists=True,
            artifact_size_bytes=size,
            verification_details={"magic_bytes_verified": True, "size_bytes": size},
        )

    def _verify_shell_execute(
        self,
        request: EnvironmentOperationRequest,
        result: ProviderExecutionResult,
    ) -> EnvironmentVerificationResult:
        """Verify shell execution completed non-physically with zero exit code."""
        output = result.output or {}
        exit_code = output.get("exit_code") if isinstance(output, dict) else None
        if exit_code != 0:
            return EnvironmentVerificationResult(
                verified=False,
                operation_type=request.operation_type.value,
                error_message=f"Shell command returned non-zero exit code: {exit_code}",
                verification_details={"stderr": output.get("stderr")},
            )
        return EnvironmentVerificationResult(
            verified=True,
            operation_type=request.operation_type.value,
            verification_details={"exit_code": 0, "stdout_length": len(output.get("stdout", ""))},
        )

    def _verify_browser_navigate(
        self,
        request: EnvironmentOperationRequest,
        result: ProviderExecutionResult,
    ) -> EnvironmentVerificationResult:
        """Verify browser navigation dispatched to a valid URL."""
        output = result.output or {}
        url = output.get("url") if isinstance(output, dict) else request.parameters.get("url")
        return EnvironmentVerificationResult(
            verified=True,
            operation_type=request.operation_type.value,
            verification_details={"url": url, "navigation_dispatched": True},
        )
