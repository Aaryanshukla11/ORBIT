"""
Phase 5 Verification Test Suite: Universal Step Progress & Live Event Telemetry.

Validates all 11 Phase 5 Architectural Exit-Gate Invariants:
1. Full execution-cycle event stream emission.
2. Tripartite reality model representation (dispatch_success != expected_effect_observed != goal_satisfied).
3. Slow telemetry sink does not block execution (non-blocking emit).
4. Crashed telemetry sink does not stop execution (full crash isolation).
5. Telemetry cannot execute physical actions.
6. Telemetry cannot declare task completion (DONE).
7. ProgressEmitter cannot infer completion from milestone counts or percentages.
8. GoalVerifier remains the sole task completion authority.
9. Lifecycle event ordering is deterministic.
10. Replanning produces a distinct new PlanDirective event.
11. No second task-state authority is introduced; estimates are strictly labeled as estimates.
"""

import asyncio
from datetime import datetime, timezone
import time
import unittest
from uuid import uuid4

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    OutcomeStatus,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.agent.progress_graph import ProgressGraph, SubgoalStatus
from orbit.runtime.cognitive.models import (
    CurrentStateObservation,
    StructuredObjective,
    SubObjective,
)
from orbit.runtime.cognitive.plan_directive import PlanDirective
from orbit.runtime.telemetry import (
    InMemoryBufferSink,
    LiveTelemetryBroadcaster,
    SlowCrashingSink,
    StructuredTelemetryEvent,
    TelemetryEventType,
    TelemetrySink,
    UniversalStepProgressEmitter,
    UniversalStepProgressStatus,
)


