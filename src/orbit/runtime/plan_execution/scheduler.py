"""Dependency-aware plan execution scheduler (M1.8 Step 3).

Enforces topological progression, strict predecessor success invariants,
fail-closed failure blocking, and cancellation propagation.
"""

from __future__ import annotations

from collections import deque
import logging
from typing import Dict, List, Optional, Set

from orbit.runtime.plan_execution.models import PlanStepExecutionStatus
from orbit.runtime.planning.graph import ActionDependencyGraph
from orbit.runtime.planning.models import ExecutableTaskPlan, PlanStep

logger = logging.getLogger(__name__)


class PlanExecutionScheduler:
    """Dependency-aware scheduler managing step lifecycles and readiness."""

    def __init__(self, plan: ExecutableTaskPlan) -> None:
        self._plan = plan
        self._graph = ActionDependencyGraph.from_plan(plan)
        self._steps_by_id: Dict[str, PlanStep] = {s.step_id: s for s in plan.steps}
        self._step_states: Dict[str, PlanStepExecutionStatus] = {}
        self._step_failure_reasons: Dict[str, str] = {}

        # Initialize states based on immediate dependency presence
        for step in plan.steps:
            if not step.dependencies:
                self._step_states[step.step_id] = PlanStepExecutionStatus.READY
            else:
                self._step_states[step.step_id] = PlanStepExecutionStatus.PENDING

    @property
    def plan(self) -> ExecutableTaskPlan:
        return self._plan

    @property
    def total_steps(self) -> int:
        return len(self._plan.steps)

    @property
    def is_complete(self) -> bool:
        """Return True if all steps have reached a terminal execution status."""
        terminal_statuses = {
            PlanStepExecutionStatus.SUCCEEDED,
            PlanStepExecutionStatus.FAILED,
            PlanStepExecutionStatus.BLOCKED,
            PlanStepExecutionStatus.SKIPPED,
            PlanStepExecutionStatus.CANCELLED,
            PlanStepExecutionStatus.UNSUPPORTED,
        }
        return all(state in terminal_statuses for state in self._step_states.values())

    @property
    def all_succeeded(self) -> bool:
        """Return True if every step in the plan succeeded or was safely skipped."""
        success_statuses = {
            PlanStepExecutionStatus.SUCCEEDED,
            PlanStepExecutionStatus.SKIPPED,
        }
        return len(self._step_states) > 0 and all(
            state in success_statuses for state in self._step_states.values()
        )

    def get_step_status(self, step_id: str) -> PlanStepExecutionStatus:
        return self._step_states.get(step_id, PlanStepExecutionStatus.PENDING)

    def get_step(self, step_id: str) -> Optional[PlanStep]:
        return self._steps_by_id.get(step_id)

    def get_ready_steps(self) -> List[PlanStep]:
        """Return all steps currently in READY status in topological order."""
        ready_steps: List[PlanStep] = []
        for step in self._plan.steps:
            if self._step_states.get(step.step_id) == PlanStepExecutionStatus.READY:
                # Double-check all dependencies have genuinely succeeded
                if self._check_dependencies_succeeded(step):
                    ready_steps.append(step)
                else:
                    # Not actually ready
                    self._step_states[step.step_id] = PlanStepExecutionStatus.PENDING
        return ready_steps

    def get_next_ready_step(self) -> Optional[PlanStep]:
        """Return the next eligible READY step in deterministic topological order."""
        ready = self.get_ready_steps()
        return ready[0] if ready else None

    def _check_dependencies_succeeded(self, step: PlanStep) -> bool:
        """Check that 100% of predecessor dependencies have status SUCCEEDED."""
        for dep_id in step.dependencies:
            dep_state = self._step_states.get(dep_id)
            if dep_state not in {PlanStepExecutionStatus.SUCCEEDED, PlanStepExecutionStatus.SKIPPED}:
                return False
        return True

    def mark_running(self, step_id: str) -> None:
        """Transition a step from READY to RUNNING."""
        curr = self._step_states.get(step_id)
        if curr != PlanStepExecutionStatus.READY:
            raise ValueError(f"Cannot transition step {step_id} to RUNNING from state {curr}")
        self._step_states[step_id] = PlanStepExecutionStatus.RUNNING

    def mark_succeeded(self, step_id: str) -> None:
        """Transition a step to SUCCEEDED and promote eligible downstream dependents to READY."""
        self._step_states[step_id] = PlanStepExecutionStatus.SUCCEEDED
        logger.info("Plan step %s SUCCEEDED", step_id)

        # Check downstream dependents
        successors = self._graph.get_successors(step_id)
        for succ_id in successors:
            succ_step = self._steps_by_id.get(succ_id)
            if succ_step and self._step_states.get(succ_id) == PlanStepExecutionStatus.PENDING:
                if self._check_dependencies_succeeded(succ_step):
                    self._step_states[succ_id] = PlanStepExecutionStatus.READY
                    logger.debug("Promoted dependent step %s to READY", succ_id)

    def mark_failed(self, step_id: str, reason: str = "Execution failed") -> None:
        """Transition a step to FAILED and recursively block all downstream dependents."""
        self._step_states[step_id] = PlanStepExecutionStatus.FAILED
        self._step_failure_reasons[step_id] = reason
        logger.warning("Plan step %s FAILED: %s", step_id, reason)
        self._block_downstream_dependents(step_id, f"Predecessor step '{step_id}' failed: {reason}")

    def mark_unsupported(self, step_id: str, reason: str = "Step action unsupported") -> None:
        """Transition a step to UNSUPPORTED and recursively block all downstream dependents."""
        self._step_states[step_id] = PlanStepExecutionStatus.UNSUPPORTED
        self._step_failure_reasons[step_id] = reason
        logger.warning("Plan step %s UNSUPPORTED: %s", step_id, reason)
        self._block_downstream_dependents(step_id, f"Predecessor step '{step_id}' was unsupported: {reason}")

    def mark_skipped(self, step_id: str, reason: str = "Step skipped by policy") -> None:
        """Transition a step to SKIPPED and check if dependents can proceed."""
        self._step_states[step_id] = PlanStepExecutionStatus.SKIPPED
        logger.info("Plan step %s SKIPPED: %s", step_id, reason)

        successors = self._graph.get_successors(step_id)
        for succ_id in successors:
            succ_step = self._steps_by_id.get(succ_id)
            if succ_step and self._step_states.get(succ_id) == PlanStepExecutionStatus.PENDING:
                if self._check_dependencies_succeeded(succ_step):
                    self._step_states[succ_id] = PlanStepExecutionStatus.READY

    def mark_cancelled(self, reason: str = "Execution cancelled") -> None:
        """Mark any non-terminal steps as CANCELLED."""
        non_terminal = {
            PlanStepExecutionStatus.PENDING,
            PlanStepExecutionStatus.READY,
            PlanStepExecutionStatus.RUNNING,
        }
        for step_id, state in list(self._step_states.items()):
            if state in non_terminal:
                self._step_states[step_id] = PlanStepExecutionStatus.CANCELLED
                self._step_failure_reasons[step_id] = reason

    def _block_downstream_dependents(self, failed_step_id: str, reason: str) -> None:
        """Recursively mark all downstream dependent steps as BLOCKED."""
        queue: deque[str] = deque(self._graph.get_successors(failed_step_id))
        visited: Set[str] = set()

        while queue:
            curr_id = queue.popleft()
            if curr_id in visited:
                continue
            visited.add(curr_id)

            curr_state = self._step_states.get(curr_id)
            if curr_state in {PlanStepExecutionStatus.PENDING, PlanStepExecutionStatus.READY}:
                self._step_states[curr_id] = PlanStepExecutionStatus.BLOCKED
                self._step_failure_reasons[curr_id] = reason
                logger.info("Marked step %s BLOCKED: %s", curr_id, reason)

            for next_succ in self._graph.get_successors(curr_id):
                if next_succ not in visited:
                    queue.append(next_succ)
