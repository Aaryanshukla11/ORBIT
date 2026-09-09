"""Capability Execution Contracts for ORBIT Runtime (M1.9).

Defines execution requests, multi-state stage outcomes, capability execution results,
and the fundamental CapabilityExecutor interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from orbit.runtime.cancellation import CancellationToken


class StageOutcomeStatus(str, Enum):
    """Granular operational and verification status of a capability or strategy stage."""

    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"                    # Physical/API input accepted by host
    EFFECT_VERIFIED = "EFFECT_VERIFIED"          # Expected state delta verified on desktop
    EFFECT_UNVERIFIED = "EFFECT_UNVERIFIED"      # Dispatched but expected delta not observed
    FAILED = "FAILED"                            # Dispatch or execution threw unrecoverable error
    RECOVERING = "RECOVERING"                    # Retrying or running alternate stage recovery
    SKIPPED = "SKIPPED"                          # Skipped due to conditional logic or prior failure


class CapabilityExecutionRequest(BaseModel):
    """Envelopes all inputs required to execute a discrete capability."""

    capability_id: str = Field(..., description="Unique capability identifier (e.g. LAUNCH_APPLICATION)")
    stage_index: int = Field(default=0, description="0-indexed sequence position in strategy")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Resolved semantic parameters")
    context: Dict[str, Any] = Field(default_factory=dict, description="Runtime execution context and task data")
    timeout_seconds: float = Field(default=30.0, ge=0.5, description="Timeout budget for capability execution")
    cancel_token: Optional[Any] = Field(default=None, description="Optional cancellation token")

    model_config = {"arbitrary_types_allowed": True}


class CapabilityExecutionResult(BaseModel):
    """Strict runtime outcome returned by a CapabilityExecutor.

    INVARIANT:
    'Executor returned without exception' MUST NOT imply execution_success = True.
    dispatch_success, execution_success, and stage_status are explicitly tracked.
    """

    capability_id: str = Field(..., description="Unique capability identifier executed")
    stage_index: int = Field(default=0, description="Stage index executed")
    dispatch_success: bool = Field(..., description="Whether physical/API dispatch succeeded")
    execution_success: bool = Field(..., description="Whether capability completed its operational objective")
    stage_status: StageOutcomeStatus = Field(
        default=StageOutcomeStatus.PENDING,
        description="Detailed verification outcome status",
    )
    output: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured output data produced for downstream stage consumption",
    )
    evidence: Dict[str, Any] = Field(
        default_factory=dict,
        description="Concrete verification evidence (e.g. verified HWND, file path, pixel delta)",
    )
    failure_code: Optional[str] = Field(
        default=None,
        description="Categorical failure identifier if execution_success is False",
    )
    failure_reason: Optional[str] = Field(
        default=None,
        description="Human-readable explanation of failure",
    )
    duration_ms: float = Field(default=0.0, ge=0.0, description="Execution elapsed time in ms")
    executed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when execution concluded",
    )


class CapabilityExecutor(ABC):
    """Abstract base class and execution contract for all runtime capability executors.

    Each concrete executor binds directly to real system adapters (workspace, pointer,
    keyboard, model session, or OS APIs) and encapsulates input validation, execution,
    and outcome measurement.
    """

    def __init__(self, capability_id: str) -> None:
        self._capability_id = capability_id

    @property
    def capability_id(self) -> str:
        return self._capability_id

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this executor is operational and all required adapters are present."""
        ...

    @abstractmethod
    def validate_inputs(self, parameters: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate input parameters against this capability's schema."""
        ...

    @abstractmethod
    async def execute(
        self,
        request: CapabilityExecutionRequest,
    ) -> CapabilityExecutionResult:
        """Execute the capability against physical runtime adapters and return structured result."""
        ...
