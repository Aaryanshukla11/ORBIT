"""Dynamic Subgoal Graph & Hierarchical Planner Subsystem.

Phase 3B (Astra 6 Modernization):
Provides a dynamic, DAG-based hierarchical subgoal planner supporting pre/post-condition
evaluation, dependency-aware task scheduling, automatic rollback on dead ends,
and multi-branch execution strategies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType
from orbit.runtime.agent.progress_graph import ProgressGraph, ProgressNode, SubgoalStatus
from orbit.runtime.cognitive.models import (
    CognitiveStepResult,
    CurrentStateObservation,
    StructuredObjective,
)

logger = logging.getLogger(__name__)


class ConditionPredicate(BaseModel):
    """Declarative pre-condition or post-condition requirement for a subgoal node."""

    predicate_type: str = Field(..., description="E.g. WINDOW_ACTIVE, PROCESS_RUNNING, FILE_EXISTS, TEXT_OBSERVED, CANVAS_NON_BLANK")
    target_value: str = Field(..., description="Expected window title, process name, filepath, or text snippet")
    case_sensitive: bool = Field(default=False)
    negate: bool = Field(default=False, description="If True, requires condition to NOT be true")

    def evaluate(self, observation: CurrentStateObservation) -> Tuple[bool, str]:
        """Evaluate predicate against current observation state."""
        val_lower = self.target_value.lower() if not self.case_sensitive else self.target_value

        if self.predicate_type == "WINDOW_ACTIVE":
            actual_title = observation.active_window_title or ""
            actual_cmp = actual_title.lower() if not self.case_sensitive else actual_title
            matched = val_lower in actual_cmp
            is_satisfied = not matched if self.negate else matched
            return is_satisfied, f"Window '{actual_title}' {'contains' if matched else 'does not contain'} '{self.target_value}'"

        elif self.predicate_type == "PROCESS_RUNNING":
            matched = False
            for win in observation.visible_windows:
                p_name = win.get("process_name") or win.get("class_name") or ""
                if val_lower in (p_name.lower() if not self.case_sensitive else p_name):
                    matched = True
                    break
            is_satisfied = not matched if self.negate else matched
            return is_satisfied, f"Process matching '{self.target_value}' {'found' if matched else 'not found'}"

        elif self.predicate_type == "TEXT_OBSERVED":
            ocr_tokens = getattr(observation, "ocr_tokens", []) or []
            all_words = []
            for tok in ocr_tokens:
                tok_str = tok if isinstance(tok, str) else str(tok.get("word", tok.get("text", "")))
                all_words.append(tok_str)

            joined_text = " ".join(all_words)
            cmp_joined = joined_text.lower() if not self.case_sensitive else joined_text
            matched = val_lower in cmp_joined or any(val_lower in (w.lower() if not self.case_sensitive else w) for w in all_words)
            is_satisfied = not matched if self.negate else matched
            return is_satisfied, f"OCR text '{self.target_value}' {'observed' if matched else 'not observed'} in '{joined_text[:100]}'"

        elif self.predicate_type == "CANVAS_NON_BLANK":
            c_status = getattr(observation, "canvas_status", "UNKNOWN")
            matched = c_status == "NON_BLANK"
            is_satisfied = not matched if self.negate else matched
            return is_satisfied, f"Canvas status is {c_status}"

        # Default fallback
        return True, "Predicate type unsupported, passing by default"


class DynamicSubgoalNode(BaseModel):
    """An execution node in the dynamic hierarchical subgoal DAG."""

    node_id: str = Field(default_factory=lambda: f"node_{uuid4().hex[:8]}")
    title: str = Field(..., description="Short title describing the subgoal milestone")
    description: str = Field(default="", description="Detailed goal and criteria")
    status: SubgoalStatus = Field(default=SubgoalStatus.PENDING)
    dependencies: List[str] = Field(default_factory=list, description="IDs of prerequisite nodes")
    dependents: List[str] = Field(default_factory=list, description="IDs of dependent downstream nodes")
    branch_id: str = Field(default="main", description="Logical execution branch ID (e.g. 'main', 'fallback_gui', 'fallback_cli')")
    is_alternate_branch: bool = Field(default=False)
    preconditions: List[ConditionPredicate] = Field(default_factory=list)
    postconditions: List[ConditionPredicate] = Field(default_factory=list)
    suggested_actions: List[str] = Field(default_factory=list)
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)
    failure_reason: Optional[str] = None
    completed_at_utc: Optional[datetime] = None


class DynamicSubgoalPlanner:
    """Manages the lifecycle, scheduling, pre-condition checks, and rollbacks of a subgoal DAG."""

    def __init__(self, progress_graph: Optional[ProgressGraph] = None) -> None:
        self.progress_graph = progress_graph or ProgressGraph()
        self.nodes: Dict[str, DynamicSubgoalNode] = {}
        self.active_branch: str = "main"
        self._root_node_ids: List[str] = []

    def create_node(
        self,
        title: str,
        description: str = "",
        dependencies: Optional[List[str]] = None,
        branch_id: str = "main",
        is_alternate_branch: bool = False,
        preconditions: Optional[List[ConditionPredicate]] = None,
        postconditions: Optional[List[ConditionPredicate]] = None,
        suggested_actions: Optional[List[str]] = None,
        max_retries: int = 3,
    ) -> DynamicSubgoalNode:
        """Create and register a new subgoal node in the DAG."""
        deps = list(dependencies or [])
        node = DynamicSubgoalNode(
            title=title,
            description=description,
            dependencies=deps,
            branch_id=branch_id,
            is_alternate_branch=is_alternate_branch,
            preconditions=preconditions or [],
            postconditions=postconditions or [],
            suggested_actions=suggested_actions or [],
            max_retries=max_retries,
        )
        self.nodes[node.node_id] = node

        # Update dependent links on ancestor nodes
        for parent_id in deps:
            if parent_id in self.nodes:
                if node.node_id not in self.nodes[parent_id].dependents:
                    self.nodes[parent_id].dependents.append(node.node_id)

        if not deps:
            self._root_node_ids.append(node.node_id)

        return node

    def get_schedulable_subgoals(self, observation: Optional[CurrentStateObservation] = None) -> List[DynamicSubgoalNode]:
        """Return all nodes whose dependencies are COMPLETED, belonging to the active branch."""
        schedulable: List[DynamicSubgoalNode] = []

        for node_id, node in self.nodes.items():
            if node.branch_id != self.active_branch and not (node.is_alternate_branch and node.status == SubgoalStatus.IN_PROGRESS):
                continue

            if node.status not in (SubgoalStatus.PENDING, SubgoalStatus.READY):
                continue

            # Check all dependencies are COMPLETED
            deps_met = True
            for parent_id in node.dependencies:
                parent = self.nodes.get(parent_id)
                if not parent or parent.status != SubgoalStatus.COMPLETED:
                    deps_met = False
                    break

            if not deps_met:
                continue

            # Evaluate preconditions if observation provided
            if observation and node.preconditions:
                pre_ok = True
                for pre in node.preconditions:
                    passed, _ = pre.evaluate(observation)
                    if not passed:
                        pre_ok = False
                        break
                if not pre_ok:
                    node.status = SubgoalStatus.BLOCKED
                    continue

            node.status = SubgoalStatus.READY
            schedulable.append(node)

        return schedulable

    def mark_in_progress(self, node_id: str) -> None:
        """Mark a subgoal node as actively executing."""
        if node_id in self.nodes:
            self.nodes[node_id].status = SubgoalStatus.IN_PROGRESS

    def mark_completed(self, node_id: str, observation: Optional[CurrentStateObservation] = None) -> bool:
        """Mark a subgoal node as successfully completed after validating postconditions."""
        if node_id not in self.nodes:
            return False

        node = self.nodes[node_id]

        # Verify postconditions if provided
        if observation and node.postconditions:
            for post in node.postconditions:
                passed, reason = post.evaluate(observation)
                if not passed:
                    logger.warning("Node '%s' postcondition failed: %s", node.title, reason)
                    return False

        node.status = SubgoalStatus.COMPLETED
        node.completed_at_utc = datetime.now(timezone.utc)
        return True

    def mark_failed_and_rollback(
        self,
        node_id: str,
        failure_reason: str,
        fallback_branch_id: Optional[str] = None,
    ) -> List[str]:
        """Mark node failed, rollback/block downstream dependents, and optionally activate fallback branch."""
        if node_id not in self.nodes:
            return []

        node = self.nodes[node_id]
        node.retry_count += 1

        if node.retry_count < node.max_retries:
            logger.info("Node '%s' failed attempt %d/%d; remaining in READY for retry", node.title, node.retry_count, node.max_retries)
            node.status = SubgoalStatus.READY
            return []

        node.status = SubgoalStatus.FAILED
        node.failure_reason = failure_reason

        # Recursively block all downstream dependents
        blocked_nodes: List[str] = []
        queue = list(node.dependents)
        while queue:
            curr_id = queue.pop(0)
            if curr_id in self.nodes:
                curr_node = self.nodes[curr_id]
                if curr_node.status not in (SubgoalStatus.COMPLETED, SubgoalStatus.FAILED):
                    curr_node.status = SubgoalStatus.BLOCKED
                    blocked_nodes.append(curr_id)
                    queue.extend(curr_node.dependents)

        # Switch to fallback branch if provided
        if fallback_branch_id:
            logger.info("Switching active branch from '%s' to fallback branch '%s'", self.active_branch, fallback_branch_id)
            self.active_branch = fallback_branch_id
            for n in self.nodes.values():
                if n.branch_id == fallback_branch_id and n.status == SubgoalStatus.PENDING:
                    n.status = SubgoalStatus.READY

        return blocked_nodes

    def is_all_completed(self) -> bool:
        """Check if all nodes in the active branch are COMPLETED."""
        active_nodes = [n for n in self.nodes.values() if n.branch_id == self.active_branch]
        if not active_nodes:
            return False
        return all(n.status == SubgoalStatus.COMPLETED for n in active_nodes)

    def to_summary_text(self) -> str:
        """Generate a structured text DAG representation for context prompts."""
        lines = [f"Subgoal DAG Progress (Active Branch: '{self.active_branch}'):"]
        for node in self.nodes.values():
            if node.branch_id == self.active_branch or node.status == SubgoalStatus.COMPLETED:
                icon = {
                    SubgoalStatus.COMPLETED: "[x]",
                    SubgoalStatus.IN_PROGRESS: "[>]",
                    SubgoalStatus.READY: "[o]",
                    SubgoalStatus.PENDING: "[ ]",
                    SubgoalStatus.BLOCKED: "[!]",
                    SubgoalStatus.FAILED: "[X]",
                }.get(node.status, "[?]")
                deps_str = f" (depends on {', '.join(node.dependencies)})" if node.dependencies else ""
                lines.append(f"{icon} {node.title} - {node.status.value}{deps_str}")
        return "\n".join(lines)
