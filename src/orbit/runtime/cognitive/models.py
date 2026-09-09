"""Domain contracts and data models for the Cognitive Intent & Decision Engine subsystem.

Re-exports strict agent action protocol, outcome contracts, and coordinate boundaries
from orbit.runtime.agent.contracts for unified AI-native execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator

from orbit.runtime.agent.contracts import (
    AbortTaskParams,
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionExecutionResult,
    ActionOutcomeContract,
    ActionType,
    ActionValidationFailureCode,
    ActionValidationResult,
    AgentAction,
    AgentActionValidator,
    ClickParams,
    CompleteGoalParams,
    DoubleClickParams,
    DragParams,
    DrawStrokesParams,
    ExpectedState,
    FocusWindowParams,
    LaunchApplicationParams,
    OutcomeStatus,
    ResolvedAction,
    RightClickParams,
    ScrollParams,
    SelectOptionParams,
    SemanticTarget,
    SendHotkeyParams,
    TypeTextParams,
    VerificationStrategy,
    WaitParams,
)
from orbit.runtime.perception.models import DesktopObservation
from orbit.runtime.task_completion.models import TaskCompletionStatus


from orbit.runtime.cognitive.recovery import (
    AgentRecoveryManager,
    RecoveryRecord,
    RecoveryStrategy,
)
from orbit.runtime.cognitive.state_machine import (
    AgentLoopState,
    AgentLoopStateMachine,
    AgentStateTransitionRecord,
    InvalidStateTransitionError,
    LEGAL_STATE_TRANSITIONS,
    TERMINAL_STATES,
)
from orbit.runtime.cognitive.trace import (
    CycleExecutionTrace,
    format_cycle_trace_block,
)


class StructuredObjective(BaseModel):
    """Structured, epistemically grounded representation of user intent."""

    objective_id: str = Field(default_factory=lambda: f"obj_{uuid4().hex[:8]}", description="Unique objective identifier")
    raw_prompt: str = Field(..., description="Original user prompt verbatim")
    user_goal: str = Field(..., description="High-level summarized goal statement")
    end_condition: str = Field(..., description="Verifiable end state criteria (e.g. canvas_has_cube_drawing, notepad_contains_text)")
    target_entities: List[str] = Field(default_factory=list, description="Target applications, controls, files, or geometric shapes")
    constraints: List[str] = Field(default_factory=list, description="Negative or positive constraints and boundaries")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Extracted parameters (e.g. shape, text, app name)")
    deliverable: Optional[str] = Field(default=None, description="Expected concrete deliverable (e.g. spreadsheet, drawing, text file)")
    success_criteria: List[str] = Field(default_factory=list, description="Explicit criteria that define completion")
    assumptions: List[str] = Field(default_factory=list, description="Operating assumptions")
    subtasks: List[str] = Field(default_factory=list, description="High-level decomposed subtasks")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of interpretation")


class SubgoalStatus(str, Enum):
    """Authoritative lifecycle status of an atomic milestone subgoal."""

    PENDING = "PENDING"          # Dependencies not yet satisfied
    READY = "READY"              # Dependencies satisfied, eligible for scheduling/execution
    IN_PROGRESS = "IN_PROGRESS"  # Actively executing under PrimitiveExecutionController
    COMPLETED = "COMPLETED"      # Post-condition verified, terminal success for this node
    BLOCKED = "BLOCKED"          # One or more ancestor dependencies failed or was aborted
    FAILED = "FAILED"            # Node execution failed and exhausted retries


class SubObjective(BaseModel):
    """Atomic milestone sub-goal specification within a decomposed plan."""

    sub_id: str = Field(default_factory=lambda: f"sub_{uuid4().hex[:8]}")
    title: str = Field(..., description="High-level title of sub-goal milestone")
    description: str = Field(default="", description="Detailed milestone goal")
    dependencies: List[str] = Field(default_factory=list, description="List of ancestor sub_ids required before this milestone")
    target_entity: Optional[str] = Field(default=None, description="App, website, document, or control targeted")
    success_criteria: List[str] = Field(default_factory=list, description="Verifiable success criteria for this sub-goal")
    constraints: List[str] = Field(default_factory=list, description="Milestone-specific constraints")
    preferred_primitives: List[AbstractActionType] = Field(default_factory=list, description="Suggested canonical primitives")
    is_completed: bool = Field(default=False)


class ProgressNode(BaseModel):
    """Authoritative runtime lifecycle tracking node for a single subgoal in ProgressGraph."""

    sub_id: str
    title: str
    status: SubgoalStatus = Field(default=SubgoalStatus.PENDING)
    dependencies: List[str] = Field(default_factory=list)
    dependents: List[str] = Field(default_factory=list)
    started_at_utc: Optional[datetime] = None
    completed_at_utc: Optional[datetime] = None
    failure_reason: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2


class ProgressSnapshot(BaseModel):
    """Immutable projection snapshot of the subgoal lifecycle state.

    INVARIANT: ProgressGraph is the sole source of truth for subgoal lifecycle.
    WorldModel, Planner, and external observers consume this immutable projection.
    WorldModel and Planner cannot independently mutate or contradict this state.
    """

    snapshot_id: str = Field(default_factory=lambda: f"snap_{uuid4().hex[:8]}")
    active_subgoal_id: Optional[str] = None
    completed_subgoals: List[str] = Field(default_factory=list)
    pending_subgoals: List[str] = Field(default_factory=list)
    ready_subgoals: List[str] = Field(default_factory=list)
    blocked_subgoals: List[str] = Field(default_factory=list)
    failed_subgoals: List[str] = Field(default_factory=list)
    nodes: Dict[str, ProgressNode] = Field(default_factory=dict)
    is_fully_completed: bool = False
    is_failed: bool = False
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProgressGraph:
    """Sole authoritative state machine and dependency DAG manager for subgoal lifecycle.

    INVARIANT: ProgressGraph is the single source of truth for subgoal status transitions.
    All transitions must be topologically valid, cycle-free, and atomically verified.
    WorldModel may reference/projection-cache progress state but cannot independently mutate or contradict it.
    """

    def __init__(self, sub_objectives: Optional[List[SubObjective]] = None) -> None:
        self._nodes: Dict[str, ProgressNode] = {}
        self._active_subgoal_id: Optional[str] = None
        if sub_objectives:
            self.load_sub_objectives(sub_objectives)

    def load_sub_objectives(self, sub_objectives: List[SubObjective]) -> None:
        """Initialize the graph from milestone specifications, validating acyclicity."""
        self._nodes.clear()
        self._active_subgoal_id = None

        # 1. Register all nodes
        for sub in sub_objectives:
            node = ProgressNode(
                sub_id=sub.sub_id,
                title=sub.title,
                status=SubgoalStatus.PENDING,
                dependencies=list(sub.dependencies),
                dependents=[],
            )
            self._nodes[sub.sub_id] = node

        # 2. Validate all dependency IDs exist and register dependents
        for node in self._nodes.values():
            for dep_id in node.dependencies:
                if dep_id not in self._nodes:
                    raise ValueError(f"Subgoal '{node.sub_id}' specifies non-existent dependency '{dep_id}'")
                self._nodes[dep_id].dependents.append(node.sub_id)

        # 3. Validate acyclicity via topological sort
        self.topological_sort()

        # 4. Initialize initial READY nodes (zero dependencies)
        for node in self._nodes.values():
            if not node.dependencies:
                node.status = SubgoalStatus.READY

    def topological_sort(self) -> List[str]:
        """Compute topological sort; raises ValueError if a cycle is detected."""
        in_degree: Dict[str, int] = {nid: len(n.dependencies) for nid, n in self._nodes.items()}
        queue: List[str] = [nid for nid, deg in in_degree.items() if deg == 0]
        sorted_nodes: List[str] = []

        while queue:
            curr = queue.pop(0)
            sorted_nodes.append(curr)
            for dependent_id in self._nodes[curr].dependents:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        if len(sorted_nodes) != len(self._nodes):
            raise ValueError("Dependency cycle detected in subgoal graph")

        return sorted_nodes

    @property
    def active_subgoal_id(self) -> Optional[str]:
        return self._active_subgoal_id

    def get_node(self, sub_id: str) -> Optional[ProgressNode]:
        return self._nodes.get(sub_id)

    def get_ready_subgoals(self) -> List[ProgressNode]:
        """Return list of subgoals ready to be scheduled and executed."""
        return [n for n in self._nodes.values() if n.status == SubgoalStatus.READY]

    def get_active_subgoal(self) -> Optional[ProgressNode]:
        """Return the currently executing subgoal, if any."""
        if self._active_subgoal_id and self._active_subgoal_id in self._nodes:
            return self._nodes[self._active_subgoal_id]
        return None

    def start_subgoal(self, sub_id: str) -> ProgressNode:
        """Transition a READY subgoal to IN_PROGRESS. Raises ValueError if not READY."""
        if sub_id not in self._nodes:
            raise KeyError(f"Subgoal '{sub_id}' not found in ProgressGraph")
        node = self._nodes[sub_id]
        if node.status != SubgoalStatus.READY:
            raise ValueError(f"Cannot start subgoal '{sub_id}': status is {node.status.value}, expected READY")

        node.status = SubgoalStatus.IN_PROGRESS
        node.started_at_utc = datetime.now(timezone.utc)
        self._active_subgoal_id = sub_id
        return node

    def complete_subgoal(self, sub_id: str) -> ProgressNode:
        """Transition an IN_PROGRESS subgoal to COMPLETED and unlock ready dependents."""
        if sub_id not in self._nodes:
            raise KeyError(f"Subgoal '{sub_id}' not found in ProgressGraph")
        node = self._nodes[sub_id]
        if node.status != SubgoalStatus.IN_PROGRESS:
            raise ValueError(f"Cannot complete subgoal '{sub_id}': status is {node.status.value}, expected IN_PROGRESS")

        node.status = SubgoalStatus.COMPLETED
        node.completed_at_utc = datetime.now(timezone.utc)
        if self._active_subgoal_id == sub_id:
            self._active_subgoal_id = None

        # Check all dependents: if all their dependencies are now COMPLETED, transition PENDING -> READY
        for dep_id in node.dependents:
            dep_node = self._nodes[dep_id]
            if dep_node.status == SubgoalStatus.PENDING:
                all_deps_done = all(
                    self._nodes[d].status == SubgoalStatus.COMPLETED
                    for d in dep_node.dependencies
                )
                if all_deps_done:
                    dep_node.status = SubgoalStatus.READY

        return node

    def fail_subgoal(self, sub_id: str, reason: str, allow_retry: bool = False) -> bool:
        """Transition an active/ready subgoal to FAILED.
        
        If allow_retry and retry limit not reached, resets to READY and returns True.
        Otherwise marks FAILED, cascades BLOCKED to all downstream dependents, and returns False.
        """
        if sub_id not in self._nodes:
            raise KeyError(f"Subgoal '{sub_id}' not found in ProgressGraph")
        node = self._nodes[sub_id]
        if node.status not in (SubgoalStatus.IN_PROGRESS, SubgoalStatus.READY):
            raise ValueError(f"Cannot fail subgoal '{sub_id}': status is {node.status.value}")

        if allow_retry and node.retry_count < node.max_retries:
            node.retry_count += 1
            node.status = SubgoalStatus.READY
            if self._active_subgoal_id == sub_id:
                self._active_subgoal_id = None
            return True

        node.status = SubgoalStatus.FAILED
        node.failure_reason = reason
        if self._active_subgoal_id == sub_id:
            self._active_subgoal_id = None

        # Cascade BLOCKED to all downstream dependents recursively
        queue: List[str] = list(node.dependents)
        while queue:
            curr_id = queue.pop(0)
            curr_node = self._nodes[curr_id]
            if curr_node.status in (SubgoalStatus.PENDING, SubgoalStatus.READY):
                curr_node.status = SubgoalStatus.BLOCKED
                curr_node.failure_reason = f"Ancestor dependency '{sub_id}' failed: {reason}"
                queue.extend(curr_node.dependents)

        return False

    def get_snapshot(self) -> ProgressSnapshot:
        """Generate an immutable projection snapshot for WorldModel and Planner."""
        completed: List[str] = []
        pending: List[str] = []
        ready: List[str] = []
        blocked: List[str] = []
        failed: List[str] = []
        nodes_copy: Dict[str, ProgressNode] = {}

        for nid, node in self._nodes.items():
            nodes_copy[nid] = node.model_copy()
            if node.status == SubgoalStatus.COMPLETED:
                completed.append(nid)
            elif node.status == SubgoalStatus.PENDING:
                pending.append(nid)
            elif node.status == SubgoalStatus.READY:
                ready.append(nid)
            elif node.status == SubgoalStatus.BLOCKED:
                blocked.append(nid)
            elif node.status == SubgoalStatus.FAILED:
                failed.append(nid)

        total_nodes = len(self._nodes)
        is_fully_completed = (total_nodes > 0) and (len(completed) == total_nodes)
        is_failed = len(failed) > 0 or (len(blocked) > 0 and not ready and not self._active_subgoal_id)

        return ProgressSnapshot(
            active_subgoal_id=self._active_subgoal_id,
            completed_subgoals=completed,
            pending_subgoals=pending,
            ready_subgoals=ready,
            blocked_subgoals=blocked,
            failed_subgoals=failed,
            nodes=nodes_copy,
            is_fully_completed=is_fully_completed,
            is_failed=is_failed,
        )


class DecomposedPlan(BaseModel):
    """Ordered sequence of sub-objectives produced by HierarchicalGoalDecomposer."""

    plan_id: str = Field(default_factory=lambda: f"plan_{uuid4().hex[:8]}")
    objective_id: str = Field(..., description="Parent objective ID")
    raw_prompt: str = Field(default="")
    sub_objectives: List[SubObjective] = Field(default_factory=list)
    reasoning: str = Field(default="")
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))



class CurrentStateObservation(BaseModel):
    """Immutable snapshot of the live desktop state observed by the perception layer."""

    observation_id: str = Field(default_factory=lambda: f"obs_{uuid4().hex[:8]}", description="Unique observation identifier")
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of observation")
    active_window_hwnd: Optional[int] = Field(default=None, description="HWND of foreground active window")
    active_window_title: Optional[str] = Field(default=None, description="Title of foreground active window")
    active_window_class: Optional[str] = Field(default=None, description="Win32 class name of active window")
    active_process_name: Optional[str] = Field(default=None, description="Process executable name of active window")
    visible_windows: List[Dict[str, Any]] = Field(default_factory=list, description="List of visible top-level windows")
    target_app_exists: bool = Field(default=False, description="Whether target application is currently running/open")
    target_app_is_active: bool = Field(default=False, description="Whether target application is the active foreground window")
    screen_summary: str = Field(default="", description="High-level text or perceptual summary of the screen")
    canvas_status: Optional[str] = Field(default=None, description="Status of target canvas if applicable: BLANK, NON_BLANK, UNKNOWN")
    ocr_tokens: List[str] = Field(default_factory=list, description="OCR text tokens recognized on screen")
    raw_evidence: Dict[str, Any] = Field(default_factory=dict, description="Raw sensory and accessibility telemetry")

    # Authoritative Canonical DesktopObservation snapshot & modality telemetry
    desktop_observation: Optional[DesktopObservation] = Field(default=None, description="Underlying canonical multimodal DesktopObservation")
    uia_status: Optional[str] = Field(default=None, description="UIA status: SUCCESS, EMPTY, UNAVAILABLE, FAILED")
    ocr_status: Optional[str] = Field(default=None, description="OCR status: SUCCESS, EMPTY, UNAVAILABLE, FAILED")
    screenshot_status: Optional[str] = Field(default=None, description="Screenshot status: SUCCESS, FALLBACK, FAILED")
    perceived_elements_count: int = Field(default=0, description="Count of fused semantic elements in perception snapshot")


class CognitiveDecision(BaseModel):
    """Output of a single reasoning cycle in the Cognitive Decision Engine.

    Stores structured, auditable decision fields without free-form unrestricted chain-of-thought.
    """

    decision_id: str = Field(default_factory=lambda: f"dec_{uuid4().hex[:8]}", description="Unique decision identifier")
    step_index: int = Field(default=0, description="0-indexed step iteration in the cognitive loop")
    decision_summary: str = Field(..., description="Auditable assessment of current state vs objective")
    decision_confidence: float = Field(default=1.0, description="Confidence in decision (0.0 to 1.0)")
    evidence_used: List[str] = Field(default_factory=list, description="Concrete observations used to make decision")
    expected_state_transition: str = Field(default="", description="Expected state transition resulting from this decision")
    reason_summary: str = Field(default="", description="Concise justification for the action")
    is_goal_satisfied: bool = Field(default=False, description="Whether current state satisfies objective end condition")
    escalated_to_llm: bool = Field(default=False, description="Whether this decision required LLM escalation")
    next_action: Optional[AbstractAction] = Field(default=None, description="The abstract action to execute next, or None if satisfied")


class ExecutionBudget(BaseModel):
    """Progress-based execution budget preventing infinite loops and tracking meaningful state change."""

    max_total_actions: int = Field(default=50, description="Hard upper bound on total actions dispatched")
    max_repeated_actions_without_progress: int = Field(default=3, description="Max consecutive identical actions without state progress")
    max_recoveries_per_transition: int = Field(default=2, description="Max recovery attempts for a single state transition")
    max_target_resolution_failures: int = Field(default=3, description="Max target grounding failures before aborting")
    max_llm_escalations: int = Field(default=5, description="Max times LLM can be invoked for decision escalation")
    no_progress_timeout_sec: float = Field(default=30.0, description="Timeout if no forward state progress is made")


class CognitiveStepResult(BaseModel):
    """Audit record of an executed cognitive loop iteration."""

    step_index: int = Field(..., description="Iteration number")
    decision: CognitiveDecision = Field(..., description="Cognitive decision made in this step")
    action_dispatched: Optional[AbstractAction] = Field(default=None, description="Action sent to executor")
    execution_result: Optional[ActionExecutionResult] = Field(default=None, description="Immediate action execution and outcome verification")
    post_observation: Optional[CurrentStateObservation] = Field(default=None, description="State observed after action execution")
    state_progress_detected: bool = Field(default=False, description="Whether this step moved the system state closer to the goal")
    duration_ms: float = Field(default=0.0, description="Execution duration of this step in milliseconds")
    trace: Optional[CycleExecutionTrace] = Field(default=None, description="Diagnostic cycle execution trace")

    @property
    def action_success(self) -> bool:
        return bool(self.execution_result and self.execution_result.dispatch_success)

    @property
    def outcome_verified(self) -> bool:
        return bool(self.execution_result and self.execution_result.expected_effect_observed)


class CognitiveExecutionResult(BaseModel):
    """End-to-end outcome of a cognitive execution loop run."""

    task_id: str = Field(..., description="Task identifier")
    objective: StructuredObjective = Field(..., description="Structured objective that guided execution")
    is_success: bool = Field(default=False, description="Whether the task objective was successfully satisfied and verified")
    total_steps: int = Field(default=0, description="Total cognitive iterations executed")
    step_history: List[CognitiveStepResult] = Field(default_factory=list, description="Chronological record of every step")
    final_status: TaskCompletionStatus = Field(default=TaskCompletionStatus.FAILED, description="Terminal task status")
    failure_reason: Optional[str] = Field(default=None, description="Explanation of failure if not successful")
    failure_code: Optional[str] = Field(default=None, description="Error code if failed")
    elapsed_duration_ms: float = Field(default=0.0, description="Total wall-clock duration in milliseconds")
    state_transitions: List[AgentStateTransitionRecord] = Field(default_factory=list, description="Auditable state machine transitions")
    cycle_traces: List[CycleExecutionTrace] = Field(default_factory=list, description="Structured cycle execution traces")
    recovery_records: List[RecoveryRecord] = Field(default_factory=list, description="Recovery records executed during task")


__all__ = [
    # Core contracts re-exported
    "AbortTaskParams",
    "AbstractAction",
    "AbstractActionType",
    "ActionExecutionOutcome",
    "ActionExecutionResult",
    "ActionOutcomeContract",
    "ActionType",
    "ActionValidationFailureCode",
    "ActionValidationResult",
    "AgentAction",
    "AgentActionValidator",
    "AgentLoopState",
    "AgentLoopStateMachine",
    "AgentRecoveryManager",
    "AgentStateTransitionRecord",
    "ClickParams",
    "CognitiveDecision",
    "CognitiveExecutionResult",
    "CognitiveStepResult",
    "CompleteGoalParams",
    "CurrentStateObservation",
    "CycleExecutionTrace",
    "DecomposedPlan",
    "DoubleClickParams",
    "DragParams",
    "DrawStrokesParams",
    "ExecutionBudget",
    "ExpectedState",
    "FocusWindowParams",
    "InvalidStateTransitionError",
    "LEGAL_STATE_TRANSITIONS",
    "LaunchApplicationParams",
    "OutcomeStatus",
    "RecoveryRecord",
    "RecoveryStrategy",
    "ResolvedAction",
    "RightClickParams",
    "ScrollParams",
    "SelectOptionParams",
    "SemanticTarget",
    "SendHotkeyParams",
    "ProgressGraph",
    "ProgressNode",
    "ProgressSnapshot",
    "SubgoalStatus",
    "StructuredObjective",
    "SubObjective",
    "TERMINAL_STATES",
    "TypeTextParams",
    "VerificationStrategy",
    "WaitParams",
    "format_cycle_trace_block",
]
