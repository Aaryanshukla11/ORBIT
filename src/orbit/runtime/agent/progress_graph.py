"""Agent Memory + Dynamic Progress Graph (ASTRA-6 Canonical Authority).

INVARIANT (ASTRA-6 Rule 8 & 9):
ProgressGraph is the SINGLE authoritative source of truth for subgoal lifecycle.
WorldModel and external observers only consume immutable ProgressSnapshot projections
and cannot independently mutate or contradict subgoal lifecycle state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import AbstractActionType

logger = logging.getLogger(__name__)


class SubgoalStatus(str, Enum):
    """Authoritative lifecycle status of an atomic milestone subgoal."""

    PENDING = "PENDING"          # Not yet started / dependencies not yet met
    READY = "READY"              # Dependencies satisfied, eligible for scheduling
    IN_PROGRESS = "IN_PROGRESS"  # Actively executing under PrimitiveExecutionController
    COMPLETED = "COMPLETED"      # Post-condition verified, terminal success for this node
    FAILED = "FAILED"            # Node execution failed and exhausted retries
    BLOCKED = "BLOCKED"          # Cannot proceed due to unmet/failed prerequisite subgoals
    SKIPPED = "SKIPPED"          # Bypassed because condition already satisfied


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

    sub_id: str = Field(default_factory=lambda: f"sg_{uuid4().hex[:8]}", description="Unique subgoal node ID")
    title: str = Field(..., description="Short title describing the subgoal milestone")
    description: str = Field(default="", description="Detailed criteria for satisfying this subgoal")
    status: SubgoalStatus = Field(default=SubgoalStatus.PENDING, description="Current progress status")
    dependencies: List[str] = Field(default_factory=list, description="IDs of prerequisite subgoals")
    dependents: List[str] = Field(default_factory=list, description="IDs of downstream dependent subgoals")
    action_ids: List[str] = Field(default_factory=list, description="IDs of actions dispatched to fulfill this subgoal")
    retry_count: int = Field(default=0, ge=0, description="Number of attempts made on this subgoal")
    max_retries: int = Field(default=3, ge=1, description="Max allowed retries before marking FAILED")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Verified sensory evidence proving completion")
    started_at_utc: Optional[datetime] = Field(default=None)
    completed_at_utc: Optional[datetime] = Field(default=None)
    failure_reason: Optional[str] = Field(default=None)
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def node_id(self) -> str:
        """Alias for sub_id to support legacy callers."""
        return self.sub_id


# Alias for backwards compatibility
SubgoalNode = ProgressNode


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

    def __init__(
        self,
        sub_objectives_or_goal: Union[str, List[SubObjective], None] = "",
        max_total_retries: int = 15,
        max_repeated_cycles: int = 3,
        sub_objectives: Optional[List[SubObjective]] = None,
        goal: str = "",
    ) -> None:
        self._goal: str = ""
        self._nodes: Dict[str, ProgressNode] = {}
        self._node_order: List[str] = []
        self._active_subgoal_id: Optional[str] = None
        self._max_total_retries = max_total_retries
        self._max_repeated_cycles = max_repeated_cycles
        self._total_retries = 0
        self._cycle_history: List[str] = []

        if isinstance(sub_objectives_or_goal, list):
            self.load_sub_objectives(sub_objectives_or_goal)
        elif isinstance(sub_objectives_or_goal, str) and sub_objectives_or_goal:
            self._goal = sub_objectives_or_goal

        if sub_objectives:
            self.load_sub_objectives(sub_objectives)
        elif goal:
            self._goal = goal

    @property
    def goal(self) -> str:
        return self._goal

    @property
    def active_subgoal_id(self) -> Optional[str]:
        return self._active_subgoal_id

    @property
    def nodes(self) -> List[ProgressNode]:
        return [self._nodes[nid] for nid in self._node_order if nid in self._nodes]

    @property
    def is_all_completed(self) -> bool:
        """Whether all subgoals in the graph have been completed or skipped."""
        if not self._nodes:
            return False
        return all(n.status in (SubgoalStatus.COMPLETED, SubgoalStatus.SKIPPED) for n in self._nodes.values())

    @property
    def is_blocked(self) -> bool:
        """Whether the progress graph is blocked with no workable subgoals remaining."""
        if not self._nodes:
            return False
        return (
            any(n.status in (SubgoalStatus.BLOCKED, SubgoalStatus.FAILED) for n in self._nodes.values())
            and not self.get_active_subgoal()
            and not self.get_ready_subgoals()
        )

    def load_sub_objectives(self, sub_objectives: List[SubObjective]) -> None:
        """Initialize the graph from milestone specifications, validating acyclicity."""
        self._nodes.clear()
        self._node_order.clear()
        self._active_subgoal_id = None

        # 1. Register all nodes
        for sub in sub_objectives:
            node = ProgressNode(
                sub_id=sub.sub_id,
                title=sub.title,
                description=sub.description,
                status=SubgoalStatus.COMPLETED if sub.is_completed else SubgoalStatus.PENDING,
                dependencies=list(sub.dependencies),
                dependents=[],
            )
            self._nodes[sub.sub_id] = node
            self._node_order.append(sub.sub_id)

        # 2. Validate all dependency IDs exist and register dependents
        for node in self._nodes.values():
            for dep_id in node.dependencies:
                if dep_id not in self._nodes:
                    raise ValueError(f"Subgoal '{node.sub_id}' specifies non-existent dependency '{dep_id}'")
                self._nodes[dep_id].dependents.append(node.sub_id)

        # 3. Validate acyclicity via topological sort
        self.topological_sort()

        # 4. Initialize initial READY nodes (zero dependencies or all dependencies completed)
        for node in self._nodes.values():
            if node.status == SubgoalStatus.PENDING:
                if not node.dependencies or self._are_dependencies_satisfied(node):
                    node.status = SubgoalStatus.READY

    def add_subgoal(
        self,
        title: str,
        description: str = "",
        dependencies: Optional[List[str]] = None,
        node_id: Optional[str] = None,
    ) -> ProgressNode:
        """Add a new subgoal to the progress graph."""
        nid = node_id or f"sg_{len(self._nodes) + 1}_{uuid4().hex[:6]}"
        deps = dependencies or []
        node = ProgressNode(
            sub_id=nid,
            title=title,
            description=description,
            dependencies=deps,
            status=SubgoalStatus.PENDING,
        )
        self._nodes[nid] = node
        self._node_order.append(nid)

        # Wire dependents
        for dep_id in deps:
            if dep_id in self._nodes:
                if nid not in self._nodes[dep_id].dependents:
                    self._nodes[dep_id].dependents.append(nid)

        # Set status to READY if all dependencies are satisfied
        if not deps or self._are_dependencies_satisfied(node):
            node.status = SubgoalStatus.READY

        return node

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

    def get_node(self, sub_id: str) -> Optional[ProgressNode]:
        """Retrieve a subgoal node by its ID."""
        return self._nodes.get(sub_id)

    def get_subgoal(self, node_id: str) -> Optional[ProgressNode]:
        """Retrieve a subgoal node by its ID (alias for get_node)."""
        return self._nodes.get(node_id)

    def get_ready_subgoals(self) -> List[ProgressNode]:
        """Return list of subgoals ready to be scheduled and executed."""
        return [n for n in self._nodes.values() if n.status == SubgoalStatus.READY]

    def get_active_subgoal(self) -> Optional[ProgressNode]:
        """Return the currently executing or candidate subgoal."""
        if self._active_subgoal_id and self._active_subgoal_id in self._nodes:
            return self._nodes[self._active_subgoal_id]

        for nid in self._node_order:
            node = self._nodes[nid]
            if node.status == SubgoalStatus.IN_PROGRESS:
                self._active_subgoal_id = nid
                return node

        # If none IN_PROGRESS, check for first READY
        ready = self.get_ready_subgoals()
        if ready:
            return ready[0]

        # Check for first PENDING whose dependencies are satisfied
        for nid in self._node_order:
            node = self._nodes[nid]
            if node.status == SubgoalStatus.PENDING:
                if self._are_dependencies_satisfied(node):
                    node.status = SubgoalStatus.READY
                    return node
                else:
                    node.status = SubgoalStatus.BLOCKED

        return None

    def start_subgoal(self, sub_id: str, action_id: Optional[str] = None) -> ProgressNode:
        """Transition a READY/PENDING subgoal to IN_PROGRESS.

        Raises KeyError if not found. Raises ValueError if dependencies not met.
        """
        if sub_id not in self._nodes:
            raise KeyError(f"Subgoal '{sub_id}' not found in ProgressGraph")
        node = self._nodes[sub_id]

        if not self._are_dependencies_satisfied(node):
            node.status = SubgoalStatus.BLOCKED
            raise ValueError(f"Cannot start subgoal '{sub_id}': dependencies are not satisfied")

        node.status = SubgoalStatus.IN_PROGRESS
        node.started_at_utc = datetime.now(timezone.utc)
        self._active_subgoal_id = sub_id
        if action_id and action_id not in node.action_ids:
            node.action_ids.append(action_id)

        self._cycle_history.append(sub_id)
        return node

    def complete_subgoal(
        self,
        sub_id: str,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> ProgressNode:
        """Transition an IN_PROGRESS or READY subgoal to COMPLETED and unlock ready dependents."""
        if sub_id not in self._nodes:
            raise KeyError(f"Subgoal '{sub_id}' not found in ProgressGraph")
        node = self._nodes[sub_id]

        node.status = SubgoalStatus.COMPLETED
        node.completed_at_utc = datetime.now(timezone.utc)
        if evidence:
            node.evidence.update(evidence)

        if self._active_subgoal_id == sub_id:
            self._active_subgoal_id = None

        # Check all dependents: if all their dependencies are now COMPLETED, transition PENDING/BLOCKED -> READY
        self._unblock_dependents()

        return node

    def fail_subgoal(
        self,
        sub_id: str,
        reason: str,
        allow_retry: bool = False,
    ) -> bool:
        """Transition a subgoal to FAILED or reset to READY for retry."""
        if sub_id not in self._nodes:
            raise KeyError(f"Subgoal '{sub_id}' not found in ProgressGraph")
        node = self._nodes[sub_id]

        if allow_retry and node.retry_count < node.max_retries and self._total_retries < self._max_total_retries:
            node.retry_count += 1
            self._total_retries += 1
            node.status = SubgoalStatus.READY
            if self._active_subgoal_id == sub_id:
                self._active_subgoal_id = None
            return True

        node.status = SubgoalStatus.FAILED
        node.failure_reason = reason
        if self._active_subgoal_id == sub_id:
            self._active_subgoal_id = None

        # Cascade BLOCKED to all downstream dependents
        queue: List[str] = list(node.dependents)
        while queue:
            curr_id = queue.pop(0)
            if curr_id in self._nodes:
                curr_node = self._nodes[curr_id]
                if curr_node.status in (SubgoalStatus.PENDING, SubgoalStatus.READY):
                    curr_node.status = SubgoalStatus.BLOCKED
                    curr_node.failure_reason = f"Ancestor dependency '{sub_id}' failed: {reason}"
                    queue.extend(curr_node.dependents)

        return False

    def fail_subgoal_attempt(self, node_id: str, error_reason: str = "") -> Tuple[bool, bool]:
        """Record a failed attempt on a subgoal with loop detection.

        Returns (can_retry: bool, loop_detected: bool).
        """
        node = self._nodes.get(node_id)
        if not node:
            return (False, False)

        node.retry_count += 1
        self._total_retries += 1

        loop_detected = self._detect_loop(node_id)

        if loop_detected or node.retry_count >= node.max_retries or self._total_retries >= self._max_total_retries:
            self.fail_subgoal(node_id, reason=error_reason or "Exceeded retry limit or loop detected", allow_retry=False)
            return (False, loop_detected)

        # Allow retry
        node.status = SubgoalStatus.READY
        if self._active_subgoal_id == node_id:
            self._active_subgoal_id = None
        return (True, False)

    def _are_dependencies_satisfied(self, node: ProgressNode) -> bool:
        """Check if all prerequisite dependencies of a node are completed."""
        for dep_id in node.dependencies:
            dep = self._nodes.get(dep_id)
            if not dep or dep.status not in (SubgoalStatus.COMPLETED, SubgoalStatus.SKIPPED):
                return False
        return True

    def _unblock_dependents(self) -> None:
        """Scan and unlock any PENDING or BLOCKED subgoals whose dependencies are now met."""
        for node in self._nodes.values():
            if node.status in (SubgoalStatus.PENDING, SubgoalStatus.BLOCKED):
                if self._are_dependencies_satisfied(node):
                    node.status = SubgoalStatus.READY

    def _detect_loop(self, node_id: str) -> bool:
        """Detect repeated cycles or infinite loops on the same subgoal."""
        if len(self._cycle_history) < self._max_repeated_cycles:
            return False
        recent = self._cycle_history[-self._max_repeated_cycles:]
        return all(nid == node_id for nid in recent)

    def create_snapshot(self) -> ProgressSnapshot:
        """Create an immutable ProgressSnapshot projection for WorldModel and telemetry."""
        completed: List[str] = []
        pending: List[str] = []
        ready: List[str] = []
        blocked: List[str] = []
        failed: List[str] = []

        for nid, node in self._nodes.items():
            if node.status in (SubgoalStatus.COMPLETED, SubgoalStatus.SKIPPED):
                completed.append(nid)
            elif node.status == SubgoalStatus.PENDING:
                pending.append(nid)
            elif node.status == SubgoalStatus.READY:
                ready.append(nid)
            elif node.status == SubgoalStatus.BLOCKED:
                blocked.append(nid)
            elif node.status == SubgoalStatus.FAILED:
                failed.append(nid)

        is_fully_completed = len(completed) == len(self._nodes) and len(self._nodes) > 0
        is_failed = len(failed) > 0 and len(ready) == 0 and not self.get_active_subgoal()

        return ProgressSnapshot(
            active_subgoal_id=self._active_subgoal_id,
            completed_subgoals=completed,
            pending_subgoals=pending,
            ready_subgoals=ready,
            blocked_subgoals=blocked,
            failed_subgoals=failed,
            nodes={k: v.model_copy() for k, v in self._nodes.items()},
            is_fully_completed=is_fully_completed,
            is_failed=is_failed,
        )

    def snapshot(self) -> ProgressSnapshot:
        """Alias for create_snapshot()."""
        return self.create_snapshot()

    def get_snapshot(self) -> ProgressSnapshot:
        """Alias for create_snapshot()."""
        return self.create_snapshot()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize progress graph for WebSocket streaming and UI presentation."""
        return {
            "goal": self._goal,
            "active_subgoal_id": self._active_subgoal_id,
            "is_all_completed": self.is_all_completed,
            "is_blocked": self.is_blocked,
            "total_subgoals": len(self._nodes),
            "completed_subgoals": sum(1 for n in self._nodes.values() if n.status == SubgoalStatus.COMPLETED),
            "subgoals": [
                {
                    "node_id": n.sub_id,
                    "title": n.title,
                    "description": n.description,
                    "status": n.status.value,
                    "dependencies": n.dependencies,
                    "retry_count": n.retry_count,
                    "action_ids": n.action_ids,
                }
                for n in self.nodes
            ],
        }


__all__ = [
    "ProgressGraph",
    "ProgressNode",
    "ProgressSnapshot",
    "SubObjective",
    "SubgoalNode",
    "SubgoalStatus",
]
