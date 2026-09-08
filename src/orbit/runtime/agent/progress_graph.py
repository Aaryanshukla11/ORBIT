"""Agent Memory + Dynamic Progress Graph (Milestone M2.0).

Maintains a structured Directed Acyclic Graph of subgoals tracking progress:
Goal -> Subgoal A (COMPLETED) -> Subgoal B (COMPLETED) -> Subgoal C (IN_PROGRESS) -> Subgoal D (BLOCKED/PENDING)

SAFETY INVARIANT:
Detects and prevents loops, repeated failed actions, and infinite retry cycles.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SubgoalStatus(str, Enum):
    """Lifecycle state of an individual subgoal in the progress graph."""

    PENDING = "PENDING"          # Not yet started
    IN_PROGRESS = "IN_PROGRESS"  # Currently executing
    COMPLETED = "COMPLETED"      # Successfully verified and satisfied
    FAILED = "FAILED"            # Failed execution after retries
    BLOCKED = "BLOCKED"          # Cannot proceed due to unmet prerequisite subgoals
    SKIPPED = "SKIPPED"          # Bypassed because condition already satisfied


class SubgoalNode(BaseModel):
    """An individual milestone / subgoal node in the progress graph."""

    node_id: str = Field(default_factory=lambda: f"sg_{uuid4().hex[:8]}", description="Unique subgoal node ID")
    title: str = Field(..., description="Short title describing the subgoal milestone")
    description: str = Field(default="", description="Detailed criteria for satisfying this subgoal")
    status: SubgoalStatus = Field(default=SubgoalStatus.PENDING, description="Current progress status")
    dependencies: List[str] = Field(default_factory=list, description="IDs of prerequisite subgoals that must complete first")
    action_ids: List[str] = Field(default_factory=list, description="IDs of actions dispatched to fulfill this subgoal")
    retry_count: int = Field(default=0, ge=0, description="Number of attempts made on this subgoal")
    max_retries: int = Field(default=3, ge=1, description="Max allowed retries before marking FAILED / BLOCKED")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Verified sensory evidence proving completion")
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at_utc: Optional[datetime] = Field(default=None)


class ProgressGraph:
    """Manages the dynamic decomposition, execution state, and loop prevention of subgoals."""

    def __init__(
        self,
        goal: str = "",
        max_total_retries: int = 15,
        max_repeated_cycles: int = 3,
    ) -> None:
        self._goal = goal
        self._nodes: Dict[str, SubgoalNode] = {}
        self._node_order: List[str] = []
        self._max_total_retries = max_total_retries
        self._max_repeated_cycles = max_repeated_cycles
        self._total_retries = 0
        self._cycle_history: List[str] = []

    @property
    def goal(self) -> str:
        return self._goal

    @property
    def nodes(self) -> List[SubgoalNode]:
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
        return any(n.status in (SubgoalStatus.BLOCKED, SubgoalStatus.FAILED) for n in self._nodes.values()) and not self.get_active_subgoal()

    def add_subgoal(
        self,
        title: str,
        description: str = "",
        dependencies: Optional[List[str]] = None,
        node_id: Optional[str] = None,
    ) -> SubgoalNode:
        """Add a new subgoal to the progress graph."""
        nid = node_id or f"sg_{len(self._nodes) + 1}_{uuid4().hex[:6]}"
        node = SubgoalNode(
            node_id=nid,
            title=title,
            description=description,
            dependencies=dependencies or [],
        )
        self._nodes[nid] = node
        self._node_order.append(nid)
        return node

    def get_subgoal(self, node_id: str) -> Optional[SubgoalNode]:
        """Retrieve a subgoal by its ID."""
        return self._nodes.get(node_id)

    def get_active_subgoal(self) -> Optional[SubgoalNode]:
        """Return the current candidate subgoal ready to execute."""
        # 1. First check if any is already IN_PROGRESS
        for nid in self._node_order:
            node = self._nodes[nid]
            if node.status == SubgoalStatus.IN_PROGRESS:
                return node

        # 2. Otherwise find the first PENDING subgoal whose dependencies are satisfied
        for nid in self._node_order:
            node = self._nodes[nid]
            if node.status == SubgoalStatus.PENDING:
                if self._are_dependencies_satisfied(node):
                    return node
                else:
                    node.status = SubgoalStatus.BLOCKED

        return None

    def start_subgoal(self, node_id: str, action_id: Optional[str] = None) -> bool:
        """Transition a subgoal to IN_PROGRESS and associate an action ID."""
        node = self._nodes.get(node_id)
        if not node:
            return False

        if not self._are_dependencies_satisfied(node):
            node.status = SubgoalStatus.BLOCKED
            return False

        node.status = SubgoalStatus.IN_PROGRESS
        if action_id and action_id not in node.action_ids:
            node.action_ids.append(action_id)

        # Record cycle for loop detection
        self._cycle_history.append(node_id)
        return True

    def complete_subgoal(self, node_id: str, evidence: Optional[Dict[str, Any]] = None) -> bool:
        """Mark a subgoal as COMPLETED with verified evidence."""
        node = self._nodes.get(node_id)
        if not node:
            return False

        node.status = SubgoalStatus.COMPLETED
        node.completed_at_utc = datetime.now(timezone.utc)
        if evidence:
            node.evidence.update(evidence)

        # Unblock dependent subgoals whose prerequisites are now satisfied
        self._unblock_dependents()
        return True

    def fail_subgoal_attempt(self, node_id: str, error_reason: str = "") -> Tuple[bool, bool]:
        """Record a failed attempt on a subgoal.
        
        Returns (can_retry: bool, loop_detected: bool).
        """
        node = self._nodes.get(node_id)
        if not node:
            return (False, False)

        node.retry_count += 1
        self._total_retries += 1

        # Check loop / thrashing detection
        loop_detected = self._detect_loop(node_id)

        if loop_detected or node.retry_count >= node.max_retries or self._total_retries >= self._max_total_retries:
            node.status = SubgoalStatus.FAILED
            logger.warning(
                "Subgoal %s failed permanently (retries: %d/%d, total: %d, loop: %s): %s",
                node_id,
                node.retry_count,
                node.max_retries,
                self._total_retries,
                loop_detected,
                error_reason,
            )
            return (False, loop_detected)

        # Allow retry: return to PENDING
        node.status = SubgoalStatus.PENDING
        return (True, False)

    def _are_dependencies_satisfied(self, node: SubgoalNode) -> bool:
        """Check if all prerequisite dependencies of a node are completed."""
        for dep_id in node.dependencies:
            dep = self._nodes.get(dep_id)
            if not dep or dep.status not in (SubgoalStatus.COMPLETED, SubgoalStatus.SKIPPED):
                return False
        return True

    def _unblock_dependents(self) -> None:
        """Scan and unblock any BLOCKED subgoals whose dependencies are now met."""
        for node in self._nodes.values():
            if node.status == SubgoalStatus.BLOCKED:
                if self._are_dependencies_satisfied(node):
                    node.status = SubgoalStatus.PENDING

    def _detect_loop(self, node_id: str) -> bool:
        """Detect repeated cycles or infinite loops on the same subgoal."""
        if len(self._cycle_history) < self._max_repeated_cycles:
            return False
        recent = self._cycle_history[-self._max_repeated_cycles:]
        return all(nid == node_id for nid in recent)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize progress graph for WebSocket streaming and UI presentation."""
        return {
            "goal": self._goal,
            "is_all_completed": self.is_all_completed,
            "is_blocked": self.is_blocked,
            "total_subgoals": len(self._nodes),
            "completed_subgoals": sum(1 for n in self._nodes.values() if n.status == SubgoalStatus.COMPLETED),
            "subgoals": [
                {
                    "node_id": n.node_id,
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
