"""
Provenance & Architectural Attribution:
======================================
Windows-Use Source:   windows_use/telemetry/ & agent/watchdog/
ORBIT Destination:    src/orbit/runtime/telemetry/events.py
Integration Paradigm: Transduced Universal Observability (Brain-Body Separation)

Adaptations Applied:
- Implemented strictly immutable, observer-only structured telemetry events.
- Enforced Tripartite Reality distinction (dispatch_success != expected_effect_observed != goal_satisfied).
- Strict Invariant: Telemetry has zero completion or physical execution authority.
======================================
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field

from orbit.runtime.agent.contracts import AbstractActionType, VerificationStrategy


class TelemetryEventType(str, Enum):
    """Categorical enumeration of deterministic lifecycle execution events."""

    # 1. Task Lifecycle Events (Authoritative lifecycle only)
    TASK_STARTED = "TASK_STARTED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_ABORTED = "TASK_ABORTED"

    # 2. Cycle & Observation
    CYCLE_STARTED = "CYCLE_STARTED"
    OBSERVATION_CAPTURED = "OBSERVATION_CAPTURED"

    # 3. Planning & Grounding
    PLAN_DIRECTIVE_EMITTED = "PLAN_DIRECTIVE_EMITTED"
    TARGET_GROUNDED = "TARGET_GROUNDED"

    # 4. Primitives Composition & Validation
    PRIMITIVES_COMPOSED = "PRIMITIVES_COMPOSED"
    PRIMITIVES_VALIDATED = "PRIMITIVES_VALIDATED"

    # 5. Physical Dispatch (Body Actuation)
    PHYSICAL_DISPATCH_COMMENCED = "PHYSICAL_DISPATCH_COMMENCED"
    PHYSICAL_DISPATCH_COMPLETED = "PHYSICAL_DISPATCH_COMPLETED"

    # 6. Verification & Reality Evaluation
    VERIFICATION_EVALUATED = "VERIFICATION_EVALUATED"

    # 7. Failure, LoopGuard & Replanning
    LOOP_GUARD_DIAGNOSIS = "LOOP_GUARD_DIAGNOSIS"
    REPLAN_TRIGGERED = "REPLAN_TRIGGERED"

    # 8. Progress Graph Milestones
    SUBGOAL_PROGRESS_ADVANCED = "SUBGOAL_PROGRESS_ADVANCED"
    PROGRESS_SNAPSHOT_UPDATED = "PROGRESS_SNAPSHOT_UPDATED"


class StructuredTelemetryEvent(BaseModel):
    """Immutable, auditable telemetry event representing a single lifecycle occurrence.

    INVARIANTS:
    1. Immutable (frozen=True): Consumers cannot mutate event payloads.
    2. Zero Authority: Does not declare task state changes or execute actions.
    3. Tripartite Reality Preservation: Action outcomes strictly separate dispatch, effect, and goal.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:10]}")
    event_type: TelemetryEventType
    task_id: str = Field(..., description="Unique task or objective identifier")
    cycle_number: int = Field(default=0, ge=0, description="Execution cycle number")
    subgoal_id: Optional[str] = Field(default=None, description="Active subgoal ID if applicable")
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_component: str = Field(default="ORBIT_CORE", description="Component emitting the event")

    # Structured Payloads (Non-executable, read-only data)
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event-specific metadata")

    # Tripartite Reality Fields (Preserved on action and verification events)
    dispatch_success: Optional[bool] = Field(
        default=None,
        description="Whether OS adapter accepted physical command",
    )
    expected_effect_observed: Optional[bool] = Field(
        default=None,
        description="Whether verifiable state delta was independently observed in desktop perception",
    )
    goal_satisfied: Optional[bool] = Field(
        default=None,
        description="Whether complete user objective is verified by GoalVerifier",
    )

    duration_ms: float = Field(default=0.0, ge=0.0, description="Duration in milliseconds if timed")


__all__ = [
    "TelemetryEventType",
    "StructuredTelemetryEvent",
]
