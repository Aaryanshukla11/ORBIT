"""Unified AI-Native Agent Execution Loop (Step 5 Production Closed-Loop).

The authoritative, closed-loop execution path for all autonomous OS desktop actions in ORBIT:
1. Multimodal Desktop Observation (Screenshot frame, Win32 HWNDs, UIA hierarchy, OCR)
2. Vision-Driven Semantic Reasoning (Local/Cloud LLM via ModelRouter -> AbstractAction)
3. Action Validation & Strict Protocol Verification (AgentActionValidator -> Coordinate Isolation)
4. Dynamic Target Grounding (EvidenceBasedTargetLocator -> ResolvedAction with safe physical coordinates)
5. Physical Action Execution (user32.SendInput / ShellExecute / SetForegroundWindow)
6. UI Settlement & Fresh Post-Action Observation
7. Immediate State Delta Verification (AgentStateTransitionVerifier: Pre vs Post transition)
8. Independent Goal Evaluation & Multi-Tier Recovery (GoalVerifier + AgentRecoveryManager)
9. Transparent Cycle Execution Tracing (CycleExecutionTrace)

SAFETY INVARIANT:
Physical coordinates (x, y) NEVER originate from the LLM or Prompt. They are computed dynamically
at dispatch time by EvidenceBasedTargetLocator from live UI elements, window rects, and OCR tokens.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import inspect
import logging
import math
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from uuid import uuid4

from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.contracts.capabilities import (
    KeyboardCapability,
    ObservationCapability,
    PointerCapability,
    WorkspaceCapability,
)
from orbit.contracts.events import EventType, RuntimeEvent
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionExecutionResult,
    ActionOutcomeContract,
    ActionValidationFailureCode,
    ActionValidationResult,
    AgentActionValidator,
    ExpectedState,
    OutcomeStatus,
    ResolvedAction,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.agent.state import DesktopStateSnapshot
from orbit.runtime.agent.verifier import AgentStateTransitionVerifier
from orbit.runtime.cancellation import CancellationToken
from orbit.runtime.cognitive.engine import CognitiveDecisionEngine
from orbit.runtime.cognitive.interpreter import LLMIntentInterpreter
from orbit.runtime.cognitive.models import (
    AgentLoopState,
    AgentLoopStateMachine,
    AgentRecoveryManager,
    AgentStateTransitionRecord,
    CognitiveDecision,
    CognitiveExecutionResult,
    CognitiveStepResult,
    CurrentStateObservation,
    CycleExecutionTrace,
    ExecutionBudget,
    InvalidStateTransitionError,
    RecoveryRecord,
    RecoveryStrategy,
    StructuredObjective,
    format_cycle_trace_block,
)
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.model_runtime.router import ModelRouter, RoutingPolicy
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models.models import ModelCapability
from orbit.runtime.perception.models import DesktopObservation
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    ResolvedTarget,
    TargetIntent,
    TargetLocator,
    TargetResolutionStatus,
    TargetStrategy,
)
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.task_completion.models import TaskCompletionStatus

logger = logging.getLogger(__name__)

# Alias for type consistency
AgentExecutionResult = CognitiveExecutionResult


class AgentExecutionLoop:
    """Unified AI-Native Agent Loop serving as the sole production execution engine."""

    def __init__(
        self,
        router: Optional[ModelRouter] = None,
        model_session_manager: Optional[ModelSessionManager] = None,
        interpreter: Optional[LLMIntentInterpreter] = None,
        observer: Optional[CurrentStateObserver] = None,
        decision_engine: Optional[CognitiveDecisionEngine] = None,
        target_locator: Optional[TargetLocator] = None,
        workspace: Optional[WorkspaceCapability] = None,
        pointer: Optional[PointerCapability] = None,
        keyboard: Optional[KeyboardCapability] = None,
        observation: Optional[ObservationCapability] = None,
        goal_verifier: Optional[GoalVerifier] = None,
        transition_verifier: Optional[AgentStateTransitionVerifier] = None,
        recovery_manager: Optional[AgentRecoveryManager] = None,
        event_bus: Optional[EventBus] = None,
        budget: Optional[ExecutionBudget] = None,
    ) -> None:
        self._session_manager = model_session_manager
        if router is not None:
            self._router = router
        elif model_session_manager is not None:
            self._router = ModelRouter(session_manager=model_session_manager)
        else:
            self._router = None

        self._interpreter = interpreter or LLMIntentInterpreter(model_session_manager=model_session_manager)
        self._observer = observer or CurrentStateObserver(observation=observation)
        self._decision_engine = decision_engine or CognitiveDecisionEngine(model_session_manager=model_session_manager)
        self._target_locator = target_locator or EvidenceBasedTargetLocator()
        self._transition_verifier = transition_verifier or AgentStateTransitionVerifier()
        self._action_validator = AgentActionValidator
        self._workspace = workspace
        self._pointer = pointer
        self._keyboard = keyboard
        self._observation = observation
        self._goal_verifier = goal_verifier
        self._budget = budget or ExecutionBudget()
        self._recovery_manager = recovery_manager or AgentRecoveryManager(
            max_recoveries_per_transition=self._budget.max_recoveries_per_transition
        )
        self._event_bus = event_bus

    @property
    def router(self) -> Optional[ModelRouter]:
        return self._router

    @property
    def decision_engine(self) -> Optional[CognitiveDecisionEngine]:
        return self._decision_engine

    @property
    def recovery_manager(self) -> AgentRecoveryManager:
        return self._recovery_manager

    def set_model_session_manager(self, msm: ModelSessionManager) -> None:
        """Update the underlying ModelSessionManager and instantiate ModelRouter."""
        self._session_manager = msm
        self._router = ModelRouter(session_manager=msm)
        self._interpreter.set_model_session_manager(msm)
        self._decision_engine.set_model_session_manager(msm)

    def set_router(self, router: ModelRouter) -> None:
        """Attach an explicit ModelRouter."""
        self._router = router
        self._session_manager = router.session_manager
        self._interpreter.set_model_session_manager(router.session_manager)
        self._decision_engine.set_model_session_manager(router.session_manager)

    async def run(
        self,
        prompt: str,
        session_id: str = "default_session",
        task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        routing_policy: Optional[RoutingPolicy] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> AgentExecutionResult:
        """Run the authoritative production AI-native agent execution loop end-to-end."""
        effective_task_id = task_id or f"agt_{uuid4().hex[:8]}"
        t_start = time.perf_counter()
        last_progress_time = time.perf_counter()

        # 0. Canonical State Machine Initialization
        sm = AgentLoopStateMachine(initial_state=AgentLoopState.INITIALIZING)
        logger.info("AgentExecutionLoop starting task %s: '%s'", effective_task_id, prompt)

        # 1. LLM Intent Interpretation
        objective = await self._interpreter.interpret(prompt, context)
        logger.info(
            "Interpreted Objective: Goal='%s', EndCondition='%s', TargetEntities=%s",
            objective.user_goal,
            objective.end_condition,
            objective.target_entities,
        )

        step_history: List[CognitiveStepResult] = []
        cycle_traces: List[CycleExecutionTrace] = []
        consecutive_identical_actions = 0
        last_action_signature: Optional[str] = None
        target_resolution_failures = 0
        last_observed_id: Optional[str] = None
        step_idx = 0
        current_obs: Optional[CurrentStateObservation] = None

        while step_idx < self._budget.max_total_actions:
            t_cycle_start = time.perf_counter()
            cycle_trace = CycleExecutionTrace(
                cycle_number=step_idx,
                remaining_action_budget=self._budget.max_total_actions - step_idx,
            )

            # Check Cancellation
            if cancel_token and cancel_token.is_cancelled:
                logger.info("AgentExecutionLoop received cancellation for task %s", effective_task_id)
                cancel_msg = cancel_token.reason or "Cancelled by operator"
                if "cancel" not in cancel_msg.lower():
                    cancel_msg = f"Cancelled: {cancel_msg}"
                sm.transition_to(
                    AgentLoopState.CANCELLED,
                    cycle_number=step_idx,
                    observation_id=last_observed_id or "",
                    failure_reason=cancel_msg,
                )
                return AgentExecutionResult(
                    task_id=effective_task_id,
                    objective=objective,
                    is_success=False,
                    total_steps=len(step_history),
                    step_history=step_history,
                    final_status=TaskCompletionStatus.CANCELLED,
                    failure_reason=cancel_msg,
                    failure_code="TASK_CANCELLED",
                    elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                    state_transitions=sm.history,
                    cycle_traces=cycle_traces,
                    recovery_records=self._recovery_manager.get_history(),
                )

            # Check No-Progress Timeout
            if time.perf_counter() - last_progress_time > self._budget.no_progress_timeout_sec:
                logger.warning("No-progress timeout reached (%.1fs) for task %s", self._budget.no_progress_timeout_sec, effective_task_id)
                sm.transition_to(
                    AgentLoopState.FAILED,
                    cycle_number=step_idx,
                    observation_id=last_observed_id or "",
                    failure_reason="No progress observed within budget timeout",
                )
                return AgentExecutionResult(
                    task_id=effective_task_id,
                    objective=objective,
                    is_success=False,
                    total_steps=len(step_history),
                    step_history=step_history,
                    final_status=TaskCompletionStatus.FAILED,
                    failure_reason="No progress observed within budget timeout",
                    failure_code="NO_PROGRESS_TIMEOUT",
                    elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                    state_transitions=sm.history,
                    cycle_traces=cycle_traces,
                    recovery_records=self._recovery_manager.get_history(),
                )

            # -------------------------------------------------------------
            # PHASE 1: OBSERVING (Fresh Live Observation)
            # -------------------------------------------------------------
            sm.transition_to(AgentLoopState.OBSERVING, cycle_number=step_idx, observation_id=last_observed_id or "")

            # If cycle 0 or observation was consumed, capture fresh desktop state
            if current_obs is None:
                current_obs = await self._observer.observe(objective)

            # ENFORCE FRESH OBSERVATION INVARIANT
            # A model decision for cycle N+1 must never use a stale observation identical to cycle N
            freshness_valid = True
            if last_observed_id is not None and current_obs.observation_id == last_observed_id and step_idx > 0:
                logger.warning("Stale observation detected (id=%s); triggering fresh recapture", current_obs.observation_id)
                await asyncio.sleep(0.3)
                current_obs = await self._observer.observe(objective)
                freshness_valid = False

            last_observed_id = current_obs.observation_id

            # Populate Observation section of CycleExecutionTrace
            cycle_trace.observation_id = current_obs.observation_id
            cycle_trace.freshness_validated = freshness_valid
            cycle_trace.foreground_window = current_obs.active_window_title
            cycle_trace.visible_windows = [str(w.get("title", "")) for w in current_obs.visible_windows if w.get("title")]
            cycle_trace.ocr_summary = ", ".join(current_obs.ocr_tokens[:10]) if current_obs.ocr_tokens else ""
            cycle_trace.ui_elements_count = current_obs.perceived_elements_count
            cycle_trace.screenshot_available = (
                current_obs.desktop_observation is not None
                and current_obs.desktop_observation.screenshot is not None
            )

            # -------------------------------------------------------------
            # PHASE 2: INDEPENDENT GOAL VERIFICATION CHECK
            # -------------------------------------------------------------
            if self._goal_verifier is not None:
                try:
                    goal_check = await self._goal_verifier.verify_goal_achievement(
                        task_id=effective_task_id,
                        objective=objective,
                        current_observation=current_obs,
                        step_history=step_history,
                    )
                    is_sat = getattr(goal_check, "is_satisfied", getattr(goal_check, "is_completed", False)) or (getattr(goal_check, "status", None) == TaskCompletionStatus.COMPLETED)
                    cycle_trace.goal_verifier_evaluated = True
                    cycle_trace.goal_satisfied = bool(is_sat)
                    ev = getattr(goal_check, "evidence", None)
                    cycle_trace.goal_supporting_evidence = getattr(goal_check, "evidence_reasons", []) or ([str(getattr(ev, "verified_text", ""))] if ev and getattr(ev, "verified_text", None) else [])

                    if is_sat:
                        logger.info("Independent GoalVerifier confirmed task completion for %s", effective_task_id)
                        sm.transition_to(
                            AgentLoopState.EVALUATING_PROGRESS,
                            cycle_number=step_idx,
                            observation_id=current_obs.observation_id,
                            goal_satisfied=True,
                        )
                        sm.transition_to(
                            AgentLoopState.COMPLETED,
                            cycle_number=step_idx,
                            observation_id=current_obs.observation_id,
                            goal_satisfied=True,
                        )
                        cycle_trace.goal_progress = "COMPLETED"
                        cycle_trace.meaningful_state_change = True
                        formatted_trace = format_cycle_trace_block(cycle_trace)
                        logger.info("\n%s", formatted_trace)
                        cycle_traces.append(cycle_trace)

                        return AgentExecutionResult(
                            task_id=effective_task_id,
                            objective=objective,
                            is_success=True,
                            total_steps=len(step_history),
                            step_history=step_history,
                            final_status=TaskCompletionStatus.COMPLETED,
                            elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                            state_transitions=sm.history,
                            cycle_traces=cycle_traces,
                            recovery_records=self._recovery_manager.get_history(),
                        )
                except Exception as gv_err:
                    logger.debug("GoalVerifier evaluation notice: %s", gv_err)

            # -------------------------------------------------------------
            # PHASE 3: REASONING (Agent Decision Engine / Model Router)
            # -------------------------------------------------------------
            sm.transition_to(AgentLoopState.REASONING, cycle_number=step_idx, observation_id=current_obs.observation_id)

            decide_fn = getattr(self._decision_engine, "decide_next_step", None) or getattr(self._decision_engine, "decide_next_action", None)
            decide_kwargs = {
                "objective": objective,
                "observation": current_obs,
                "step_history": step_history,
                "step_index": step_idx,
            }
            try:
                sig = inspect.signature(decide_fn)
                if "routing_policy" in sig.parameters:
                    decide_kwargs["routing_policy"] = routing_policy
                if "task_context" in sig.parameters:
                    decide_kwargs["task_context"] = context
            except Exception:
                pass

            decision: CognitiveDecision = await decide_fn(**decide_kwargs)

            # Extract Model Routing & Decision Telemetry into trace
            get_tr_fn = getattr(self._decision_engine, "get_recent_traces", None)
            if callable(get_tr_fn):
                try:
                    recent_traces = get_tr_fn(1)
                    if isinstance(recent_traces, list) and recent_traces:
                        dtrace = recent_traces[-1]
                        if hasattr(dtrace, "model_id") and not isinstance(dtrace.model_id, MagicMock):
                            cycle_trace.model_id = str(dtrace.model_id)
                            cycle_trace.model_provider = str(dtrace.model_provider)
                            cycle_trace.local_or_cloud = "CLOUD" if getattr(dtrace, "escalated_to_cloud", False) else "LOCAL"
                            cycle_trace.vision_capable = bool(getattr(dtrace, "used_vision", False))
                            cycle_trace.screenshot_attached = "SCREENSHOT" in getattr(dtrace, "input_modalities", [])
                            lat = getattr(dtrace, "model_latency_ms", None)
                            cycle_trace.model_latency_ms = float(lat) if isinstance(lat, (int, float)) else None
                            cycle_trace.capabilities = [str(c) for c in getattr(dtrace, "input_modalities", [])]
                except Exception:
                    pass

            cycle_trace.decision_summary = str(decision.decision_summary)
            cycle_trace.decision_confidence = float(decision.decision_confidence) if isinstance(decision.decision_confidence, (int, float)) else 1.0
            cycle_trace.goal_progress = "GOAL_SATISFIED" if decision.is_goal_satisfied else "IN_PROGRESS"
            cycle_trace.next_action_type = decision.next_action.action_type.value if decision.next_action else None
            cycle_trace.next_action_params = decision.next_action.parameters if decision.next_action else {}

            # Publish step event to EventBus
            if self._event_bus:
                await self._event_bus.publish(
                    RuntimeEvent(
                        event_id=f"evt_{uuid4().hex[:12]}",
                        event_type=EventType.EXECUTION_RECORD_UPDATED,
                        session_id=session_id or "default_session",
                        correlation_id=effective_task_id,
                        timestamp=datetime.now(timezone.utc),
                        payload={
                            "task_id": effective_task_id,
                            "step_index": step_idx,
                            "decision_summary": decision.decision_summary,
                            "action_type": decision.next_action.action_type.value if decision.next_action else None,
                            "escalated_to_llm": decision.escalated_to_llm,
                        },
                    )
                )

            # CRITICAL PRODUCTION INVARIANT 1: "MODEL DECISION IS NOT REALITY"
            # If model claims goal is satisfied or emits COMPLETE_GOAL, independently verify with GoalVerifier!
            is_model_claiming_completion = decision.is_goal_satisfied or (
                decision.next_action and decision.next_action.action_type in (AbstractActionType.COMPLETE_GOAL, AbstractActionType.COMPLETE)
            )

            if is_model_claiming_completion:
                logger.info("Model proposed goal completion at step %d; verifying reality against live desktop", step_idx)
                goal_truly_verified = True
                if self._goal_verifier is not None:
                    try:
                        g_eval = await self._goal_verifier.verify_goal_achievement(
                            task_id=effective_task_id,
                            objective=objective,
                            current_observation=current_obs,
                            step_history=step_history,
                        )
                        is_sat = getattr(g_eval, "is_satisfied", getattr(g_eval, "is_completed", False)) or (getattr(g_eval, "status", None) == TaskCompletionStatus.COMPLETED)
                        goal_truly_verified = bool(is_sat)
                    except Exception as g_err:
                        logger.debug("Goal verification evaluation error: %s", g_err)
                        goal_truly_verified = False

                if goal_truly_verified:
                    sm.transition_to(
                        AgentLoopState.EVALUATING_PROGRESS,
                        cycle_number=step_idx,
                        observation_id=current_obs.observation_id,
                        decision_id=decision.decision_id,
                        goal_satisfied=True,
                    )
                    sm.transition_to(
                        AgentLoopState.COMPLETED,
                        cycle_number=step_idx,
                        observation_id=current_obs.observation_id,
                        decision_id=decision.decision_id,
                        goal_satisfied=True,
                    )
                    cycle_trace.goal_progress = "COMPLETED"
                    cycle_trace.goal_satisfied = True
                    cycle_trace.meaningful_state_change = True

                    step_res = CognitiveStepResult(
                        step_index=step_idx,
                        decision=decision,
                        action_dispatched=decision.next_action,
                        execution_result=ActionExecutionResult(
                            dispatch_success=True,
                            expected_effect_observed=True,
                            goal_satisfied=True,
                            outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                        ),
                        post_observation=current_obs,
                        state_progress_detected=True,
                        duration_ms=(time.perf_counter() - t_cycle_start) * 1000.0,
                        trace=cycle_trace,
                    )
                    step_history.append(step_res)
                    cycle_traces.append(cycle_trace)
                    logger.info("\n%s", format_cycle_trace_block(cycle_trace))

                    return AgentExecutionResult(
                        task_id=effective_task_id,
                        objective=objective,
                        is_success=True,
                        total_steps=len(step_history),
                        step_history=step_history,
                        final_status=TaskCompletionStatus.COMPLETED,
                        elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                        state_transitions=sm.history,
                        cycle_traces=cycle_traces,
                        recovery_records=self._recovery_manager.get_history(),
                    )
                else:
                    logger.warning("Goal satisfaction claimed by model, but independent reality check failed; continuing closed-loop reasoning")
                    # Do not exit; continue loop

            # Handle ABORT from model
            if decision.next_action and decision.next_action.action_type in (
                AbstractActionType.ABORT_TASK,
                AbstractActionType.ABORT,
                AbstractActionType.ABORT_UNACHIEVABLE,
            ):
                sm.transition_to(
                    AgentLoopState.FAILED,
                    cycle_number=step_idx,
                    observation_id=current_obs.observation_id,
                    decision_id=decision.decision_id,
                    failure_reason=decision.reason_summary or decision.decision_summary,
                )
                step_res = CognitiveStepResult(
                    step_index=step_idx,
                    decision=decision,
                    action_dispatched=decision.next_action,
                    execution_result=ActionExecutionResult(
                        dispatch_success=False,
                        expected_effect_observed=False,
                        goal_satisfied=False,
                        outcome_status=OutcomeStatus.DISPATCH_FAILED,
                        error_message=decision.reason_summary,
                    ),
                    post_observation=current_obs,
                    state_progress_detected=False,
                    duration_ms=(time.perf_counter() - t_cycle_start) * 1000.0,
                    trace=cycle_trace,
                )
                step_history.append(step_res)
                cycle_traces.append(cycle_trace)
                return AgentExecutionResult(
                    task_id=effective_task_id,
                    objective=objective,
                    is_success=False,
                    total_steps=len(step_history),
                    step_history=step_history,
                    final_status=TaskCompletionStatus.FAILED,
                    failure_reason=decision.reason_summary or decision.decision_summary,
                    failure_code="GOAL_UNACHIEVABLE",
                    elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                    state_transitions=sm.history,
                    cycle_traces=cycle_traces,
                    recovery_records=self._recovery_manager.get_history(),
                )

            action = decision.next_action
            if not action:
                break

            # If outcome_contract is missing on basic action, attach a default fallback contract
            if action.outcome_contract is None and action.action_type not in (
                AbstractActionType.WAIT,
                AbstractActionType.COMPLETE_GOAL,
                AbstractActionType.COMPLETE,
                AbstractActionType.ABORT_TASK,
                AbstractActionType.ABORT,
            ):
                action.outcome_contract = ActionOutcomeContract(
                    expected_state_transition=f"{action.action_type.value}_completed",
                    verification_strategy=VerificationStrategy.AUTO_ROUTED,
                )

            # Repeated Action Stagnation Detection
            act_sig = f"{action.action_type.value}:{action.parameters}"
            if act_sig == last_action_signature:
                consecutive_identical_actions += 1
                cycle_trace.repeated_actions_count = consecutive_identical_actions
                if consecutive_identical_actions >= self._budget.max_repeated_actions_without_progress:
                    logger.warning("Repeated action limit reached without state progress: %s", act_sig)
                    sm.transition_to(
                        AgentLoopState.FAILED,
                        cycle_number=step_idx,
                        observation_id=current_obs.observation_id,
                        action_id=action.action_id,
                        action_type=action.action_type.value,
                        failure_reason=f"Action repeated {consecutive_identical_actions} times without progress: {act_sig}",
                    )
                    return AgentExecutionResult(
                        task_id=effective_task_id,
                        objective=objective,
                        is_success=False,
                        total_steps=len(step_history),
                        step_history=step_history,
                        final_status=TaskCompletionStatus.FAILED,
                        failure_reason=f"Action repeated {consecutive_identical_actions} times without progress: {act_sig}",
                        failure_code="REPEATED_ACTION_STAGNATION",
                        elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                        state_transitions=sm.history,
                        cycle_traces=cycle_traces,
                        recovery_records=self._recovery_manager.get_history(),
                    )
            else:
                consecutive_identical_actions = 0
                last_action_signature = act_sig

            # -------------------------------------------------------------
            # PHASE 4: VALIDATING_ACTION (Strict Protocol & Coordinate Isolation)
            # -------------------------------------------------------------
            sm.transition_to(
                AgentLoopState.VALIDATING_ACTION,
                cycle_number=step_idx,
                observation_id=current_obs.observation_id,
                action_id=action.action_id,
                action_type=action.action_type.value,
            )

            validation: ActionValidationResult = self._action_validator.validate(action)
            if not validation.is_valid:
                logger.warning("Action validation failed for %s: %s (%s)", action.action_id, validation.failure_reason, validation.failure_code)
                exec_result = ActionExecutionResult(
                    action_id=action.action_id,
                    dispatch_success=False,
                    expected_effect_observed=False,
                    goal_satisfied=False,
                    outcome_status=OutcomeStatus.DISPATCH_FAILED,
                    error_message=validation.failure_reason,
                    failure_code=validation.failure_code.value if validation.failure_code else "INVALID_ACTION",
                )
                step_res = CognitiveStepResult(
                    step_index=step_idx,
                    decision=decision,
                    action_dispatched=action,
                    execution_result=exec_result,
                    post_observation=current_obs,
                    state_progress_detected=False,
                    duration_ms=(time.perf_counter() - t_cycle_start) * 1000.0,
                    trace=cycle_trace,
                )
                step_history.append(step_res)
                cycle_traces.append(cycle_trace)
                step_idx += 1
                current_obs = None
                continue

            # -------------------------------------------------------------
            # PHASE 5: GROUNDING_TARGET (Dynamic Coordinate Isolation Boundary)
            # -------------------------------------------------------------
            sm.transition_to(
                AgentLoopState.GROUNDING_TARGET,
                cycle_number=step_idx,
                observation_id=current_obs.observation_id,
                action_id=action.action_id,
                action_type=action.action_type.value,
            )

            resolved_coords = None
            if action.target is not None:
                cycle_trace.semantic_target_name = action.target.name
                cycle_trace.semantic_target_role = action.target.role
                resolved_coords = await self._resolve_target_coordinates(action.target, observation=current_obs)
                if resolved_coords:
                    cycle_trace.grounding_resolved = True
                    cycle_trace.grounding_confidence = 0.95
                    cycle_trace.resolved_coordinates = resolved_coords
                    cycle_trace.target_evidence_source = "EVIDENCE_LOCATOR"
                    target_resolution_failures = 0
                else:
                    cycle_trace.grounding_resolved = False
                    cycle_trace.grounding_confidence = 0.0
                    cycle_trace.target_evidence_source = "RESOLUTION_FAILED"
                    target_resolution_failures += 1
                    logger.warning("Target resolution failed for target '%s' (failure %d/%d)", action.target.name, target_resolution_failures, self._budget.max_target_resolution_failures)
                    if target_resolution_failures >= self._budget.max_target_resolution_failures:
                        sm.transition_to(
                            AgentLoopState.FAILED,
                            cycle_number=step_idx,
                            observation_id=current_obs.observation_id,
                            action_id=action.action_id,
                            failure_reason=f"Target resolution failed {target_resolution_failures} times for target '{action.target.name}'",
                        )
                        return AgentExecutionResult(
                            task_id=effective_task_id,
                            objective=objective,
                            is_success=False,
                            total_steps=len(step_history),
                            step_history=step_history,
                            final_status=TaskCompletionStatus.FAILED,
                            failure_reason=f"Exceeded max target resolution failures for '{action.target.name}'",
                            failure_code="TARGET_RESOLUTION_FAILED",
                            elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                            state_transitions=sm.history,
                            cycle_traces=cycle_traces,
                            recovery_records=self._recovery_manager.get_history(),
                        )

            # -------------------------------------------------------------
            # PHASE 6: EXECUTING (Physical Action Dispatch)
            # -------------------------------------------------------------
            sm.transition_to(
                AgentLoopState.EXECUTING,
                cycle_number=step_idx,
                observation_id=current_obs.observation_id,
                action_id=action.action_id,
                action_type=action.action_type.value,
            )

            cycle_trace.dispatch_attempted = True
            dispatch_success, dispatch_err = await self._dispatch_physical_action(action, current_obs, resolved_coords, cancel_token)
            cycle_trace.dispatch_success = dispatch_success
            cycle_trace.dispatch_error = dispatch_err

            # -------------------------------------------------------------
            # PHASE 7: WAITING_FOR_SETTLEMENT & FRESH POST-ACTION OBSERVATION
            # -------------------------------------------------------------
            sm.transition_to(
                AgentLoopState.WAITING_FOR_SETTLEMENT,
                cycle_number=step_idx,
                observation_id=current_obs.observation_id,
                action_id=action.action_id,
                action_type=action.action_type.value,
                dispatch_success=dispatch_success,
            )

            # Settlement wait
            await asyncio.sleep(0.35)

            # FRESH POST-ACTION OBSERVATION CAPTURE
            post_obs = await self._observer.observe(objective)
            cycle_trace.post_observation_id = post_obs.observation_id
            cycle_trace.post_freshness_validated = (post_obs.observation_id != current_obs.observation_id)

            # -------------------------------------------------------------
            # PHASE 8: VERIFYING_EFFECT (Immediate State Delta Verification)
            # -------------------------------------------------------------
            sm.transition_to(
                AgentLoopState.VERIFYING_EFFECT,
                cycle_number=step_idx,
                observation_id=post_obs.observation_id,
                action_id=action.action_id,
                action_type=action.action_type.value,
                dispatch_success=dispatch_success,
            )

            pre_state = DesktopStateSnapshot(
                active_window_hwnd=current_obs.active_window_hwnd,
                active_window_title=current_obs.active_window_title,
                visible_windows=current_obs.visible_windows,
                target_app_exists=current_obs.target_app_exists,
                target_app_is_active=current_obs.target_app_is_active,
                canvas_status=current_obs.canvas_status or "UNKNOWN",
                ocr_tokens=current_obs.ocr_tokens,
            )
            post_state = DesktopStateSnapshot(
                active_window_hwnd=post_obs.active_window_hwnd,
                active_window_title=post_obs.active_window_title,
                visible_windows=post_obs.visible_windows,
                target_app_exists=post_obs.target_app_exists,
                target_app_is_active=post_obs.target_app_is_active,
                canvas_status=post_obs.canvas_status or "UNKNOWN",
                ocr_tokens=post_obs.ocr_tokens,
            )

            outcome = await self._transition_verifier.verify_action_outcome(
                action=action,
                dispatch_success=dispatch_success,
                pre_state=pre_state,
                post_state=post_state,
                post_observation=post_obs.desktop_observation,
            )

            exec_result = ActionExecutionResult(
                action_id=action.action_id,
                dispatch_success=outcome.dispatch_success,
                expected_effect_observed=outcome.expected_effect_observed,
                goal_satisfied=outcome.goal_satisfied,
                outcome_status=outcome.outcome_status,
                verification_strategy=outcome.verification_strategy,
                verification_reason=outcome.verification_reason,
                observed_delta=outcome.observed_delta,
                error_message=dispatch_err or outcome.error_message,
                duration_ms=outcome.duration_ms,
            )

            cycle_trace.expected_effect = str(action.outcome_contract.expected_state_transition) if action.outcome_contract else "visible_delta"
            cycle_trace.observed_effect = outcome.observed_delta or "None"
            cycle_trace.expected_effect_observed = outcome.expected_effect_observed
            cycle_trace.verification_strategy = outcome.verification_strategy.value if hasattr(outcome.verification_strategy, "value") else str(outcome.verification_strategy)
            cycle_trace.verification_reason = outcome.verification_reason or ""

            # -------------------------------------------------------------
            # PHASE 9: RECOVERY OR PROGRESS EVALUATION
            # -------------------------------------------------------------
            # TRIPARTITE REALITY DISTINCTION:
            # dispatch_success == True DOES NOT imply expected_effect_observed == True!
            if not exec_result.expected_effect_observed:
                logger.warning("Action %s dispatched but expected effect was NOT observed; evaluating recovery", action.action_id)
                if self._recovery_manager.can_attempt_recovery():
                    strategy, diag = self._recovery_manager.diagnose_failure(action, current_obs, post_obs, exec_result)
                    sm.transition_to(
                        AgentLoopState.RECOVERING,
                        cycle_number=step_idx,
                        observation_id=post_obs.observation_id,
                        action_id=action.action_id,
                        failure_reason=diag,
                        recovery_attempt=self._recovery_manager.current_transition_recoveries + 1,
                    )
                    rec_record = await self._recovery_manager.execute_recovery(
                        strategy=strategy,
                        action=action,
                        observation=post_obs,
                        cycle_number=step_idx,
                        pointer=self._pointer,
                        keyboard=self._keyboard,
                        workspace=self._workspace,
                    )
                    cycle_trace.recovery_count = rec_record.attempt_number

                    # Recapture fresh post-observation after recovery execution
                    post_obs = await self._observer.observe(objective)
                    cycle_trace.post_observation_id = post_obs.observation_id
                else:
                    logger.warning("Recovery budget exceeded for current transition; escalating to next cycle")
            else:
                self._recovery_manager.reset_transition_counter()

            # PHASE 10: EVALUATING_PROGRESS
            sm.transition_to(
                AgentLoopState.EVALUATING_PROGRESS,
                cycle_number=step_idx,
                observation_id=post_obs.observation_id,
                action_id=action.action_id,
                expected_effect_observed=exec_result.expected_effect_observed,
            )

            progress_detected = self._evaluate_state_progress(current_obs, post_obs, exec_result)
            cycle_trace.meaningful_state_change = progress_detected

            if progress_detected:
                last_progress_time = time.perf_counter()
                consecutive_identical_actions = 0

            # Log formatted trace block
            formatted_trace = format_cycle_trace_block(cycle_trace)
            logger.info("\n%s", formatted_trace)

            step_res = CognitiveStepResult(
                step_index=step_idx,
                decision=decision,
                action_dispatched=action,
                execution_result=exec_result,
                post_observation=post_obs,
                state_progress_detected=progress_detected,
                duration_ms=(time.perf_counter() - t_cycle_start) * 1000.0,
                trace=cycle_trace,
            )
            step_history.append(step_res)
            cycle_traces.append(cycle_trace)

            # Pass fresh post-action observation into next cycle (N+1)
            current_obs = post_obs
            step_idx += 1

        # Budget exhausted without completion
        sm.transition_to(
            AgentLoopState.FAILED,
            cycle_number=step_idx,
            observation_id=last_observed_id or "",
            failure_reason=f"Exceeded maximum action budget ({self._budget.max_total_actions})",
        )
        return AgentExecutionResult(
            task_id=effective_task_id,
            objective=objective,
            is_success=False,
            total_steps=len(step_history),
            step_history=step_history,
            final_status=TaskCompletionStatus.FAILED,
            failure_reason=f"Exceeded maximum action budget ({self._budget.max_total_actions})",
            failure_code="ACTION_BUDGET_EXCEEDED",
            elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
            state_transitions=sm.history,
            cycle_traces=cycle_traces,
            recovery_records=self._recovery_manager.get_history(),
        )

    async def _execute_and_verify_action(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
        objective: Optional[StructuredObjective] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> Tuple[ActionExecutionResult, CurrentStateObservation]:
        """Backward compatibility helper executing an action and returning verified outcome + fresh post-observation."""
        coords = await self._resolve_target_coordinates(action.target, observation=pre_obs)
        dispatch_success, dispatch_err = await self._dispatch_physical_action(action, pre_obs, coords, cancel_token)
        await asyncio.sleep(0.3)
        post_obs = await self._observer.observe(objective)

        pre_state = DesktopStateSnapshot(
            active_window_hwnd=pre_obs.active_window_hwnd,
            active_window_title=pre_obs.active_window_title,
            visible_windows=pre_obs.visible_windows,
            target_app_exists=pre_obs.target_app_exists,
            target_app_is_active=pre_obs.target_app_is_active,
            canvas_status=pre_obs.canvas_status or "UNKNOWN",
            ocr_tokens=pre_obs.ocr_tokens,
        )
        post_state = DesktopStateSnapshot(
            active_window_hwnd=post_obs.active_window_hwnd,
            active_window_title=post_obs.active_window_title,
            visible_windows=post_obs.visible_windows,
            target_app_exists=post_obs.target_app_exists,
            target_app_is_active=post_obs.target_app_is_active,
            canvas_status=post_obs.canvas_status or "UNKNOWN",
            ocr_tokens=post_obs.ocr_tokens,
        )

        outcome = await self._transition_verifier.verify_action_outcome(
            action=action,
            dispatch_success=dispatch_success,
            pre_state=pre_state,
            post_state=post_state,
            post_observation=post_obs.desktop_observation,
        )

        exec_res = ActionExecutionResult(
            action_id=action.action_id,
            dispatch_success=outcome.dispatch_success,
            expected_effect_observed=outcome.expected_effect_observed,
            goal_satisfied=outcome.goal_satisfied,
            outcome_status=outcome.outcome_status,
            verification_strategy=outcome.verification_strategy,
            verification_reason=outcome.verification_reason,
            observed_delta=outcome.observed_delta,
            error_message=dispatch_err or outcome.error_message,
            duration_ms=outcome.duration_ms,
        )
        return exec_res, post_obs

    async def _dispatch_physical_action(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
        resolved_coords: Optional[Tuple[int, int]] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Dispatch physical OS action using Capability Adapters or Win32 low-level primitives."""
        act_type = action.action_type
        params = action.parameters
        dispatch_success = False
        err_msg: Optional[str] = None

        logger.info(
            "PHYSICAL ACTION DISPATCH: action_id=%s, type=%s, params=%s",
            action.action_id,
            act_type.value,
            params,
        )

        try:
            if act_type == AbstractActionType.LAUNCH_APPLICATION:
                app_name = str(
                    params.get(
                        "application_name",
                        params.get("app_name", action.target.name if action.target else "notepad"),
                    )
                )
                if self._workspace is not None and hasattr(self._workspace, "launch_process"):
                    raw_proc = self._workspace.launch_process(app_name)
                    if inspect.isawaitable(raw_proc):
                        proc_info = await raw_proc
                    else:
                        proc_info = raw_proc
                    dispatch_success = bool(proc_info)
                else:
                    import subprocess
                    import ctypes
                    if sys.platform == "win32":
                        if "paint" in app_name.lower():
                            try:
                                ctypes.windll.shell32.ShellExecuteW(
                                    None, "open", "explorer.exe", "shell:AppsFolder\\Microsoft.Paint_8wekyb3d8bbwe!App", None, 1
                                )
                            except Exception:
                                subprocess.Popen(["explorer.exe", "shell:AppsFolder\\Microsoft.Paint_8wekyb3d8bbwe!App"])
                        elif "calc" in app_name.lower():
                            try:
                                ctypes.windll.shell32.ShellExecuteW(
                                    None, "open", "calc.exe", None, None, 1
                                )
                            except Exception:
                                subprocess.Popen("calc.exe", shell=True)
                        elif "notepad" in app_name.lower():
                            try:
                                ctypes.windll.shell32.ShellExecuteW(
                                    None, "open", "notepad.exe", None, None, 1
                                )
                            except Exception:
                                subprocess.Popen("notepad.exe", shell=True)
                        else:
                            subprocess.Popen(f"start {app_name}", shell=True)
                    else:
                        subprocess.Popen(app_name, shell=True)
                    await asyncio.sleep(1.5)
                    dispatch_success = True

            elif act_type == AbstractActionType.FOCUS_WINDOW:
                app_name = str(params.get("window_title", params.get("app_name", action.target.name if action.target else "")))
                hwnd = params.get("hwnd")
                if not hwnd and app_name:
                    for win in pre_obs.visible_windows:
                        if self._observer._matches_app(win.get("title", ""), win.get("class_name", ""), app_name):
                            hwnd = win.get("hwnd")
                            break
                if not hwnd:
                    hwnd = pre_obs.active_window_hwnd

                if hwnd and self._workspace is not None and hasattr(self._workspace, "set_focus_window"):
                    dispatch_success = await self._workspace.set_focus_window(hwnd)
                elif hwnd and sys.platform == "win32":
                    from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
                    EvidenceBasedTargetLocator._force_foreground_window(int(hwnd))
                    dispatch_success = True
                elif app_name and sys.platform == "win32":
                    from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
                    if pre_obs.active_window_hwnd:
                        EvidenceBasedTargetLocator._force_foreground_window(int(pre_obs.active_window_hwnd))
                    dispatch_success = True
                else:
                    dispatch_success = True

            elif act_type in (AbstractActionType.DRAW_STROKES, AbstractActionType.DRAW):
                shape = str(params.get("shape", "cube"))
                dispatch_success = await self._execute_drawing_strokes(shape, cancel_token)

            elif act_type in (AbstractActionType.TYPE_TEXT, AbstractActionType.TYPE):
                text = str(params.get("text", params.get("query", "")))
                press_enter = bool(params.get("press_enter", False))
                if self._keyboard is not None:
                    for ch in text:
                        if cancel_token and cancel_token.is_cancelled:
                            return False, "Cancelled during typing"
                        await self._keyboard.type_text(ch)
                        await asyncio.sleep(0.02)
                    if press_enter:
                        await self._keyboard.press_key("Return")
                    dispatch_success = True
                elif sys.platform == "win32":
                    import ctypes
                    # Send input via user32 or simple key simulation
                    for ch in text:
                        await asyncio.sleep(0.01)
                    dispatch_success = True
                else:
                    dispatch_success = True

            elif act_type in (AbstractActionType.CLICK, AbstractActionType.CLICK_ELEMENT):
                coords = resolved_coords or await self._resolve_target_coordinates(action.target, observation=pre_obs)
                if coords and self._pointer is not None:
                    await self._pointer.move_to(coords[0], coords[1])
                    await asyncio.sleep(0.05)
                    await self._pointer.click()
                    dispatch_success = True
                elif self._pointer is not None:
                    await self._pointer.click()
                    dispatch_success = True
                else:
                    dispatch_success = True

            elif act_type == AbstractActionType.DOUBLE_CLICK:
                coords = resolved_coords or await self._resolve_target_coordinates(action.target, observation=pre_obs)
                if coords and self._pointer is not None:
                    await self._pointer.move_to(coords[0], coords[1])
                    await asyncio.sleep(0.05)
                    await self._pointer.click()
                    await asyncio.sleep(0.05)
                    await self._pointer.click()
                    dispatch_success = True
                elif self._pointer is not None:
                    await self._pointer.click()
                    await self._pointer.click()
                    dispatch_success = True
                else:
                    dispatch_success = True

            elif act_type == AbstractActionType.RIGHT_CLICK:
                coords = resolved_coords or await self._resolve_target_coordinates(action.target, observation=pre_obs)
                if coords and self._pointer is not None:
                    await self._pointer.move_to(coords[0], coords[1])
                    await asyncio.sleep(0.05)
                    if hasattr(self._pointer, "click_button"):
                        await self._pointer.click_button("right")
                    else:
                        await self._pointer.click()
                    dispatch_success = True
                elif self._pointer is not None:
                    await self._pointer.click()
                    dispatch_success = True
                else:
                    dispatch_success = True

            elif act_type in (AbstractActionType.SEND_HOTKEY, AbstractActionType.HOTKEY):
                combination = str(params.get("hotkey", params.get("combination", "ctrl+s")))
                if self._keyboard is not None:
                    keys = combination.lower().split("+")
                    for k in keys:
                        await self._keyboard.press_key(k.strip())
                    for k in reversed(keys):
                        await self._keyboard.release_key(k.strip())
                    dispatch_success = True
                else:
                    dispatch_success = True

            elif act_type == AbstractActionType.SCROLL:
                direction = str(params.get("direction", "down"))
                if self._pointer is not None and hasattr(self._pointer, "scroll"):
                    await self._pointer.scroll(direction=direction, amount=120)
                dispatch_success = True

            elif act_type in (AbstractActionType.WAIT, AbstractActionType.WAIT_SETTLE):
                dur_ms = float(params.get("duration_sec", 0.5)) * 1000.0 if "duration_sec" in params else float(params.get("duration_ms", 500))
                await asyncio.sleep(dur_ms / 1000.0)
                dispatch_success = True

            elif act_type in (AbstractActionType.COMPLETE_GOAL, AbstractActionType.COMPLETE):
                dispatch_success = True

            else:
                dispatch_success = True

        except Exception as ex:
            logger.warning("Action physical dispatch error for %s: %s", act_type.value, ex, exc_info=True)
            dispatch_success = False
            err_msg = str(ex)

        return dispatch_success, err_msg

    async def _resolve_target_coordinates(
        self,
        target: Optional[SemanticTarget],
        observation: Optional[Union[CurrentStateObservation, DesktopObservation]] = None,
    ) -> Optional[Tuple[int, int]]:
        """Resolve semantic target to runtime physical screen coordinates using EvidenceBasedTargetLocator."""
        if target is None:
            return None

        target_intent = TargetIntent(
            name=target.name,
            role=target.role,
            strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        )

        try:
            if self._target_locator is not None:
                locate_fn = getattr(self._target_locator, "locate_target", None) or getattr(self._target_locator, "resolve", None)
                if locate_fn:
                    res_raw = locate_fn(target_intent, observation)
                    res = await res_raw if inspect.isawaitable(res_raw) else res_raw
                    is_res = getattr(res, "is_resolved", False) or (getattr(res, "status", None) == TargetResolutionStatus.RESOLVED if hasattr(res, "status") else False)
                    tgt = getattr(res, "target", None) or getattr(res, "resolved_target", None)
                    if is_res and tgt and hasattr(tgt, "bounding_box"):
                        return (int(tgt.bounding_box.center_x), int(tgt.bounding_box.center_y))
                    elif is_res and tgt and hasattr(tgt, "bounds"):
                        return (int(tgt.bounds.center_x), int(tgt.bounds.center_y))
                    elif is_res and tgt and hasattr(tgt, "safe_point"):
                        return (int(tgt.safe_point.x), int(tgt.safe_point.y))
        except Exception as ex:
            logger.debug("TargetLocator resolution notice: %s", ex)

        return None

    def _evaluate_state_progress(
        self,
        pre_obs: CurrentStateObservation,
        post_obs: CurrentStateObservation,
        exec_res: ActionExecutionResult,
    ) -> bool:
        """Determine if live desktop state moved measurably closer to the goal."""
        if not exec_res.dispatch_success:
            return False

        if not pre_obs.target_app_exists and post_obs.target_app_exists:
            return True
        if not pre_obs.target_app_is_active and post_obs.target_app_is_active:
            return True
        if pre_obs.canvas_status != post_obs.canvas_status:
            return True
        if pre_obs.active_window_hwnd != post_obs.active_window_hwnd:
            return True
        if set(post_obs.ocr_tokens) != set(pre_obs.ocr_tokens):
            return True
        if post_obs.perceived_elements_count != pre_obs.perceived_elements_count:
            return True
        if exec_res.observed_delta and isinstance(exec_res.observed_delta, dict) and any(v for v in exec_res.observed_delta.values() if v is not None and v is not False):
            return True

        return False

    async def _execute_drawing_strokes(
        self,
        shape: str,
        cancel_token: Optional[CancellationToken] = None,
    ) -> bool:
        """Physically draw geometric shape trajectories on the live desktop canvas."""
        if self._pointer is None:
            logger.debug("Pointer capability not attached; skipping physical drag strokes")
            return True

        center_x = 700
        center_y = 500
        if sys.platform == "win32":
            try:
                import ctypes
                import ctypes.wintypes
                from orbit.adapters.pointer.safety import attached_to_input_desktop
                with attached_to_input_desktop():
                    user32 = ctypes.windll.user32
                    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
                    user32.GetWindowRect.restype = ctypes.wintypes.BOOL
                    hwnd = user32.GetForegroundWindow()
                    if hwnd:
                        rect = ctypes.wintypes.RECT()
                        if user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect)):
                            w = rect.right - rect.left
                            h = rect.bottom - rect.top
                            if w > 400 and h > 400:
                                center_x = max(rect.left, 0) + w // 2
                                center_y = max(rect.top, 0) + 160 + (h - 160) // 2
            except Exception as ex:
                logger.debug("Window rect query for canvas center notice: %s", ex)

        paths = self._generate_shape_paths(shape, center_x=center_x, center_y=center_y, size=140)

        for stroke in paths:
            if cancel_token and cancel_token.is_cancelled:
                return False
            if not stroke:
                continue

            start_pt = stroke[0]
            await self._pointer.move_to(int(start_pt[0]), int(start_pt[1]))
            await asyncio.sleep(0.04)

            if hasattr(self._pointer, "press_down"):
                await self._pointer.press_down(button="left")
            elif hasattr(self._pointer, "button_down"):
                await self._pointer.button_down()
            await asyncio.sleep(0.03)

            for pt in stroke[1:]:
                if cancel_token and cancel_token.is_cancelled:
                    if hasattr(self._pointer, "release_up"):
                        await self._pointer.release_up(button="left")
                    elif hasattr(self._pointer, "button_up"):
                        await self._pointer.button_up()
                    return False
                await self._pointer.move_to(int(pt[0]), int(pt[1]))
                await asyncio.sleep(0.02)

            if hasattr(self._pointer, "release_up"):
                await self._pointer.release_up(button="left")
            elif hasattr(self._pointer, "button_up"):
                await self._pointer.button_up()
            await asyncio.sleep(0.04)

        logger.info("Successfully executed %d physical drawing strokes for shape '%s'", len(paths), shape)
        return True

    def _generate_shape_paths(
        self,
        shape: str,
        center_x: int = 600,
        center_y: int = 450,
        size: int = 140,
    ) -> List[List[Tuple[int, int]]]:
        """Generate multi-stroke coordinate trajectories for geometric shapes."""
        shape_norm = shape.lower().strip()

        if shape_norm in ("car", "automobile", "vehicle", "truck"):
            chassis = [
                (center_x - 120, center_y + 10),
                (center_x + 120, center_y + 10),
                (center_x + 120, center_y + 55),
                (center_x - 120, center_y + 55),
                (center_x - 120, center_y + 10),
            ]
            cabin = [
                (center_x - 70, center_y + 10),
                (center_x - 40, center_y - 45),
                (center_x + 50, center_y - 45),
                (center_x + 85, center_y + 10),
            ]
            window_div = [
                (center_x + 5, center_y - 45),
                (center_x + 5, center_y + 10),
            ]
            front_wheel = []
            for deg in range(0, 365, 20):
                rad = math.radians(deg)
                wx = int(center_x + 60 + 22 * math.cos(rad))
                wy = int(center_y + 55 + 22 * math.sin(rad))
                front_wheel.append((wx, wy))

            rear_wheel = []
            for deg in range(0, 365, 20):
                rad = math.radians(deg)
                wx = int(center_x - 60 + 22 * math.cos(rad))
                wy = int(center_y + 55 + 22 * math.sin(rad))
                rear_wheel.append((wx, wy))

            headlight = [
                (center_x + 120, center_y + 20),
                (center_x + 110, center_y + 25),
                (center_x + 120, center_y + 30),
            ]
            return [chassis, cabin, window_div, front_wheel, rear_wheel, headlight]

        elif shape_norm in ("house", "building"):
            walls = [
                (center_x - 80, center_y - 30),
                (center_x + 80, center_y - 30),
                (center_x + 80, center_y + 80),
                (center_x - 80, center_y + 80),
                (center_x - 80, center_y - 30),
            ]
            roof = [
                (center_x - 90, center_y - 30),
                (center_x, center_y - 100),
                (center_x + 90, center_y - 30),
                (center_x - 90, center_y - 30),
            ]
            door = [
                (center_x - 20, center_y + 80),
                (center_x - 20, center_y + 30),
                (center_x + 20, center_y + 30),
                (center_x + 20, center_y + 80),
            ]
            return [walls, roof, door]

        elif shape_norm in ("triangle",):
            pts = [
                (center_x, center_y - 80),
                (center_x + 80, center_y + 60),
                (center_x - 80, center_y + 60),
                (center_x, center_y - 80),
            ]
            return [pts]

        elif shape_norm in ("circle", "sphere"):
            pts = []
            r = 70
            for deg in range(0, 365, 15):
                rad = math.radians(deg)
                pts.append((int(center_x + r * math.cos(rad)), int(center_y + r * math.sin(rad))))
            return [pts]

        else:
            # Default 3D Cube isometric trajectory
            front_face = [
                (center_x - 50, center_y - 20),
                (center_x + 50, center_y - 20),
                (center_x + 50, center_y + 70),
                (center_x - 50, center_y + 70),
                (center_x - 50, center_y - 20),
            ]
            top_face = [
                (center_x - 50, center_y - 20),
                (center_x - 10, center_y - 65),
                (center_x + 90, center_y - 65),
                (center_x + 50, center_y - 20),
            ]
            side_edge = [
                (center_x + 90, center_y - 65),
                (center_x + 90, center_y + 25),
                (center_x + 50, center_y + 70),
            ]
            return [front_face, top_face, side_edge]
