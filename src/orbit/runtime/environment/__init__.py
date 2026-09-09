"""ORBIT Environment Providers & Registry.

Decouples environment primitives (SPREADSHEET_WRITE, BROWSER_NAVIGATE, FILE_WRITE, etc.)
from underlying tool and application implementations via clean provider contracts.
"""

from orbit.runtime.environment.registry import (
    EnvironmentProvider,
    EnvironmentProviderRegistry,
    ProviderExecutionResult,
)

__all__ = [
    "EnvironmentProvider",
    "EnvironmentProviderRegistry",
    "ProviderExecutionResult",
]
