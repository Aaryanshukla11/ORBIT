"""
Phase 4 Verification Test Suite: Perception, LoopGuard & Fault Resilience.

Validates the strict Brain-Body Separation and cognitive replanning invariants:
1. LoopGuardDiagnosticEngine is diagnosis-only (produces FailureReport, never executes actions).
2. LoopGuard consumes fresh post-action observations and state fingerprints.
3. LoopGuard detects:
   - Stalled loops (3 consecutive unchanged state fingerprints)
   - Repetitive action spam (sliding window repetitions)
   - Failed action retries
   - State cycles (A -> B -> A)
   - Dead window handles
4. Invariant Proof:
   LOOP DETECTED != RECOVERY ACTION EXECUTED DIRECTLY
   and instead:
   LOOP DETECTED -> FailureReport -> AgentPlanner.replan() -> NEW PlanDirective -> PrimitiveComposer -> PrimitiveExecutionController
5. Invariant Proof:
   The NEW PlanDirective emitted by AgentPlanner.replan() strictly differs from the failed strategy
   (e.g., UIA Click -> Keyboard Shortcut or Physical Click).
"""

from datetime import datetime, timezone
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionExecutionResult,
    OutcomeStatus,
    SemanticTarget,
)
from orbit.runtime.cognitive.agent_planner import AgentPlanner
from orbit.runtime.cognitive.failure_analyst import (
    CognitiveFailureAnalyst,
    FailureCategory,
    FailureReport,
    LoopGuardDiagnosticEngine,
)
from orbit.runtime.cognitive.models import (
    CurrentStateObservation,
    StructuredObjective,
    SubObjective,
)
from orbit.runtime.cognitive.plan_directive import PlanDirective
from orbit.runtime.cognitive.primitive_composer import PrimitiveComposer
from orbit.runtime.cognitive.primitive_execution_controller import PrimitiveExecutionController
from orbit.runtime.cognitive.primitive_validator import PrimitiveValidator
from orbit.runtime.cognitive.recovery import AgentRecoveryManager, RecoveryRecord, RecoveryStrategy
from orbit.runtime.world_model import AgentWorldModel


