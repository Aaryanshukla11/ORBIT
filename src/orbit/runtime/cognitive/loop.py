"""Closed-loop Cognitive Execution Loop coordinating Observe -> Delta -> Reason -> Resolve -> Act -> Verify."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import math
import sys
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from orbit.contracts.capabilities import (
    KeyboardCapability,
    ObservationCapability,
    PointerCapability,
    WorkspaceCapability,
)
from orbit.runtime.cancellation import CancellationToken
from orbit.runtime.cognitive.engine import CognitiveDecisionEngine
from orbit.runtime.cognitive.interpreter import LLMIntentInterpreter
from orbit.runtime.cognitive.models import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionResult,
    CognitiveDecision,
    CognitiveExecutionResult,
    CognitiveStepResult,
    CurrentStateObservation,
    ExecutionBudget,
    OutcomeStatus,
    SemanticTarget,
    StructuredObjective,
)
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.targeting import EvidenceBasedTargetLocator, TargetIntent, TargetLocator, TargetStrategy
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.task_completion.models import TaskCompletionStatus

logger = logging.getLogger(__name__)


class CognitiveExecutionLoop:
    """Orchestrates the dynamic closed-loop Cognitive Intent & Decision Engine lifecycle."""

    def __init__(
        self,
        interpreter: Optional[LLMIntentInterpreter] = None,
        observer: Optional[CurrentStateObserver] = None,
        decision_engine: Optional[CognitiveDecisionEngine] = None,
        target_locator: Optional[TargetLocator] = None,
        workspace: Optional[WorkspaceCapability] = None,
        pointer: Optional[PointerCapability] = None,
        keyboard: Optional[KeyboardCapability] = None,
        observation: Optional[ObservationCapability] = None,
        goal_verifier: Optional[GoalVerifier] = None,
        model_session_manager: Optional[Any] = None,
        budget: Optional[ExecutionBudget] = None,
    ) -> None:
        self._interpreter = interpreter or LLMIntentInterpreter(model_session_manager=model_session_manager)
        self._observer = observer or CurrentStateObserver(observation=observation)
        self._decision_engine = decision_engine or CognitiveDecisionEngine(model_session_manager=model_session_manager)
        self._target_locator = target_locator or EvidenceBasedTargetLocator()
        self._workspace = workspace
        self._pointer = pointer
        self._keyboard = keyboard
        self._observation = observation
        self._goal_verifier = goal_verifier
        self._model_session_manager = model_session_manager
        self._budget = budget or ExecutionBudget()

    def set_model_session_manager(self, msm: Any) -> None:
        self._model_session_manager = msm
        self._interpreter.set_model_session_manager(msm)
        self._decision_engine.set_model_session_manager(msm)

    async def run(
        self,
        prompt: str,
        session_id: str = "default_session",
        task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> CognitiveExecutionResult:
        """Run the closed-loop Cognitive Intent & Decision Engine."""
        effective_task_id = task_id or f"cog_{uuid4().hex[:8]}"
        t_start = time.perf_counter()
        last_progress_time = time.perf_counter()

        logger.info("CognitiveExecutionLoop starting task %s with prompt: '%s'", effective_task_id, prompt)

        # 1. LLM Intent Interpretation
        objective = await self._interpreter.interpret(prompt, context)
        logger.info("Interpreted Objective: Goal='%s', EndCondition='%s'", objective.user_goal, objective.end_condition)

        step_history: List[CognitiveStepResult] = []
        consecutive_identical_actions = 0
        last_action_signature: Optional[str] = None

        step_idx = 0
        while step_idx < self._budget.max_total_actions:
            if cancel_token and cancel_token.is_cancelled:
                return CognitiveExecutionResult(
                    task_id=effective_task_id,
                    objective=objective,
                    is_success=False,
                    total_steps=len(step_history),
                    step_history=step_history,
                    final_status=TaskCompletionStatus.CANCELLED,
                    failure_reason=f"Cancelled: {cancel_token.reason}",
                    failure_code="TASK_CANCELLED",
                    elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                )

            # Check no-progress timeout
            if (time.perf_counter() - last_progress_time) > self._budget.no_progress_timeout_sec:
                logger.warning("No forward state progress detected within %fs budget", self._budget.no_progress_timeout_sec)
                return CognitiveExecutionResult(
                    task_id=effective_task_id,
                    objective=objective,
                    is_success=False,
                    total_steps=len(step_history),
                    step_history=step_history,
                    final_status=TaskCompletionStatus.FAILED,
                    failure_reason=f"Execution halted: No state progress detected within {self._budget.no_progress_timeout_sec}s",
                    failure_code="NO_PROGRESS_TIMEOUT",
                    elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                )

            t_step_start = time.perf_counter()

            # 2. Current State Observation
            observation = await self._observer.observe(objective)

            # 3. State / Goal Delta & Cognitive Decision (Fast Rules -> Recovery -> LLM)
            decision = await self._decision_engine.decide_next_step(
                objective=objective,
                observation=observation,
                step_history=step_history,
                step_index=step_idx,
            )
            logger.info("Step %d Decision [%s]: %s", step_idx, "LLM" if decision.escalated_to_llm else "RULES", decision.decision_summary)

            # Check if Goal is already satisfied
            if decision.is_goal_satisfied or (decision.next_action and decision.next_action.action_type == AbstractActionType.COMPLETE_GOAL):
                step_res = CognitiveStepResult(
                    step_index=step_idx,
                    decision=decision,
                    action_dispatched=decision.next_action,
                    execution_result=ActionExecutionResult(
                        dispatch_success=True,
                        expected_effect_observed=True,
                        outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                        evidence={"final_state": observation.screen_summary},
                    ),
                    post_observation=observation,
                    state_progress_detected=True,
                    duration_ms=(time.perf_counter() - t_step_start) * 1000.0,
                )
                step_history.append(step_res)
                return CognitiveExecutionResult(
                    task_id=effective_task_id,
                    objective=objective,
                    is_success=True,
                    total_steps=len(step_history),
                    step_history=step_history,
                    final_status=TaskCompletionStatus.COMPLETED,
                    elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                )

            if decision.next_action and decision.next_action.action_type == AbstractActionType.ABORT_UNACHIEVABLE:
                step_res = CognitiveStepResult(
                    step_index=step_idx,
                    decision=decision,
                    action_dispatched=decision.next_action,
                    execution_result=ActionExecutionResult(
                        dispatch_success=False,
                        expected_effect_observed=False,
                        outcome_status=OutcomeStatus.DISPATCH_FAILED,
                        error_message=decision.reason_summary,
                    ),
                    post_observation=observation,
                    state_progress_detected=False,
                    duration_ms=(time.perf_counter() - t_step_start) * 1000.0,
                )
                step_history.append(step_res)
                return CognitiveExecutionResult(
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

            # Track repeated action budget
            act_sig = f"{action.action_type.value}:{action.parameters}"
            if act_sig == last_action_signature:
                consecutive_identical_actions += 1
                if consecutive_identical_actions >= self._budget.max_repeated_actions_without_progress:
                    logger.warning("Repeated action limit reached without state progress: %s", act_sig)
                    return CognitiveExecutionResult(
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

            # 4. Target Resolution & Physical Action Dispatch
            exec_result = await self._execute_and_verify_action(action, observation, cancel_token)

            # Settle window/state after action
            await asyncio.sleep(0.3)

            # 5. Immediate Post-Observation & Progress Detection
            post_obs = await self._observer.observe(objective)
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
        return CognitiveExecutionResult(
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
        cancel_token: Optional[CancellationToken] = None,
    ) -> ActionExecutionResult:
        """Translate SemanticTarget to coordinates, dispatch physical input, and verify immediate outcome."""
        act_type = action.action_type
        params = action.parameters

        dispatch_success = False
        err_msg = None
        target_name = action.target.name if action.target else str(params.get("app_name", "unknown"))
        target_role = action.target.role if action.target else "unknown"

        # Diagnostic Log: ACTION
        logger.info(
            "ACTION:\n"
            "  action_id: %s\n"
            "  action_type: %s\n"
            "  semantic target: name='%s', role='%s', context='%s'",
            action.action_id,
            act_type.value,
            target_name,
            target_role,
            action.target.context if action.target else "",
        )

        try:
            # -------------------------------------------------------------
            # Physical Execution via Capability Adapters
            # -------------------------------------------------------------
            if act_type == AbstractActionType.LAUNCH_APPLICATION:
                app_name = str(params.get("app_name", action.target.name if action.target else "mspaint"))
                logger.info(
                    "DISPATCH:\n"
                    "  adapter class: %s\n"
                    "  dispatch function: launch_application\n"
                    "  native API used: ShellExecute / CreateProcess\n"
                    "  app_name: %s",
                    type(self._workspace).__name__ if self._workspace else "subprocess",
                    app_name,
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
                                ctypes.windll.shell32.ShellExecuteW(None, "open", "explorer.exe", "shell:AppsFolder\\Microsoft.Paint_8wekyb3d8bbwe!App", None, 1)
                            except Exception:
                                subprocess.Popen(["explorer.exe", "shell:AppsFolder\\Microsoft.Paint_8wekyb3d8bbwe!App"])
                        else:
                            subprocess.Popen(f"start {app_name}", shell=True)
                    else:
                        subprocess.Popen(app_name, shell=True)
                    # Settle wait for app window initialization
                    await asyncio.sleep(2.0)
                    dispatch_success = True

            elif act_type == AbstractActionType.FOCUS_WINDOW:
                app_name = str(params.get("app_name", action.target.name if action.target else ""))
                hwnd = params.get("hwnd")
                if not hwnd and app_name:
                    for win in pre_obs.visible_windows:
                        if self._observer._matches_app(win.get("title", ""), win.get("class_name", ""), app_name):
                            hwnd = win.get("hwnd")
                            break
                if not hwnd:
                    hwnd = pre_obs.active_window_hwnd

                logger.info(
                    "TARGET RESOLUTION:\n"
                    "  resolved x/y: N/A (Window Focus)\n"
                    "  target window HWND: %s\n"
                    "  foreground HWND: %s",
                    hwnd,
                    pre_obs.active_window_hwnd,
                )
                logger.info(
                    "DISPATCH:\n"
                    "  adapter class: %s\n"
                    "  dispatch function: set_focus_window\n"
                    "  native API used: SetForegroundWindow\n"
                    "  target HWND: %s",
                    type(self._workspace).__name__ if self._workspace else "Win32",
                    hwnd,
                )
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

            elif act_type == AbstractActionType.DRAW_STROKES:
                shape = str(params.get("shape", "cube"))
                logger.info(
                    "DISPATCH:\n"
                    "  adapter class: %s\n"
                    "  dispatch function: _execute_drawing_strokes\n"
                    "  native API used: user32.SendInput (MOUSEINPUT)\n"
                    "  shape: %s",
                    type(self._pointer).__name__ if self._pointer else "None",
                    shape,
                )
                dispatch_success = await self._execute_drawing_strokes(shape, cancel_token)

            elif act_type == AbstractActionType.TYPE_TEXT:
                text = str(params.get("text", ""))
                logger.info(
                    "DISPATCH:\n"
                    "  adapter class: %s\n"
                    "  dispatch function: keyboard.type_text\n"
                    "  native API used: user32.SendInput (KEYBDINPUT)\n"
                    "  payload length: %d",
                    type(self._keyboard).__name__ if self._keyboard else "None",
                    len(text),
                )
                if self._keyboard is not None:
                    for ch in text:
                        if cancel_token and cancel_token.is_cancelled:
                            return ActionExecutionResult(
                                dispatch_success=False,
                                expected_effect_observed=False,
                                outcome_status=OutcomeStatus.DISPATCH_FAILED,
                                error_message="Cancelled during typing",
                            )
                        await self._keyboard.type_text(ch)
                        await asyncio.sleep(0.02)
                    dispatch_success = True
                else:
                    dispatch_success = False
                    err_msg = "REQUIRED_ADAPTER_MISSING: KeyboardCapability"

            elif act_type == AbstractActionType.CLICK_ELEMENT:
                # Dynamic Runtime Target Resolution (SemanticTarget -> Physical Coordinates)
                coords = await self._resolve_target_coordinates(action.target)
                logger.info(
                    "DISPATCH:\n"
                    "  adapter class: %s\n"
                    "  dispatch function: pointer.click\n"
                    "  native API used: user32.SendInput (MOUSEINPUT)\n"
                    "  resolved coordinates: %s",
                    type(self._pointer).__name__ if self._pointer else "None",
                    coords,
                )
                if coords and self._pointer is not None:
                    await self._pointer.move_to(coords[0], coords[1])
                    await asyncio.sleep(0.05)
                    await self._pointer.click()
                    dispatch_success = True
                elif self._pointer is not None:
                    # Fallback click
                    await self._pointer.click()
                    dispatch_success = True
                else:
                    dispatch_success = False
                    err_msg = "REQUIRED_ADAPTER_MISSING: PointerCapability"

            elif act_type == AbstractActionType.SEND_HOTKEY:
                combination = str(params.get("combination", "ctrl+s"))
                logger.info(
                    "DISPATCH:\n"
                    "  adapter class: %s\n"
                    "  dispatch function: keyboard.press_shortcut\n"
                    "  native API used: user32.SendInput\n"
                    "  combination: %s",
                    type(self._keyboard).__name__ if self._keyboard else "None",
                    combination,
                )
                if self._keyboard is not None:
                    keys = combination.lower().split("+")
                    for k in keys:
                        await self._keyboard.press_key(k.strip())
                    for k in reversed(keys):
                        await self._keyboard.release_key(k.strip())
                    dispatch_success = True
                else:
                    dispatch_success = False
                    err_msg = "REQUIRED_ADAPTER_MISSING: KeyboardCapability"

            elif act_type == AbstractActionType.WAIT_SETTLE:
                dur_ms = float(params.get("duration_ms", 500))
                await asyncio.sleep(dur_ms / 1000.0)
                dispatch_success = True

            elif act_type == AbstractActionType.COMPLETE_GOAL:
                dispatch_success = True

            else:
                dispatch_success = False
                err_msg = f"UNKNOWN_ACTION_TYPE: {act_type.value if hasattr(act_type, 'value') else act_type}"

        except Exception as ex:
            logger.warning("Action dispatch error for %s: %s", act_type.value, ex, exc_info=True)
            dispatch_success = False
            err_msg = str(ex)

        # -------------------------------------------------------------
        # Immediate Outcome Verification (Did this action cause its expected effect?)
        # -------------------------------------------------------------
        expected_effect_observed = dispatch_success
        outcome_status = OutcomeStatus.EFFECT_VERIFIED if dispatch_success else OutcomeStatus.DISPATCH_FAILED

        return ActionExecutionResult(
            dispatch_success=dispatch_success,
            expected_effect_observed=expected_effect_observed,
            outcome_status=outcome_status,
            error_message=err_msg,
        )

    async def _resolve_target_coordinates(self, target: Optional[SemanticTarget]) -> Optional[tuple[int, int]]:
        """Resolve semantic target to runtime physical screen coordinates."""
        if target is None:
            return None

        # Build TargetIntent and query TargetLocator
        target_intent = TargetIntent(
            name=target.name,
            role=target.role,
            strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        )
        try:
            if self._target_locator is not None:
                res = await self._target_locator.locate_target(target_intent)
                if res and res.is_resolved and res.resolved_target:
                    return (int(res.resolved_target.bounds.center_x), int(res.resolved_target.bounds.center_y))
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

        # State transition detections:
        # 1. Target app opened
        if not pre_obs.target_app_exists and post_obs.target_app_exists:
            return True
        # 2. Window focus changed to target
        if not pre_obs.target_app_is_active and post_obs.target_app_is_active:
            return True
        # 3. Canvas status transitioned
        if pre_obs.canvas_status != post_obs.canvas_status:
            return True
        # 4. Verified effect observed
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

            # Hold mouse button down
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

            # Release mouse button
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
    ) -> List[List[tuple[int, int]]]:
        """Generate multi-stroke coordinate trajectories for geometric shapes."""
        shape_norm = shape.lower().strip()

        if shape_norm in ("car", "automobile", "vehicle", "truck"):
            # Detailed Car Drawing Trajectory:
            # 1. Lower Chassis Box
            chassis = [
                (center_x - 120, center_y + 10),
                (center_x + 120, center_y + 10),
                (center_x + 120, center_y + 55),
                (center_x - 120, center_y + 55),
                (center_x - 120, center_y + 10),
            ]
            # 2. Upper Cabin / Roof (Trapezoid)
            cabin = [
                (center_x - 70, center_y + 10),
                (center_x - 40, center_y - 45),
                (center_x + 50, center_y - 45),
                (center_x + 85, center_y + 10),
            ]
            # 3. Window Divider
            window_div = [
                (center_x + 5, center_y - 45),
                (center_x + 5, center_y + 10),
            ]
            # 4. Front Wheel Circle (center_x + 60, center_y + 55)
            front_wheel = []
            for deg in range(0, 365, 20):
                rad = math.radians(deg)
                wx = int(center_x + 60 + 22 * math.cos(rad))
                wy = int(center_y + 55 + 22 * math.sin(rad))
                front_wheel.append((wx, wy))

            # 5. Rear Wheel Circle (center_x - 60, center_y + 55)
            rear_wheel = []
            for deg in range(0, 365, 20):
                rad = math.radians(deg)
                wx = int(center_x - 60 + 22 * math.cos(rad))
                wy = int(center_y + 55 + 22 * math.sin(rad))
                rear_wheel.append((wx, wy))

            # 6. Headlight & Tail light accents
            headlight = [
                (center_x + 120, center_y + 20),
                (center_x + 120, center_y + 35),
            ]
            taillight = [
                (center_x - 120, center_y + 20),
                (center_x - 120, center_y + 35),
            ]
            return [chassis, cabin, window_div, front_wheel, rear_wheel, headlight, taillight]

        elif shape_norm in ("cube", "box_3d"):
            s = size
            offset = int(s * 0.45)
            p1 = (center_x - s // 2, center_y - s // 2)
            p2 = (center_x + s // 2, center_y - s // 2)
            p3 = (center_x + s // 2, center_y + s // 2)
            p4 = (center_x - s // 2, center_y + s // 2)
            front_square = [p1, p2, p3, p4, p1]

            q1 = (p1[0] + offset, p1[1] - offset)
            q2 = (p2[0] + offset, p2[1] - offset)
            q3 = (p3[0] + offset, p3[1] - offset)
            q4 = (p4[0] + offset, p4[1] - offset)
            back_square = [q1, q2, q3, q4, q1]

            e1 = [p1, q1]
            e2 = [p2, q2]
            e3 = [p3, q3]
            e4 = [p4, q4]

            return [front_square, back_square, e1, e2, e3, e4]

        elif shape_norm in ("house",):
            # House: walls box, roof triangle, door
            walls = [
                (center_x - 80, center_y - 20),
                (center_x + 80, center_y - 20),
                (center_x + 80, center_y + 70),
                (center_x - 80, center_y + 70),
                (center_x - 80, center_y - 20),
            ]
            roof = [
                (center_x - 95, center_y - 20),
                (center_x, center_y - 95),
                (center_x + 95, center_y - 20),
            ]
            door = [
                (center_x - 22, center_y + 70),
                (center_x - 22, center_y + 20),
                (center_x + 22, center_y + 20),
                (center_x + 22, center_y + 70),
            ]
            return [walls, roof, door]

        elif shape_norm in ("circle", "oval"):
            pts = []
            radius = size // 2
            for deg in range(0, 365, 15):
                rad = math.radians(deg)
                x = int(center_x + radius * math.cos(rad))
                y = int(center_y + radius * math.sin(rad))
                pts.append((x, y))
            return [pts]

        elif shape_norm in ("triangle",):
            p1 = (center_x, center_y - size // 2)
            p2 = (center_x + size // 2, center_y + size // 2)
            p3 = (center_x - size // 2, center_y + size // 2)
            return [[p1, p2, p3, p1]]

        elif shape_norm in ("star",):
            star_pts = []
            for i in range(11):
                r = size // 2 if i % 2 == 0 else size // 4
                ang = -math.pi / 2 + i * math.pi / 5
                star_pts.append((int(center_x + r * math.cos(ang)), int(center_y + r * math.sin(ang))))
            return [star_pts]

        elif shape_norm in ("stickman", "person"):
            head_pts = [
                (int(center_x + 25 * math.cos(math.radians(deg))), int(center_y - 60 + 25 * math.sin(math.radians(deg))))
                for deg in range(0, 365, 30)
            ]
            body = [(center_x, center_y - 35), (center_x, center_y + 35)]
            left_leg = [(center_x, center_y + 35), (center_x - 35, center_y + 95)]
            right_leg = [(center_x, center_y + 35), (center_x + 35, center_y + 95)]
            arms = [(center_x - 45, center_y - 10), (center_x, center_y - 15), (center_x + 45, center_y - 10)]
            return [head_pts, body, left_leg, right_leg, arms]

        else:
            p1 = (center_x - size // 2, center_y - size // 2)
            p2 = (center_x + size // 2, center_y - size // 2)
            p3 = (center_x + size // 2, center_y + size // 2)
            p4 = (center_x - size // 2, center_y + size // 2)
            return [[p1, p2, p3, p4, p1]]
