"""PlanDirective domain model.

The authoritative execution directive emitted by AgentPlanner following Semantic Feasibility
selection, bridging high-level cognitive planning to canonical primitive action composition.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import (
    AbstractActionType,
    ActionOutcomeContract,
    SemanticTarget,
)


class PlanDirective(BaseModel):
    """Authoritative execution directive for an active subgoal.

    INVARIANT (ASTRA Dimension 3 & 5): Emitted ONLY after candidate plans have been evaluated
    and approved by Semantic Feasibility. Encapsulates intent strategy, semantic targets,
    canonical primitive preferences, and outcome contracts without physical screen coordinates.
    """

    directive_id: str = Field(default_factory=lambda: f"dir_{uuid4().hex[:8]}")
    objective_id: str = Field(..., description="Parent structured objective ID")
    subgoal_id: str = Field(..., description="Active subgoal milestone ID from ProgressGraph")
    subgoal_title: str = Field(..., description="Summary title of the subgoal milestone")
    intent_strategy: str = Field(default="GUI_INTERACTIVE", description="Execution strategy (e.g. GUI_INTERACTIVE, CANVAS_RENDERING, ENVIRONMENT_INTERFACE)")
    candidate_plan_id: str = Field(default_factory=lambda: f"cand_{uuid4().hex[:8]}")

    # Targeting and constraints
    semantic_targets: List[SemanticTarget] = Field(default_factory=list, description="Logical targets without screen coordinates")
    constraints: List[str] = Field(default_factory=list, description="Negative or boundary constraints")
    preferred_primitives: List[AbstractActionType] = Field(default_factory=list, description="Allowed canonical primitives")

    # Verification and limits
    expected_outcome: ActionOutcomeContract = Field(
        default_factory=lambda: ActionOutcomeContract(expected_state_transition="Subgoal post-condition observed"),
        description="Contract declaring verifiable outcome required for completion",
    )
    max_cycles: int = Field(default=10, description="Maximum execution cycles allowed for this directive")
    feasibility_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Semantic feasibility score assigned prior to emission")

    # Creative / Domain payload (strokes, formulas, text snippets)
    creative_payload: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured creative generation payload (normalized strokes, text content) without screen coordinates",
    )

    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = [
    "PlanDirective",
]
