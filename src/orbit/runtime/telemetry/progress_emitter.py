"""
Provenance & Architectural Attribution:
======================================
Windows-Use Source:   windows_use/agent/loop.py & watchdog/service.py
ORBIT Destination:    src/orbit/runtime/telemetry/progress_emitter.py
Integration Paradigm: Universal Step Progress & Reality-Separated Telemetry (Brain-Body Separation)

Adaptations Applied:
- Implemented UniversalStepProgressEmitter bridging ProgressGraph, ExecutionTrace, and live telemetry.
- Enforced strict Invariant: ProgressEmitter MUST NEVER infer task completion or failure from milestone counts,
  step counts, elapsed time, or percentages.
- Preserved strict distinction: PLAN PROGRESS vs ENVIRONMENT-VERIFIED PROGRESS vs GOAL VERIFICATION STATUS.
======================================
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import ActionExecutionOutcome, OutcomeStatus
from orbit.runtime.agent.progress_graph import ProgressGraph, ProgressSnapshot, SubgoalStatus
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective, SubObjective
from orbit.runtime.cognitive.plan_directive import PlanDirective
from orbit.runtime.cognitive.trace import CycleExecutionTrace
from orbit.runtime.telemetry.broadcaster import LiveTelemetryBroadcaster
from orbit.runtime.telemetry.events import StructuredTelemetryEvent, TelemetryEventType

logger = logging.getLogger(__name__)


class UniversalStepProgressStatus(BaseModel):
    """Structured, immutable snapshot of multi-tier execution progress.

    SAFETY INVARIANT:
    Separates plan estimation from verified environmental state delta and goal verification.
    """

    task_id: str
    cycle_number: int
    active_subgoal_id: Optional[str] = None
    active_subgoal_title: str = ""

    # Tier 1: Plan Progress (Estimates & milestones)
    total_subgoals_count: int = 0
    completed_subgoals_count: int = 0
    estimated_remaining_steps: int = Field(default=0, description="Estimated remaining steps (NEVER a completion condition)")

    # Tier 2: Environment-Verified Progress (Observed state deltas)
    total_actions_dispatched: int = 0
    verified_effects_count: int = 0
    failed_effects_count: int = 0

    # Tier 3: Authoritative Goal Verification Status (Sole Authority)
    goal_verification_status: str = Field(
        default="IN_PROGRESS",
        description="Authoritative status from GoalVerifier: IN_PROGRESS | VERIFIED_COMPLETE | FAILED | ABORTED",
    )
    goal_satisfied: bool = False
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UniversalStepProgressEmitter:
    """Universal step progress telemetry emitter for ORBIT.

    INVARIANTS:
    1. Observer Only: Publishes telemetry events; does NOT execute actions or plan.
    2. Zero Completion Authority: NEVER infers completion from milestone counts, percentage,
       or step counts. Only emits TASK_COMPLETED when receiving authoritative GoalVerifier evidence.
    3. Zero Failure Authority: NEVER infers TASK_FAILED without authoritative signal.
    """

    def __init__(self, broadcaster: Optional[LiveTelemetryBroadcaster] = None) -> None:
        self._broadcaster = broadcaster or LiveTelemetryBroadcaster()
        self._dispatched_count = 0
        self._verified_count = 0
        self._failed_count = 0

    @property
    def broadcaster(self) -> LiveTelemetryBroadcaster:
        return self._broadcaster

    def emit_task_started(self, objective: StructuredObjective) -> None:
        """Emit authoritative TASK_STARTED event."""
        event = StructuredTelemetryEvent(
            event_type=TelemetryEventType.TASK_STARTED,
            task_id=objective.objective_id,
            cycle_number=0,
            source_component="UniversalStepProgressEmitter",
            payload={
                "user_goal": objective.user_goal or objective.raw_prompt,
                "end_condition": objective.end_condition,
                "parameters": objective.parameters,
            },
        )
        self._broadcaster.emit(event)

    def emit_cycle_started(self, task_id: str, cycle_number: int) -> None:
        """Emit CYCLE_STARTED event."""
        event = StructuredTelemetryEvent(
            event_type=TelemetryEventType.CYCLE_STARTED,
            task_id=task_id,
            cycle_number=cycle_number,
            source_component="AgentExecutionLoop",
            payload={"cycle": cycle_number},
        )
        self._broadcaster.emit(event)

    def emit_observation_captured(
        self,
        task_id: str,
        cycle_number: int,
        obs: CurrentStateObservation,
    ) -> None:
        """Emit OBSERVATION_CAPTURED event."""
        event = StructuredTelemetryEvent(
            event_type=TelemetryEventType.OBSERVATION_CAPTURED,
            task_id=task_id,
            cycle_number=cycle_number,
            source_component="CurrentStateObserver",
            payload={
                "observation_id": getattr(obs, "observation_id", ""),
                "active_window_title": getattr(obs, "active_window_title", ""),
                "active_hwnd": getattr(obs, "active_hwnd", getattr(obs, "active_window_hwnd", 0)),
                "visible_windows_count": len(getattr(obs, "visible_windows", []) or []),
                "interactive_elements_count": len(getattr(obs, "interactive_elements", []) or []),
            },
        )
        self._broadcaster.emit(event)

    def emit_plan_directive(
        self,
        task_id: str,
        cycle_number: int,
        directive: PlanDirective,
        is_replan: bool = False,
    ) -> None:
        """Emit PLAN_DIRECTIVE_EMITTED event."""
        event = StructuredTelemetryEvent(
            event_type=TelemetryEventType.PLAN_DIRECTIVE_EMITTED,
            task_id=task_id,
            cycle_number=cycle_number,
            subgoal_id=directive.subgoal_id,
            source_component="AgentPlanner",
            payload={
                "directive_id": directive.directive_id,
                "subgoal_title": directive.subgoal_title,
                "intent_strategy": directive.intent_strategy,
                "preferred_primitives": [p.value for p in directive.preferred_primitives],
                "semantic_targets": [t.model_dump() for t in directive.semantic_targets],
                "feasibility_score": directive.feasibility_score,
                "is_replan": is_replan,
            },
        )
        self._broadcaster.emit(event)

    def emit_target_grounded(
        self,
        task_id: str,
        cycle_number: int,
        target_name: str,
        resolved: bool,
        evidence_source: str,
        confidence: float,
        coordinates: Optional[tuple[int, int]] = None,
    ) -> None:
        """Emit TARGET_GROUNDED event (Evidence-based target locator result)."""
        event = StructuredTelemetryEvent(
            event_type=TelemetryEventType.TARGET_GROUNDED,
            task_id=task_id,
            cycle_number=cycle_number,
            source_component="EvidenceBasedTargetLocator",
            payload={
                "target_name": target_name,
                "resolved": resolved,
                "evidence_source": evidence_source,
                "confidence": confidence,
                "has_coordinates": coordinates is not None,
            },
        )
        self._broadcaster.emit(event)

    def emit_primitives_composed(
        self,
        task_id: str,
        cycle_number: int,
        subgoal_id: Optional[str],
        actions_count: int,
        action_types: List[str],
    ) -> None:
        """Emit PRIMITIVES_COMPOSED event."""
        event = StructuredTelemetryEvent(
            event_type=TelemetryEventType.PRIMITIVES_COMPOSED,
            task_id=task_id,
            cycle_number=cycle_number,
            subgoal_id=subgoal_id,
            source_component="PrimitiveComposer",
            payload={
                "composed_actions_count": actions_count,
                "action_types": action_types,
            },
        )
        self._broadcaster.emit(event)

    def emit_dispatch_commenced(
        self,
        task_id: str,
        cycle_number: int,
        action_id: str,
        action_type: str,
        target_name: str,
    ) -> None:
        """Emit PHYSICAL_DISPATCH_COMMENCED event."""
        self._dispatched_count += 1
        event = StructuredTelemetryEvent(
            event_type=TelemetryEventType.PHYSICAL_DISPATCH_COMMENCED,
            task_id=task_id,
            cycle_number=cycle_number,
            source_component="PrimitiveExecutionController",
            payload={
                "action_id": action_id,
                "action_type": action_type,
                "target_name": target_name,
            },
        )
        self._broadcaster.emit(event)

    def emit_dispatch_completed(
        self,
        task_id: str,
        cycle_number: int,
        action_id: str,
        outcome: ActionExecutionOutcome,
    ) -> None:
        """Emit PHYSICAL_DISPATCH_COMPLETED event preserving Tripartite Reality."""
        event = StructuredTelemetryEvent(
            event_type=TelemetryEventType.PHYSICAL_DISPATCH_COMPLETED,
            task_id=task_id,
            cycle_number=cycle_number,
            source_component="PrimitiveExecutionController",
            dispatch_success=outcome.dispatch_success,
            expected_effect_observed=outcome.expected_effect_observed,
            goal_satisfied=outcome.goal_satisfied,
            duration_ms=outcome.duration_ms,
            payload={
                "action_id": action_id,
                "verification_reason": outcome.verification_reason,
                "error_message": outcome.error_message,
            },
        )
        self._broadcaster.emit(event)

    def emit_verification_evaluated(
        self,
        task_id: str,
        cycle_number: int,
        outcome: ActionExecutionOutcome,
    ) -> None:
        """Emit VERIFICATION_EVALUATED event preserving Tripartite Reality."""
        if outcome.expected_effect_observed:
            self._verified_count += 1
        else:
            self._failed_count += 1

        event = StructuredTelemetryEvent(
            event_type=TelemetryEventType.VERIFICATION_EVALUATED,
            task_id=task_id,
            cycle_number=cycle_number,
            source_component="MultiEvidenceActionVerifier",
            dispatch_success=outcome.dispatch_success,
            expected_effect_observed=outcome.expected_effect_observed,
            goal_satisfied=outcome.goal_satisfied,
            payload={
                "action_id": outcome.action_id,
                "verification_strategy": outcome.verification_strategy.value if hasattr(outcome.verification_strategy, "value") else str(outcome.verification_strategy),
                "verification_reason": outcome.verification_reason,
            },
        )
        self._broadcaster.emit(event)

    def emit_loop_guard_diagnosis(
        self,
        task_id: str,
        cycle_number: int,
        category: str,
        diagnosis: str,
    ) -> None:
        """Emit LOOP_GUARD_DIAGNOSIS event."""
        event = StructuredTelemetryEvent(
            event_type=TelemetryEventType.LOOP_GUARD_DIAGNOSIS,
            task_id=task_id,
            cycle_number=cycle_number,
            source_component="LoopGuardDiagnosticEngine",
            payload={
                "category": category,
                "diagnosis": diagnosis,
            },
        )
        self._broadcaster.emit(event)

    def emit_subgoal_progress(
        self,
        task_id: str,
        cycle_number: int,
        progress_graph: ProgressGraph,
    ) -> None:
        """Emit SUBGOAL_PROGRESS_ADVANCED event from authoritative ProgressGraph."""
        snapshot = progress_graph.get_snapshot()
        active_sg = progress_graph.get_active_subgoal()
        total_nodes = len(snapshot.nodes)
        completed_nodes = len(snapshot.completed_subgoals)
        pct = (completed_nodes / total_nodes * 100.0) if total_nodes > 0 else 0.0

        event = StructuredTelemetryEvent(
            event_type=TelemetryEventType.SUBGOAL_PROGRESS_ADVANCED,
            task_id=task_id,
            cycle_number=cycle_number,
            subgoal_id=active_sg.sub_id if active_sg else None,
            source_component="ProgressGraph",
            payload={
                "completed_count": completed_nodes,
                "total_count": total_nodes,
                "active_subgoal": active_sg.title if active_sg else "None",
                "progress_percentage": pct,
                "estimated_remaining_milestones": max(0, total_nodes - completed_nodes),
            },
        )
        self._broadcaster.emit(event)

    def emit_authoritative_task_completed(
        self,
        task_id: str,
        cycle_number: int,
        verification_evidence: Dict[str, Any],
    ) -> None:
        """Emit TASK_COMPLETED event ONLY upon receiving authoritative verification from GoalVerifier.

        Invariant: ProgressEmitter never infers this event.
        """
        event = StructuredTelemetryEvent(
            event_type=TelemetryEventType.TASK_COMPLETED,
            task_id=task_id,
            cycle_number=cycle_number,
            source_component="GoalVerifier",
            goal_satisfied=True,
            payload={
                "verified_completion": True,
                "evidence": verification_evidence,
            },
        )
        self._broadcaster.emit(event)

    def emit_authoritative_task_failed(
        self,
        task_id: str,
        cycle_number: int,
        reason: str,
    ) -> None:
        """Emit TASK_FAILED event ONLY upon receiving authoritative failure decision."""
        event = StructuredTelemetryEvent(
            event_type=TelemetryEventType.TASK_FAILED,
            task_id=task_id,
            cycle_number=cycle_number,
            source_component="GoalVerifier",
            goal_satisfied=False,
            payload={
                "failure_reason": reason,
            },
        )
        self._broadcaster.emit(event)

    def get_progress_status(
        self,
        task_id: str,
        cycle_number: int,
        progress_graph: Optional[ProgressGraph] = None,
        goal_satisfied: bool = False,
    ) -> UniversalStepProgressStatus:
        """Compute structured multi-tier progress snapshot."""
        total_sg = 0
        completed_sg = 0
        active_id = None
        active_title = ""

        if progress_graph:
            snap = progress_graph.get_snapshot()
            total_sg = len(snap.nodes)
            completed_sg = len(snap.completed_subgoals)
            active = progress_graph.get_active_subgoal()
            if active:
                active_id = active.sub_id
                active_title = active.title

        return UniversalStepProgressStatus(
            task_id=task_id,
            cycle_number=cycle_number,
            active_subgoal_id=active_id,
            active_subgoal_title=active_title,
            total_subgoals_count=total_sg,
            completed_subgoals_count=completed_sg,
            estimated_remaining_steps=max(0, total_sg - completed_sg),
            total_actions_dispatched=self._dispatched_count,
            verified_effects_count=self._verified_count,
            failed_effects_count=self._failed_count,
            goal_verification_status="VERIFIED_COMPLETE" if goal_satisfied else "IN_PROGRESS",
            goal_satisfied=goal_satisfied,
        )


__all__ = [
    "UniversalStepProgressStatus",
    "UniversalStepProgressEmitter",
]
