"""ORBIT Environment Providers & Registry.

Decouples environment primitives (SPREADSHEET_WRITE, BROWSER_NAVIGATE, FILE_WRITE, SHELL_EXECUTE, IMAGE_GENERATE, etc.)
from underlying tool and application implementations via clean provider contracts.
Enforces non-physical separation, zero physical OS bypass, and artifact verification lifecycle.
"""

from orbit.runtime.environment.registry import (
    EnvironmentProvider,
    EnvironmentProviderRegistry,
    ProviderExecutionResult,
    get_default_environment_registry,
)
from orbit.runtime.environment.shell_provider import (
    RestrictedShellPolicy,
    ShellExecutionProvider,
    ShellSecurityViolation,
)
from orbit.runtime.environment.file_providers import (
    LocalFileProvider,
)
from orbit.runtime.environment.drawing_provider import (
    CanvasDrawingProvider,
)
from orbit.runtime.environment.environment_operation_verifier import (
    EnvironmentOperationRequest,
    EnvironmentOperationType,
    EnvironmentOperationVerifier,
    EnvironmentSafetyPolicy,
    EnvironmentVerificationResult,
)

__all__ = [
    "EnvironmentProvider",
    "EnvironmentProviderRegistry",
    "ProviderExecutionResult",
    "get_default_environment_registry",
    "RestrictedShellPolicy",
    "ShellExecutionProvider",
    "ShellSecurityViolation",
    "LocalFileProvider",
    "ArtifactImageGenProvider",
    "CanvasDrawingProvider",
    "EnvironmentOperationRequest",
    "EnvironmentOperationType",
    "EnvironmentOperationVerifier",
    "EnvironmentSafetyPolicy",
    "EnvironmentVerificationResult",
]
