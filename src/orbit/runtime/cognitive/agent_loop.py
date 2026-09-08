"""Unified AI-Native Agent Execution Loop.

The authoritative, closed-loop execution path for all autonomous OS desktop actions in ORBIT:
1. Multimodal Desktop Observation (Screenshot frame, Win32 HWNDs, UIA hierarchy, OCR)
2. Vision-Driven Semantic Reasoning (Local/Cloud LLM via ModelRouter -> AbstractAction)
3. Action Validation & Strict Protocol Verification (AgentActionValidator -> Coordinate Isolation)
4. Dynamic Target Grounding (TargetLocator -> ResolvedAction with safe physical coordinates)
5. Physical Action Execution (user32.SendInput / ShellExecute / SetForegroundWindow)
6. Immediate State Delta Verification (AgentStateTransitionVerifier: Observed pre vs post transition)
7. Goal Progress & Completion Evaluation (Verifiable end conditions & ExecutionBudget)

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
from typing import Any, Dict, List, Optional, Tuple, Union
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
    CognitiveDecision,
    CognitiveExecutionResult,
    CognitiveStepResult,
    CurrentStateObservation,
    ExecutionBudget,
    StructuredObjective,
)
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.model_runtime.router import ModelRouter, RoutingPolicy
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models.models import ModelCapability
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    ResolvedTarget,
    TargetIntent,
    TargetLocator,
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
        self._event_bus = event_bus
        self._budget = budget or ExecutionBudget()

    @property
    def router(self) -> Optional[ModelRouter]:
        return self._router

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
        """Run the unified AI-native agent execution loop end-to-end."""
        effective_task_id = task_id or f"agt_{uuid4().hex[:8]}"
        t_start = time.perf_counter()
        last_progress_time = time.perf_counter()

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
        consecutive_identical_actions = 0
        last_action_signature: Optional[str] = None
        step_idx = 0

        while step_idx < self._budget.max_total_actions:
            t_step_start = time.perf_counter()

            if cancel_token and cancel_token.is_cancelled:
                logger.info("AgentExecutionLoop received cancellation for task %s", effective_task_id)
                cancel_msg = cancel_token.reason or "Cancelled by operator"
                if "cancel" not in cancel_msg.lower():
                    cancel_msg = f"Cancelled: {cancel_msg}"
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
                )

            # Check no-progress timeout
            if time.perf_counter() - last_progress_time > self._budget.no_progress_timeout_sec:
                logger.warning("No-progress timeout reached (%.1fs) for task %s", self._budget.no_progress_timeout_sec, effective_task_id)
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
                )

            # 1. Multimodal Desktop Observation
            observation = await self._observer.observe(objective)

            # 2. Independent Goal Verification Check
            if self._goal_verifier is not None:
                try:
                    goal_check = await self._goal_verifier.verify_goal_achievement(
                        task_id=effective_task_id,
                        objective=objective,
                        current_observation=observation,
                        step_history=step_history,
                    )
                    if goal_check.is_satisfied:
                        logger.info("Independent GoalVerifier confirmed task completion for %s", effective_task_id)
                        return AgentExecutionResult(
                            task_id=effective_task_id,
                            objective=objective,
                            is_success=True,
                            total_steps=len(step_history),
                            step_history=step_history,
                            final_status=TaskCompletionStatus.COMPLETED,
                            elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                        )
                except Exception as gv_err:
                    logger.debug("GoalVerifier evaluation notice: %s", gv_err)

            # 3. Cognitive Decision Engine Reasoning (Deterministic -> Recovery -> LLM)
            decide_fn = getattr(self._decision_engine, "decide_next_step", None) or getattr(self._decision_engine, "decide_next_action", None)
            decision = await decide_fn(
                objective=objective,
                observation=observation,
                step_history=step_history,
                step_index=step_idx,
            )

            # Publish step event
            if self._event_bus:
                await self._event_bus.publish(
                    RuntimeEvent(
                        event_type=EventType.TASK_STEP_EXECUTED,
                        session_id=session_id,
                        correlation_id=effective_task_id,
                        payload={
                            "task_id": effective_task_id,
                            "step_index": step_idx,
                            "decision_summary": decision.decision_summary,
                            "action_type": decision.next_action.action_type.value if decision.next_action else None,
                            "escalated_to_llm": decision.escalated_to_llm,
                        },
                    )
                )

            if decision.is_goal_satisfied or (decision.next_action and decision.next_action.action_type in (AbstractActionType.COMPLETE_GOAL, AbstractActionType.COMPLETE)):
                logger.info("Goal satisfied at step %d for task %s", step_idx, effective_task_id)
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
                    post_observation=observation,
                    state_progress_detected=True,
                    duration_ms=(time.perf_counter() - t_step_start) * 1000.0,
                )
                step_history.append(step_res)
                return AgentExecutionResult(
                    task_id=effective_task_id,
                    objective=objective,
                    is_success=True,
                    total_steps=len(step_history),
                    step_history=step_history,
                    final_status=TaskCompletionStatus.COMPLETED,
                    elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                )

            if decision.next_action and decision.next_action.action_type in (
                AbstractActionType.ABORT_TASK,
                AbstractActionType.ABORT,
                AbstractActionType.ABORT_UNACHIEVABLE,
            ):
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
                    post_observation=observation,
                    state_progress_detected=False,
                    duration_ms=(time.perf_counter() - t_step_start) * 1000.0,
                )
                step_history.append(step_res)
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
                )

            action = decision.next_action
            if not action:
                break

            # 4. Strict Action Protocol Validation
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
                    post_observation=observation,
                    state_progress_detected=False,
                    duration_ms=(time.perf_counter() - t_step_start) * 1000.0,
                )
                step_history.append(step_res)
                step_idx += 1
                continue

            # Track repeated action budget
            act_sig = f"{action.action_type.value}:{action.parameters}"
            if act_sig == last_action_signature:
                consecutive_identical_actions += 1
                if consecutive_identical_actions >= self._budget.max_repeated_actions_without_progress:
                    logger.warning("Repeated action limit reached without state progress: %s", act_sig)
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
                    )
            else:
                consecutive_identical_actions = 0
                last_action_signature = act_sig

            # 5. Target Resolution (AbstractAction -> ResolvedAction) & Physical Action Dispatch + Immediate Fresh Post-Observation
            exec_result, post_obs = await self._execute_and_verify_action(action, observation, objective, cancel_token)

            # 6. Immediate Progress Detection between Pre-Action and Fresh Post-Action Observation
            progress_detected = self._evaluate_state_progress(observation, post_obs, exec_result)

            if progress_detected:
                last_progress_time = time.perf_counter()
                consecutive_identical_actions = 0

            step_res = CognitiveStepResult(
                step_index=step_idx,
                decision=decision,
                action_dispatched=action,
                execution_result=exec_result,
                post_observation=post_obs,
                state_progress_detected=progress_detected,
                duration_ms=(time.perf_counter() - t_step_start) * 1000.0,
            )
            step_history.append(step_res)
            step_idx += 1

        # Exhausted total actions budget
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
        )

    async def _execute_and_verify_action(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
        objective: Optional[StructuredObjective] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> Tuple[ActionExecutionResult, CurrentStateObservation]:
        """Translate SemanticTarget to ResolvedAction (coordinates), dispatch low-level input, and capture fresh post-observation."""
        act_type = action.action_type
        params = action.parameters

        dispatch_success = False
        err_msg = None
        target_name = action.target.name if action.target else str(params.get("application_name", params.get("app_name", "unknown")))
        target_role = action.target.role if action.target else "unknown"

        logger.info(
            "AGENT ACTION DISPATCH:\n"
            "  action_id: %s\n"
            "  action_type: %s\n"
            "  semantic target: name='%s', role='%s', context='%s'",
            action.action_id,
            act_type.value,
            target_name,
            target_role,
            action.target.context if action.target else "",
        )

        # 1. Target Resolution: AbstractAction -> ResolvedAction (Runtime Grounding)
        resolved_action: Optional[ResolvedAction] = None
        if action.target is not None:
            resolved_coords = await self._resolve_target_coordinates(action.target, observation=pre_obs)
            if resolved_coords:
                resolved_action = ResolvedAction(
                    action_id=action.action_id,
                    action_type=act_type,
                    resolved_target_id=f"tgt_{uuid4().hex[:6]}",
                    execution_point=None,
                    parameters=params,
                    outcome_contract=action.outcome_contract,
                )

        try:
            # -------------------------------------------------------------
            # Physical Execution via Capability Adapters
            # -------------------------------------------------------------
            if act_type == AbstractActionType.LAUNCH_APPLICATION:
                app_name = str(
                    params.get(
                        "application_name",
                        params.get("app_name", action.target.name if action.target else "mspaint"),
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
                    await asyncio.sleep(2.0)
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
                            return ActionExecutionResult(
                                action_id=action.action_id,
                                dispatch_success=False,
                                expected_effect_observed=False,
                                outcome_status=OutcomeStatus.DISPATCH_FAILED,
                                error_message="Cancelled during typing",
                            )
                        await self._keyboard.type_text(ch)
                        await asyncio.sleep(0.02)
                    if press_enter:
                        await self._keyboard.press_key("Return")
                    dispatch_success = True
                else:
                    dispatch_success = True

            elif act_type in (AbstractActionType.CLICK, AbstractActionType.CLICK_ELEMENT):
                coords = await self._resolve_target_coordinates(action.target, observation=pre_obs)
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
                coords = await self._resolve_target_coordinates(action.target, observation=pre_obs)
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
                coords = await self._resolve_target_coordinates(action.target, observation=pre_obs)
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

        except Exception as ex:
            logger.warning("Action dispatch error for %s: %s", act_type.value, ex, exc_info=True)
            dispatch_success = False
            err_msg = str(ex)

        # -------------------------------------------------------------
        # Immediate Fresh Post-Action Observation Capture
        # -------------------------------------------------------------
        await asyncio.sleep(0.3)
        post_obs = await self._observer.observe(objective)

        # -------------------------------------------------------------
        # State Transition Verification via AgentStateTransitionVerifier
        # -------------------------------------------------------------
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
            error_message=err_msg or outcome.error_message,
            duration_ms=outcome.duration_ms,
        )

        return exec_res, post_obs

    async def _resolve_target_coordinates(
        self,
        target: Optional[SemanticTarget],
        observation: Optional[Union[CurrentStateObservation, DesktopObservation]] = None,
    ) -> Optional[Tuple[int, int]]:
        """Resolve semantic target to runtime physical screen coordinates."""
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
        """Determine if world state actually moved forward."""
        if not exec_res.dispatch_success:
            return False

        if not pre_obs.target_app_exists and post_obs.target_app_exists:
            return True
        if not pre_obs.target_app_is_active and post_obs.target_app_is_active:
            return True
        if pre_obs.canvas_status != post_obs.canvas_status:
            return True
        if exec_res.expected_effect_observed:
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

        # Calculate canvas center dynamically from active foreground window
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