class TestPhase4PerceptionAndLoopGuard(unittest.TestCase):
    """Test suite for LoopGuard diagnostic engine and cognitive failure analysis."""

    def setUp(self):
        self.loop_guard = LoopGuardDiagnosticEngine(window=5, max_stagnant_steps=3)
        self.analyst = CognitiveFailureAnalyst()
        self.planner = AgentPlanner()
        self.composer = PrimitiveComposer()

    def _create_obs(self, hwnd=1001, title="Test Window", elements=None, ocr=None):
        return CurrentStateObservation(
            observation_id=f"obs_{uuid4().hex[:8]}",
            active_hwnd=hwnd,
            active_window_title=title,
            visible_windows=[{"hwnd": hwnd, "title": title}],
            interactive_elements=elements or [{"control_type": "Button", "name": "Submit"}],
            ocr_tokens=ocr or ["Submit", "Cancel"],
            target_app_exists=True,
            target_app_is_active=True,
        )

    def _create_action(self, act_type=AbstractActionType.CLICK, target_name="Submit", params=None):
        return AbstractAction(
            action_id=f"act_{uuid4().hex[:8]}",
            action_type=act_type,
            target=SemanticTarget(name=target_name, role="control"),
            parameters=params or {},
            expected_effect="State delta expected",
        )

    def _create_failed_outcome(self, reason="No state transition observed"):
        return ActionExecutionOutcome(
            action_id="act_test",
            dispatch_success=True,
            expected_effect_observed=False,
            outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
            verified=False,
            verification_reason=reason,
        )

    def _create_success_outcome(self):
        return ActionExecutionOutcome(
            action_id="act_ok",
            dispatch_success=True,
            expected_effect_observed=True,
            outcome_status=OutcomeStatus.EFFECT_VERIFIED,
            verified=True,
        )

    def test_loopguard_is_diagnosis_only_and_emits_failure_report(self):
        """Proof 1: LoopGuard returns FailureReport only, with zero action execution methods."""
        self.assertFalse(hasattr(self.loop_guard, "execute"))
        self.assertFalse(hasattr(self.loop_guard, "execute_action"))
        self.assertFalse(hasattr(self.loop_guard, "execute_recovery"))

        obs = self._create_obs()
        action = self._create_action()
        outcome = self._create_failed_outcome()

        # Diagnosis on first action is None (no loop yet)
        report = self.loop_guard.record_and_diagnose(action, obs, outcome)
        self.assertIsNone(report)

    def test_stalled_loop_detection(self):
        """Proof 2: LoopGuard detects stagnant UI state across 3 consecutive failed steps."""
        obs_frozen = self._create_obs(title="Frozen Calculator", elements=[{"control_type": "Edit", "name": "Display"}])
        act1 = self._create_action(AbstractActionType.CLICK, "Button 1")
        act2 = self._create_action(AbstractActionType.CLICK, "Button 2")
        act3 = self._create_action(AbstractActionType.CLICK, "Button 3")
        outcome = self._create_failed_outcome()

        # Step 1
        rep1 = self.loop_guard.record_and_diagnose(act1, obs_frozen, outcome)
        self.assertIsNone(rep1)

        # Step 2
        rep2 = self.loop_guard.record_and_diagnose(act2, obs_frozen, outcome)
        self.assertIsNone(rep2)

        # Step 3 -> STALLED_LOOP_DETECTED
        rep3 = self.loop_guard.record_and_diagnose(act3, obs_frozen, outcome)
        self.assertIsNotNone(rep3)
        self.assertIsInstance(rep3, FailureReport)
        self.assertEqual(rep3.category, FailureCategory.STALLED_LOOP_DETECTED)
        self.assertIn("consecutive steps", rep3.diagnosis)

    def test_failed_action_retry_detection(self):
        """Proof 3: Repeating the exact same failed action triggers FAILED_ACTION_RETRY."""
        obs = self._create_obs()
        action = self._create_action(AbstractActionType.CLICK, "Save Button")
        outcome = self._create_failed_outcome()

        # Step 1: fails
        self.loop_guard.record_and_diagnose(action, obs, outcome)

        # Step 2: same action dispatched again with no strategy adaptation
        rep2 = self.loop_guard.record_and_diagnose(action, obs, outcome)
        self.assertIsNotNone(rep2)
        self.assertEqual(rep2.category, FailureCategory.FAILED_ACTION_RETRY)
        self.assertFalse(rep2.is_transient)

    def test_repetitive_action_in_sliding_window(self):
        """Proof 4: Dispatching the same action 3 times in sliding window triggers REPETITIVE_ACTION_DETECTED."""
        obs1 = self._create_obs(title="State 1")
        obs2 = self._create_obs(title="State 2")
        action = self._create_action(AbstractActionType.CLICK, "Next Button")
        success_outcome = self._create_success_outcome()

        self.loop_guard.record_and_diagnose(action, obs1, success_outcome)
        self.loop_guard.record_and_diagnose(action, obs2, success_outcome)
        rep3 = self.loop_guard.record_and_diagnose(action, obs1, success_outcome)

        self.assertIsNotNone(rep3)
        self.assertEqual(rep3.category, FailureCategory.REPETITIVE_ACTION_DETECTED)

    def test_state_cycle_detection(self):
        """Proof 5: Returning to identical UI states (A -> B -> A -> B -> A) triggers STATE_CYCLE_DETECTED."""
        obs_a = self._create_obs(title="View A", elements=[{"control_type": "Pane", "name": "Panel A"}])
        obs_b = self._create_obs(title="View B", elements=[{"control_type": "Pane", "name": "Panel B"}])
        act_a = self._create_action(AbstractActionType.CLICK, "Go to B")
        act_b = self._create_action(AbstractActionType.CLICK, "Go to A")
        ok_outcome = self._create_success_outcome()

        self.loop_guard.record_and_diagnose(act_a, obs_a, ok_outcome)  # A visit 1
        self.loop_guard.record_and_diagnose(act_b, obs_b, ok_outcome)  # B visit 1
        self.loop_guard.record_and_diagnose(act_a, obs_a, ok_outcome)  # A visit 2
        self.loop_guard.record_and_diagnose(act_b, obs_b, ok_outcome)  # B visit 2
        rep = self.loop_guard.record_and_diagnose(act_a, obs_a, ok_outcome)  # A visit 3

        self.assertIsNotNone(rep)
        self.assertEqual(rep.category, FailureCategory.STATE_CYCLE_DETECTED)
        self.assertIn("cyclic loop", rep.diagnosis)

    def test_dead_window_and_com_disconnect_diagnosis(self):
        """Proof 6: COM disconnect or dead window handle is categorized as DEAD_WINDOW_HANDLE."""
        action = self._create_action(AbstractActionType.CLICK, "File Menu")
        com_outcome = ActionExecutionOutcome(
            action_id="act_com",
            dispatch_success=False,
            expected_effect_observed=False,
            outcome_status=OutcomeStatus.DISPATCH_FAILED,
            verified=False,
            error_message="COM error RPC_E_DISCONNECTED (0x80010108)",
        )
        obs = self._create_obs()
        rep = self.analyst.analyze_failure(action, obs, obs, com_outcome)

        self.assertIsNotNone(rep)
        self.assertEqual(rep.category, FailureCategory.DEAD_WINDOW_HANDLE)
        self.assertFalse(rep.is_transient)

    def test_loop_detected_does_not_execute_recovery_action_directly(self):
        """Proof 7 (Guardrail 9): LOOP DETECTED != RECOVERY ACTION EXECUTED DIRECTLY.

        Instead, the flow is strictly:
        LOOP DETECTED -> FailureReport -> AgentPlanner.replan() -> NEW PlanDirective -> execution
        """
        # 1. Setup stalled loop condition
        obs = self._create_obs(title="Unresponsive Dialog", elements=[{"control_type": "Button", "name": "Save"}])
        failed_action = self._create_action(AbstractActionType.CLICK, "Save")
        failed_outcome = self._create_failed_outcome("Save click produced no response")

        # Emulate 3 steps of stagnation in LoopGuard
        self.loop_guard.record_and_diagnose(failed_action, obs, failed_outcome)
        self.loop_guard.record_and_diagnose(failed_action, obs, failed_outcome)
        failure_rep = self.loop_guard.record_and_diagnose(failed_action, obs, failed_outcome)

        self.assertIsNotNone(failure_rep)
        self.assertEqual(failure_rep.category, FailureCategory.STALLED_LOOP_DETECTED)

        # 2. Assert that LoopGuard and FailureAnalyst NEVER execute actions
        self.assertFalse(hasattr(self.loop_guard, "execute_recovery"))
        self.assertFalse(hasattr(self.analyst, "execute_recovery"))

        # 3. Pass FailureReport to authoritative AgentPlanner.replan()
        objective = StructuredObjective(
            objective_id="obj_test",
            raw_prompt="Save the document as report.txt",
            user_goal="Save document",
            end_condition="Document saved to disk",
            parameters={"filename": "report.txt"},
        )
        subgoal = SubObjective(
            sub_id="sg_1",
            title="Save Document",
            description="Click save button",
        )
        failed_directive = PlanDirective(
            directive_id="dir_failed_1",
            objective_id=objective.objective_id,
            subgoal_id=subgoal.sub_id,
            subgoal_title=subgoal.title,
            intent_strategy="GUI_INTERACTIVE",
            preferred_primitives=[AbstractActionType.CLICK],
            semantic_targets=[SemanticTarget(name="Save", role="control")],
        )

        world_model = AgentWorldModel()
        new_directive, sem_report = self.planner.replan(
            objective=objective,
            subgoal=subgoal,
            world_model=world_model,
            failure_report=failure_rep,
            failed_directive=failed_directive,
            observation=obs,
        )

        self.assertTrue(sem_report.is_feasible)
        self.assertIsNotNone(new_directive)
        # 4. Authoritative replanner produced a NEW PlanDirective with alternative modality
        self.assertNotEqual(new_directive.directive_id, failed_directive.directive_id)
        self.assertIn(AbstractActionType.SEND_HOTKEY, new_directive.preferred_primitives)
        self.assertEqual(new_directive.intent_strategy, "KEYBOARD_SHORTCUT")

        # 5. PrimitiveComposer composes strictly from NEW PlanDirective
        composed_seq = self.composer.compose_from_directive(new_directive)
        self.assertTrue(len(composed_seq.actions) > 0)
        self.assertEqual(composed_seq.actions[0].action_type, AbstractActionType.SEND_HOTKEY)
        self.assertEqual(composed_seq.actions[0].parameters.get("hotkey"), "ctrl+s")

    def test_new_plan_directive_differs_from_failed_strategy(self):
        """Proof 8: The NEW PlanDirective differs from the failed strategy when replanning is required."""
        objective = StructuredObjective(
            objective_id="obj_calc",
            raw_prompt="Open Calculator and calculate total",
            user_goal="Calculate total",
            end_condition="Total calculated and displayed",
            parameters={},
        )
        subgoal = SubObjective(
            sub_id="sg_calc_submit",
            title="Submit Calculation",
            description="Click Equals button",
        )
        failed_directive = PlanDirective(
            directive_id="dir_click_eq",
            objective_id=objective.objective_id,
            subgoal_id=subgoal.sub_id,
            subgoal_title=subgoal.title,
            intent_strategy="GUI_INTERACTIVE",
            preferred_primitives=[AbstractActionType.CLICK],
            semantic_targets=[SemanticTarget(name="Equals", role="control")],
        )
        failure_rep = FailureReport(
            action_id="act_click_eq",
            action_type=AbstractActionType.CLICK,
            category=FailureCategory.TARGET_UNRESPONSIVE,
            diagnosis="Click on Equals button had no effect",
        )

        new_directive, sem_report = self.planner.replan(
            objective=objective,
            subgoal=subgoal,
            world_model=AgentWorldModel(),
            failure_report=failure_rep,
            failed_directive=failed_directive,
        )

        self.assertTrue(sem_report.is_feasible)
        self.assertIsNotNone(new_directive)
        # Verify strict distinction
        self.assertNotEqual(new_directive.directive_id, failed_directive.directive_id)
        self.assertNotEqual(new_directive.candidate_plan_id, failed_directive.candidate_plan_id)
        self.assertNotEqual(new_directive.intent_strategy, failed_directive.intent_strategy)
        self.assertNotEqual(new_directive.preferred_primitives, failed_directive.preferred_primitives)
        self.assertEqual(new_directive.preferred_primitives, [AbstractActionType.SEND_HOTKEY])


if __name__ == "__main__":
    unittest.main()
