"""Directed Acyclic Graph (DAG) construction, cycle detection, and topological sorting for task plans."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple

from orbit.runtime.planning.models import PlanStep


class ActionDependencyGraph:
    """Explicit Directed Acyclic Graph (DAG) for managing and validating plan step dependencies."""

    def __init__(self):
        self._steps: Dict[str, PlanStep] = {}
        # step_id -> set of step_ids that MUST run before step_id (predecessors / dependencies)
        self._predecessors: Dict[str, Set[str]] = defaultdict(set)
        # step_id -> set of step_ids that run AFTER step_id (successors)
        self._successors: Dict[str, Set[str]] = defaultdict(set)

    @classmethod
    def from_plan(cls, plan: Any) -> ActionDependencyGraph:
        """Construct an ActionDependencyGraph from an ExecutableTaskPlan."""
        graph = cls()
        if plan and hasattr(plan, "steps"):
            for step in plan.steps:
                graph.add_step(step)
        return graph

    @property
    def steps(self) -> Dict[str, PlanStep]:
        return dict(self._steps)

    def add_step(self, step: PlanStep) -> None:
        """Add a step node to the graph and register its declared dependencies."""
        self._steps[step.step_id] = step
        for dep_id in step.dependencies:
            self.add_dependency(step.step_id, dep_id)

    def add_dependency(self, step_id: str, depends_on_step_id: str) -> None:
        """Declare that `step_id` depends on `depends_on_step_id` (depends_on must execute first)."""
        self._predecessors[step_id].add(depends_on_step_id)
        self._successors[depends_on_step_id].add(step_id)

    def get_successors(self, step_id: str) -> List[str]:
        """Return list of step_ids that depend on the given step_id."""
        return sorted(list(self._successors.get(step_id, set())))

    def get_predecessors(self, step_id: str) -> List[str]:
        """Return list of step_ids that must run before the given step_id."""
        return sorted(list(self._predecessors.get(step_id, set())))

    def has_cycles(self) -> bool:
        """Return True if any dependency cycles exist."""
        return len(self.detect_cycles()) > 0

    def find_cycle_path(self) -> str:
        """Return human-readable cycle path representation if cycles exist."""
        cycles = self.detect_cycles()
        if not cycles:
            return ""
        return "; ".join([" -> ".join(c) for c in cycles])

    def detect_cycles(self) -> List[List[str]]:
        """Detect any dependency cycles using Depth-First Search with coloring."""
        # 0 = unvisited, 1 = visiting (in active recursion stack), 2 = visited
        visited: Dict[str, int] = {sid: 0 for sid in self._steps}
        cycles: List[List[str]] = []
        path: List[str] = []

        def dfs(node: str):
            visited[node] = 1
            path.append(node)

            for succ in self._successors.get(node, set()):
                if succ not in self._steps:
                    continue
                if visited.get(succ, 0) == 1:
                    # Found cycle
                    cycle_start_idx = path.index(succ)
                    cycles.append(path[cycle_start_idx:] + [succ])
                elif visited.get(succ, 0) == 0:
                    dfs(succ)

            path.pop()
            visited[node] = 2

        for sid in self._steps:
            if visited[sid] == 0:
                dfs(sid)

        return cycles

    def topological_sort(self) -> List[PlanStep]:
        """Produce a deterministic, topologically ordered linear sequence of execution steps.

        Raises:
            ValueError if the graph contains dependency cycles or unresolved dependencies.
        """
        in_degree = {sid: len([p for p in self._predecessors[sid] if p in self._steps]) for sid in self._steps}
        queue = deque(sorted([sid for sid, deg in in_degree.items() if deg == 0]))
        sorted_steps: List[PlanStep] = []

        while queue:
            current_id = queue.popleft()
            sorted_steps.append(self._steps[current_id])

            for succ_id in sorted(self._successors.get(current_id, set())):
                if succ_id in in_degree:
                    in_degree[succ_id] -= 1
                    if in_degree[succ_id] == 0:
                        queue.append(succ_id)

        if len(sorted_steps) != len(self._steps):
            unresolved = [sid for sid, deg in in_degree.items() if deg > 0]
            raise ValueError(f"Dependency cycle or unresolvable dependencies detected in plan steps: {unresolved}")

        # Update step_index on sorted steps
        for idx, step in enumerate(sorted_steps):
            step.step_index = idx

        return sorted_steps

    def get_dependencies_map(self) -> Dict[str, List[str]]:
        """Return a mapping of step_id -> sorted list of predecessor step_ids."""
        return {
            sid: sorted(list(self._predecessors[sid]))
            for sid in self._steps
        }

    def validate(self) -> Tuple[bool, List[str]]:
        """Validate the integrity of the graph.

        Returns:
            Tuple of (is_valid, list_of_error_messages)
        """
        errors: List[str] = []

        # 1. Missing dependency reference check
        for sid, preds in self._predecessors.items():
            for pred in preds:
                if pred not in self._steps:
                    errors.append(f"Step '{sid}' depends on non-existent step '{pred}'")

        # 2. Cycle detection
        cycles = self.detect_cycles()
        if cycles:
            for cycle in cycles:
                cycle_str = " -> ".join(cycle)
                errors.append(f"Dependency cycle detected: {cycle_str}")

        return len(errors) == 0, errors