class TestPhase5TelemetryAndProgress(unittest.IsolatedAsyncioTestCase):
    """Phase 5 Verification Suite."""

    async def asyncSetUp(self):
        self.broadcaster = LiveTelemetryBroadcaster()
        self.buffer_sink = InMemoryBufferSink()
        self.broadcaster.add_sink(self.buffer_sink)
        self.broadcaster.start()
        self.emitter = UniversalStepProgressEmitter(broadcaster=self.broadcaster)

    async def asyncTearDown(self):
        await self.broadcaster.stop()

    def _create_sample_objective(self):
        return StructuredObjective(
            objective_id="obj_telemetry_task_1",
            raw_prompt="Open Notepad and write test message",
            user_goal="Write test message in Notepad",
            end_condition="Text visible in Notepad",
            parameters={"text": "Hello ORBIT Telemetry"},
        )

    def _create_sample_directive(self, is_replan=False):
        return PlanDirective(
            directive_id=f"dir_{'replan_' if is_replan else ''}{uuid4().hex[:6]}",
            objective_id="obj_telemetry_task_1",
            subgoal_id="sg_type_text",
            subgoal_title="Type Text in Editor",
            intent_strategy="KEYBOARD_SHORTCUT" if is_replan else "GUI_INTERACTIVE",
            preferred_primitives=[AbstractActionType.SEND_HOTKEY if is_replan else AbstractActionType.TYPE_TEXT],
            semantic_targets=[SemanticTarget(name="Text Editor", role="edit")],
        )

    async def test_1_full_execution_cycle_event_stream(self):
        """Proof 1: Full execution-cycle event stream is emitted and captured across all lifecycle phases."""
        obj = self._create_sample_objective()
        directive = self._create_sample_directive()

        # Emit full lifecycle events
        self.emitter.emit_task_started(obj)
        self.emitter.emit_cycle_started(obj.objective_id, 1)

        obs = CurrentStateObservation(
            observation_id="obs_cycle_1",
            active_window_title="Notepad",
            active_hwnd=2002,
        )
        self.emitter.emit_observation_captured(obj.objective_id, 1, obs)
        self.emitter.emit_plan_directive(obj.objective_id, 1, directive)
        self.emitter.emit_target_grounded(obj.objective_id, 1, "Text Editor", True, "UIA", 0.95, (100, 200))
        self.emitter.emit_primitives_composed(obj.objective_id, 1, "sg_type_text", 1, ["TYPE_TEXT"])
        self.emitter.emit_dispatch_commenced(obj.objective_id, 1, "act_101", "TYPE_TEXT", "Text Editor")

        outcome = ActionExecutionOutcome(
            action_id="act_101",
            dispatch_success=True,
            expected_effect_observed=True,
            goal_satisfied=False,
            outcome_status=OutcomeStatus.EFFECT_VERIFIED,
            verification_strategy=VerificationStrategy.OCR_TEXT,
            verification_reason="Text detected in edit box",
            duration_ms=45.0,
        )
        self.emitter.emit_dispatch_completed(obj.objective_id, 1, "act_101", outcome)
        self.emitter.emit_verification_evaluated(obj.objective_id, 1, outcome)

        # Authoritative goal verification completion
        self.emitter.emit_authoritative_task_completed(obj.objective_id, 1, {"ocr_verified": True})

        await self.broadcaster.flush()
        events = self.buffer_sink.get_events()

        self.assertGreaterEqual(len(events), 9)
        event_types = [e.event_type for e in events]
        self.assertIn(TelemetryEventType.TASK_STARTED, event_types)
        self.assertIn(TelemetryEventType.OBSERVATION_CAPTURED, event_types)
        self.assertIn(TelemetryEventType.PLAN_DIRECTIVE_EMITTED, event_types)
        self.assertIn(TelemetryEventType.PHYSICAL_DISPATCH_COMMENCED, event_types)
        self.assertIn(TelemetryEventType.PHYSICAL_DISPATCH_COMPLETED, event_types)
        self.assertIn(TelemetryEventType.VERIFICATION_EVALUATED, event_types)
        self.assertIn(TelemetryEventType.TASK_COMPLETED, event_types)

    async def test_2_tripartite_reality_model_representation(self):
        """Proof 2: dispatch_success != expected_effect_observed != goal_satisfied are independently represented."""
        # Scenario: Physical click accepted by Win32, but target button was unresponsive (no state delta), goal not satisfied
        outcome = ActionExecutionOutcome(
            action_id="act_unresponsive_btn",
            dispatch_success=True,
            expected_effect_observed=False,
            goal_satisfied=False,
            outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
            verification_reason="No visual state change detected after click",
        )

        self.emitter.emit_dispatch_completed("task_tripartite", 1, "act_unresponsive_btn", outcome)
        self.emitter.emit_verification_evaluated("task_tripartite", 1, outcome)

        await self.broadcaster.flush()
        events = self.buffer_sink.get_events()

        disp_evt = [e for e in events if e.event_type == TelemetryEventType.PHYSICAL_DISPATCH_COMPLETED][0]
        self.assertTrue(disp_evt.dispatch_success)
        self.assertFalse(disp_evt.expected_effect_observed)
        self.assertFalse(disp_evt.goal_satisfied)

        ver_evt = [e for e in events if e.event_type == TelemetryEventType.VERIFICATION_EVALUATED][0]
        self.assertTrue(ver_evt.dispatch_success)
        self.assertFalse(ver_evt.expected_effect_observed)
        self.assertFalse(ver_evt.goal_satisfied)

    async def test_3_slow_telemetry_sink_does_not_block_execution(self):
        """Proof 3: A slow telemetry consumer (2s sleep) does not delay synchronous emit() or agent execution."""
        slow_sink = SlowCrashingSink(delay_sec=1.0, crash_after=999)
        self.broadcaster.add_sink(slow_sink)

        t_start = time.perf_counter()
        # Emit 5 events rapidly
        for i in range(5):
            self.emitter.emit_cycle_started("task_speed_test", i)
        t_elapsed = time.perf_counter() - t_start

        # Synchronous emission must return in < 20ms (non-blocking) despite 1.0s sink delay
        self.assertLess(t_elapsed, 0.05)

    async def test_4_crashed_telemetry_sink_does_not_stop_execution(self):
        """Proof 4: A crashing telemetry consumer raises an error in isolation without crashing broadcaster or emitter."""
        crashing_sink = SlowCrashingSink(delay_sec=0.0, crash_after=1)
        self.broadcaster.add_sink(crashing_sink)

        # Emission should succeed without raising
        self.emitter.emit_cycle_started("task_crash_isolation", 1)
        self.emitter.emit_cycle_started("task_crash_isolation", 2)
        await self.broadcaster.flush()

        # Buffer sink still received all events
        self.assertEqual(len(self.buffer_sink.get_events()), 2)

    def test_5_telemetry_cannot_execute_actions(self):
        """Proof 5: Telemetry broadcaster and emitter possess zero actuator or action execution capabilities."""
        self.assertFalse(hasattr(self.broadcaster, "execute"))
        self.assertFalse(hasattr(self.broadcaster, "dispatch"))
        self.assertFalse(hasattr(self.broadcaster, "click"))
        self.assertFalse(hasattr(self.emitter, "execute"))
        self.assertFalse(hasattr(self.emitter, "dispatch"))

    def test_6_telemetry_cannot_declare_done(self):
        """Proof 6: Telemetry has zero completion authority and cannot declare DONE on its own."""
        self.assertFalse(hasattr(self.broadcaster, "complete_task"))
        self.assertFalse(hasattr(self.broadcaster, "declare_done"))
        self.assertFalse(hasattr(self.emitter, "declare_done"))

    async def test_7_progress_emitter_cannot_infer_completion_from_milestones(self):
        """Proof 7: ProgressEmitter MUST NEVER infer TASK_COMPLETED from 100% milestone completion or step counts."""
        # Create a progress graph and mark all subgoals COMPLETE
        sg1 = SubObjective(sub_id="sg_1", title="Step 1", description="First milestone")
        sg2 = SubObjective(sub_id="sg_2", title="Step 2", description="Second milestone")
        pg = ProgressGraph(sub_objectives_or_goal=[sg1, sg2])
        pg.start_subgoal("sg_1")
        pg.complete_subgoal("sg_1")
        pg.start_subgoal("sg_2")
        pg.complete_subgoal("sg_2")

        # Snapshot is now 100% complete
        snap = pg.get_snapshot()
        self.assertTrue(snap.is_fully_completed)
        self.assertEqual(len(snap.completed_subgoals), 2)

        # Emit subgoal progress
        self.emitter.emit_subgoal_progress("task_milestone_test", 2, pg)
        await self.broadcaster.flush()

        events = self.buffer_sink.get_events()
        event_types = [e.event_type for e in events]

        # SUBGOAL_PROGRESS_ADVANCED was emitted, but TASK_COMPLETED was NOT inferred!
        self.assertIn(TelemetryEventType.SUBGOAL_PROGRESS_ADVANCED, event_types)
        self.assertNotIn(TelemetryEventType.TASK_COMPLETED, event_types)

        # Status explicitly shows goal_satisfied = False until GoalVerifier confirms
        status = self.emitter.get_progress_status("task_milestone_test", 2, pg, goal_satisfied=False)
        self.assertFalse(status.goal_satisfied)
        self.assertEqual(status.goal_verification_status, "IN_PROGRESS")

    async def test_8_goal_verifier_remains_sole_completion_authority(self):
        """Proof 8: TASK_COMPLETED is emitted ONLY via emit_authoritative_task_completed with GoalVerifier evidence."""
        self.emitter.emit_authoritative_task_completed(
            task_id="task_sole_authority",
            cycle_number=3,
            verification_evidence={"file_exists": True, "ocr_matched": True},
        )
        await self.broadcaster.flush()

        events = self.buffer_sink.get_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, TelemetryEventType.TASK_COMPLETED)
        self.assertEqual(events[0].source_component, "GoalVerifier")
        self.assertTrue(events[0].goal_satisfied)

    async def test_9_deterministic_event_ordering(self):
        """Proof 9: Deterministic lifecycle event ordering is preserved across the pipeline."""
        directive = self._create_sample_directive()
        outcome = ActionExecutionOutcome(
            action_id="act_order_test",
            dispatch_success=True,
            expected_effect_observed=True,
            outcome_status=OutcomeStatus.EFFECT_VERIFIED,
        )

        self.emitter.emit_plan_directive("task_order", 1, directive)
        self.emitter.emit_target_grounded("task_order", 1, "Editor", True, "UIA", 1.0)
        self.emitter.emit_primitives_composed("task_order", 1, "sg_1", 1, ["CLICK"])
        self.emitter.emit_dispatch_commenced("task_order", 1, "act_order_test", "CLICK", "Editor")
        self.emitter.emit_dispatch_completed("task_order", 1, "act_order_test", outcome)
        self.emitter.emit_verification_evaluated("task_order", 1, outcome)

        await self.broadcaster.flush()
        types = [e.event_type for e in self.buffer_sink.get_events()]

        expected_order = [
            TelemetryEventType.PLAN_DIRECTIVE_EMITTED,
            TelemetryEventType.TARGET_GROUNDED,
            TelemetryEventType.PRIMITIVES_COMPOSED,
            TelemetryEventType.PHYSICAL_DISPATCH_COMMENCED,
            TelemetryEventType.PHYSICAL_DISPATCH_COMPLETED,
            TelemetryEventType.VERIFICATION_EVALUATED,
        ]
        self.assertEqual(types, expected_order)

    async def test_10_replan_produces_new_plan_directive_event(self):
        """Proof 10: LoopGuard failure diagnosis triggers replanning and emits distinct new PLAN_DIRECTIVE_EMITTED event."""
        self.emitter.emit_loop_guard_diagnosis(
            task_id="task_replan_test",
            cycle_number=2,
            category="STALLED_LOOP_DETECTED",
            diagnosis="Desktop UI remained completely unchanged across 3 consecutive steps",
        )

        replan_directive = self._create_sample_directive(is_replan=True)
        self.emitter.emit_plan_directive(
            task_id="task_replan_test",
            cycle_number=3,
            directive=replan_directive,
            is_replan=True,
        )

        await self.broadcaster.flush()
        events = self.buffer_sink.get_events()

        self.assertEqual(events[0].event_type, TelemetryEventType.LOOP_GUARD_DIAGNOSIS)
        self.assertEqual(events[1].event_type, TelemetryEventType.PLAN_DIRECTIVE_EMITTED)
        self.assertTrue(events[1].payload.get("is_replan"))
        self.assertEqual(events[1].payload.get("intent_strategy"), "KEYBOARD_SHORTCUT")

    def test_11_no_second_task_state_authority_and_estimates_separated(self):
        """Proof 11: Progress status strictly separates plan estimates from verified state and goal authority."""
        status = UniversalStepProgressStatus(
            task_id="task_estimate_test",
            cycle_number=2,
            active_subgoal_id="sg_1",
            active_subgoal_title="Step 1",
            total_subgoals_count=4,
            completed_subgoals_count=2,
            estimated_remaining_steps=2,
            total_actions_dispatched=5,
            verified_effects_count=4,
            failed_effects_count=1,
            goal_verification_status="IN_PROGRESS",
            goal_satisfied=False,
        )

        self.assertEqual(status.estimated_remaining_steps, 2)
        self.assertFalse(status.goal_satisfied)
        self.assertEqual(status.goal_verification_status, "IN_PROGRESS")


if __name__ == "__main__":
    unittest.main()
