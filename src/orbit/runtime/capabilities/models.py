"""Domain models and contracts for ORBIT Capability-Aware Architecture."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CapabilityCategory(str, Enum):
    """Categorical classification of agent runtime capabilities."""

    DESKTOP_CONTROL = "DESKTOP_CONTROL"
    INPUT = "INPUT"
    CREATIVE_VISUAL = "CREATIVE_VISUAL"
    DOCUMENT = "DOCUMENT"
    BROWSER = "BROWSER"
    SYSTEM = "SYSTEM"
    DATA = "DATA"


class CapabilitySource(str, Enum):
    """Origin source of a capability."""

    INTERNAL = "INTERNAL"
    ENVIRONMENT_APP = "ENVIRONMENT_APP"
    ENVIRONMENT_MODEL = "ENVIRONMENT_MODEL"
    COMPOSITE = "COMPOSITE"


class FeasibilityStatus(str, Enum):
    """Feasibility outcome for an objective against registered capabilities."""

    FEASIBLE = "FEASIBLE"
    CONDITIONALLY_FEASIBLE = "CONDITIONALLY_FEASIBLE"
    INSUFFICIENT_CAPABILITY = "INSUFFICIENT_CAPABILITY"
    UNSUPPORTED = "UNSUPPORTED"


class CapabilityLimitation(BaseModel):
    """Explicit limitation boundary for a capability."""

    description: str = Field(..., description="Human-readable explanation of what is NOT supported")
    unsupported_patterns: List[str] = Field(
        default_factory=list,
        description="Substrings, regexes, or keywords that this capability cannot reliably satisfy",
    )
    severity: str = Field(default="HARD_LIMIT", description="HARD_LIMIT or ADVISORY")


class Capability(BaseModel):
    """Registered capability definition with explicit operational boundaries."""

    capability_id: str = Field(..., description="Unique machine-readable identifier")
    name: str = Field(..., description="Human-readable display name")
    description: str = Field(..., description="Description of what this capability reliably achieves")
    category: CapabilityCategory = Field(..., description="Capability category")
    source: CapabilitySource = Field(
        default=CapabilitySource.INTERNAL,
        description="Origin source of capability (INTERNAL, ENVIRONMENT_APP, ENVIRONMENT_MODEL, COMPOSITE)",
    )
    supported_goal_types: List[str] = Field(
        default_factory=list,
        description="Goal types or actions this capability natively supports",
    )
    supported_subtypes: List[str] = Field(
        default_factory=list,
        description="Specific granular entities or shapes reliably supported (e.g. ['cube', 'circle', 'rectangle'])",
    )
    limitations: List[CapabilityLimitation] = Field(
        default_factory=list,
        description="Explicit limitations preventing false assumptions of universality",
    )
    reliability_score: float = Field(
        default=0.90,
        ge=0.0,
        le=1.0,
        description="Historical or expected baseline reliability (0.0 to 1.0)",
    )
    execution_cost: float = Field(
        default=1.0,
        description="Relative execution cost or latency (higher = heavier)",
    )
    verification_methods: List[str] = Field(
        default_factory=list,
        description="Applicable verification strategies (e.g. ['PIXEL_DIFF', 'OCR', 'UIA_STATE', 'SEMANTIC_VISION'])",
    )
    is_available: bool = Field(
        default=True,
        description="Whether this capability is currently operational and configured",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional capability metadata",
    )

    def can_handle_subtype(self, subtype: str) -> bool:
        """Check if a specific subtype or shape is supported."""
        sub_l = subtype.strip().lower()
        return any(s.lower() == sub_l or s.lower() in sub_l for s in self.supported_subtypes)

    def violates_limitation(self, query: str) -> Optional[CapabilityLimitation]:
        """Check if query triggers any registered limitation."""
        q_l = query.strip().lower()
        for lim in self.limitations:
            for pat in lim.unsupported_patterns:
                if pat.lower() in q_l:
                    return lim
        return None


# ---------------------------------------------------------------------------
# Goal Requirements Domain Contracts
# ---------------------------------------------------------------------------

class GoalRequirement(BaseModel):
    """Declarative specification of WHAT is required to achieve a goal."""

    requirement_id: str = Field(..., description="Unique requirement identifier")
    requirement_type: str = Field(
        ...,
        description="Type: APPLICATION_LIFECYCLE, CONTENT_CREATION, CONTENT_IMPORT, DATA_INPUT, STATE_VERIFICATION, FILE_MANAGEMENT",
    )
    semantic_description: str = Field(..., description="Human-readable description of what is needed")
    required_capability_category: CapabilityCategory = Field(..., description="Target category of capability")
    mandatory: bool = Field(default=True, description="Whether this requirement is strictly mandatory")
    success_criteria: List[str] = Field(default_factory=list, description="Verifiable success conditions")
    alternatives: List[str] = Field(default_factory=list, description="Acceptable alternative approaches")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Domain-specific parameters (fidelity, subject, app)")


class GoalRequirementSet(BaseModel):
    """Complete decomposed requirement specification for an objective."""

    objective_id: str = Field(..., description="Associated StructuredObjective identifier")
    raw_goal: str = Field(..., description="Original user prompt or raw goal")
    requirements: List[GoalRequirement] = Field(default_factory=list, description="Ordered set of requirements")
    target_domain: str = Field(default="general", description="Domain classification (creative_drawing, document_editing, system_automation)")
    required_fidelity: str = Field(
        default="STANDARD",
        description="Fidelity expectation: PRIMITIVE, STANDARD, or HIGH_FIDELITY_SEMANTIC",
    )

    def get_mandatory_requirements(self) -> List[GoalRequirement]:
        return [r for r in self.requirements if r.mandatory]


# ---------------------------------------------------------------------------
# Strategy & Composition Domain Contracts
# ---------------------------------------------------------------------------

class StrategyStage(BaseModel):
    """Discrete abstract stage within an execution strategy."""

    stage_index: int = Field(..., description="0-indexed sequence position")
    name: str = Field(..., description="Stage name (e.g. LAUNCH_HOST_APPLICATION, IMPORT_VISUAL_CONTENT)")
    capability_id: str = Field(..., description="Primary capability executing this stage")
    description: str = Field(..., description="What this stage accomplishes")
    expected_outcome: str = Field(..., description="Expected perceptual or system state delta")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Stage parameters")


class StrategyOption(BaseModel):
    """Candidate execution strategy composed of one or more capabilities."""

    strategy_id: str = Field(..., description="Unique strategy identifier")
    name: str = Field(..., description="Human-readable strategy name")
    description: str = Field(..., description="Description of execution approach")
    required_capabilities: List[str] = Field(
        default_factory=list,
        description="List of capability IDs necessary for this strategy",
    )
    stages: List[StrategyStage] = Field(
        default_factory=list,
        description="Ordered sequence of abstract execution stages",
    )
    estimated_success_probability: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall estimated probability of meeting the user's semantic goal",
    )
    semantic_goal_coverage: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Semantic adequacy score (how well the approach satisfies the true goal)",
    )
    risk_level: str = Field(default="LOW", description="LOW, MEDIUM, or HIGH risk")
    dependencies: List[str] = Field(default_factory=list, description="External environment prerequisites")
    missing_capabilities: List[str] = Field(default_factory=list, description="Required capabilities currently unavailable")
    rejection_reason: Optional[str] = Field(default=None, description="Explicit reason why strategy was disqualified if any")
    rationale: str = Field(default="", description="Why this strategy was formulated or ranked")
    is_available: bool = Field(default=True, description="Whether all required capabilities are available")


class StrategySelectionResult(BaseModel):
    """Result of evaluating and ranking candidate execution strategies."""

    selected_strategy: Optional[StrategyOption] = Field(
        default=None,
        description="Optimal strategy chosen for execution",
    )
    candidate_strategies: List[StrategyOption] = Field(
        default_factory=list,
        description="Ranked list of all evaluated candidate strategies",
    )
    is_executable: bool = Field(
        default=False,
        description="Whether an acceptable strategy exists above the reliability threshold",
    )
    selection_reasoning: str = Field(
        default="",
        description="Explanation of why this strategy was chosen or why none succeeded",
    )


# ---------------------------------------------------------------------------
# Capability Gap & Feasibility Contracts
# ---------------------------------------------------------------------------

class CapabilityGapReport(BaseModel):
    """Structured report detailing what capabilities are absent to achieve a goal."""

    requested_goal: str = Field(..., description="Original user prompt or raw goal")
    attempted_strategies: List[StrategyOption] = Field(default_factory=list, description="All evaluated strategies and rejection reasons")
    missing_capabilities: List[str] = Field(default_factory=list, description="Specific capability IDs that were required but missing")
    unmet_requirements: List[str] = Field(default_factory=list, description="Specific goal requirements that could not be satisfied")
    reason: str = Field(..., description="Clear explanation of the architectural capability gap")
    recommended_prerequisites: List[str] = Field(default_factory=list, description="Concrete actions or tools needed to enable this workflow")
    gap_severity: str = Field(default="BLOCKING", description="BLOCKING or DEGRADED")


class FeasibilityAssessment(BaseModel):
    """Authoritative feasibility evaluation of an objective against capabilities."""

    is_feasible: bool = Field(..., description="Whether ORBIT can reliably achieve this goal")
    status: FeasibilityStatus = Field(..., description="Categorical feasibility status")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in assessment")
    matched_strategy: Optional[StrategyOption] = Field(
        default=None,
        description="Selected viable strategy if feasible",
    )
    available_capabilities: List[str] = Field(
        default_factory=list,
        description="Registered capabilities available for this objective",
    )
    missing_capabilities: List[str] = Field(
        default_factory=list,
        description="Required capabilities that are absent or unavailable",
    )
    triggered_limitations: List[str] = Field(
        default_factory=list,
        description="Limitation boundaries triggered by the request",
    )
    explanation: str = Field(..., description="Clear diagnostic explanation for planner and user")
    suggested_alternatives: List[str] = Field(
        default_factory=list,
        description="Suggestions if the goal cannot be executed as requested",
    )
    capability_gap: Optional[CapabilityGapReport] = Field(
        default=None,
        description="Detailed capability gap report if goal is unfeasible",
    )
