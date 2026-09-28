"""ORBIT Tool Schema and Service Subsystem.

Provides structured, model-facing capability descriptors, standard JSON schema export,
strict parameter validation, and translation to canonical ORBIT AbstractActions.

Architectural Invariants:
1. Sensory & capability description only (zero direct actuation in tool layer).
2. Model tool requests must pass through ToolService -> AgentPlanner -> PlanDirective -> PrimitiveComposer -> PrimitiveExecutionController.
3. Coordinates (x, y) are strictly forbidden in parameters or targets.
4. Fail-closed validation for unknown, malformed, or unauthorized tool calls.
"""

from orbit.runtime.tools.registry import (
    DuplicateToolRegistrationError,
    InvalidToolNameError,
    ToolRegistry,
)
from orbit.runtime.tools.schema import (
    ToolCategory,
    ToolSchema,
    ToolValidationResult,
)
from orbit.runtime.tools.service import (
    StructuredToolRequest,
    ToolService,
)

__all__ = [
    "DuplicateToolRegistrationError",
    "InvalidToolNameError",
    "StructuredToolRequest",
    "ToolCategory",
    "ToolRegistry",
    "ToolSchema",
    "ToolService",
    "ToolValidationResult",
]
