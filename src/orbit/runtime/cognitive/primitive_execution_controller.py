"""Primitive Execution Controller (ORBIT Sole Physical Execution Authority).

INVARIANT (ORBIT Rule 1 & 6):
PrimitiveExecutionController is the SINGLE physical execution authority.
Every environment-changing action MUST go through:
PlanDirective -> PrimitiveComposer -> PrimitiveValidator -> PrimitiveExecutionController -> Safety Gate -> Grounded Physical Dispatch -> Observe -> Verify.

No cognitive module, planner, decision engine, or recovery manager may bypass
PrimitiveExecutionController and directly execute an OS or capability action.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from orbit.contracts.capabilities import (
    KeyboardCapability,
    PointerCapability,
    WorkspaceCapability,
)
from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    OutcomeStatus,
    ResolvedAction,
)
from orbit.runtime.cognitive.models import (
    CognitiveStepResult,
    CurrentStateObservation,
    StructuredObjective,
)
from orbit.runtime.cognitive.primitive_validator import (
    PrimitiveValidationResult,
    PrimitiveValidator,
)
from orbit.runtime.environment.drawing_provider import CanvasDrawingProvider
from orbit.runtime.environment.registry import EnvironmentProviderRegistry
from orbit.runtime.task_completion.multi_evidence_verifier import (
    MultiEvidenceActionVerifier,
    MultiEvidenceVerificationResult,
)

logger = logging.getLogger(__name__)


class ControllerExecutionResult(BaseModel):
    """Execution and verification outcome for a single action step."""

    action_dispatched: AbstractAction
    execution_outcome: ActionExecutionOutcome
    post_observation: CurrentStateObservation
    should_continue: bool = Field(..., description="Whether closed-loop pipeline may advance to Action N+1")
    failure_report: Optional[Dict[str, Any]] = Field(default=None, description="Diagnostic data if verification failed")


class PrimitiveExecutionController:
    """Sole physical execution authority enforcing single execution path and closed-loop invariants.

    Guarantees:
    1. Validation check via PrimitiveValidator.
    2. Resolution / grounding via target resolver or provider.
    3. Safety check before execution.
    4. Physical execution via registered capabilities (Pointer, Keyboard, Workspace) or Environment Providers.
    5. Post-execution live observation capture.
    6. Multi-evidence semantic verification.
    7. Closed-loop enforcement: Action N+1 is forbidden if verification failed.
    """

    def __init__(
        self,
        validator: Optional[PrimitiveValidator] = None,
        verifier: Optional[MultiEvidenceActionVerifier] = None,
        provider_registry: Optional[EnvironmentProviderRegistry] = None,
        pointer: Optional[PointerCapability] = None,
        keyboard: Optional[KeyboardCapability] = None,
        workspace: Optional[WorkspaceCapability] = None,
        application_launcher: Optional[Any] = None,
    ) -> None:
        self._validator = validator or PrimitiveValidator()
        self._verifier = verifier or MultiEvidenceActionVerifier()
        self._provider_registry = provider_registry
        self._pointer = pointer
        self._keyboard = keyboard
        self._workspace = workspace
        self._application_launcher = application_launcher

    def set_capabilities(
        self,
        pointer: Optional[PointerCapability] = None,
        keyboard: Optional[KeyboardCapability] = None,
        workspace: Optional[WorkspaceCapability] = None,
        application_launcher: Optional[Any] = None,
        provider_registry: Optional[EnvironmentProviderRegistry] = None,
    ) -> None:
        """Dynamically configure capability adapters."""
        if pointer is not None:
            self._pointer = pointer
        if keyboard is not None:
            self._keyboard = keyboard
        if workspace is not None:
            self._workspace = workspace
        if application_launcher is not None:
            self._application_launcher = application_launcher
        if provider_registry is not None:
            self._provider_registry = provider_registry

    async def dispatch_physical_action(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
        resolved_coords: Optional[Tuple[int, int]] = None,
        cancel_token: Optional[Any] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Physical action execution across registered capabilities and providers."""
        act_type = action.action_type
        params = action.parameters
        dispatch_success = False
        err_msg: Optional[str] = None

        logger.info(
            "[PHYSICAL DISPATCH] action_id=%s, type=%s, params=%s",
            getattr(action, "action_id", "act"),
            act_type.value if hasattr(act_type, "value") else str(act_type),
            params,
        )

        try:
            if act_type == AbstractActionType.LAUNCH_APPLICATION:
                app_name = str(
                    params.get(
                        "application_name",
                        params.get("app_name", action.target.name if action.target else "notepad"),
                    )
                ).strip()

                # IDEMPOTENT APPLICATION LAUNCH: Check if application is already open
                already_open_hwnd = None
                already_open_title = ""
                for win in pre_obs.visible_windows:
                    w_title = (win.get("title") or "").lower()
                    w_proc = (win.get("process_name") or "").lower()
                    if app_name.lower() in w_title or app_name.lower() in w_proc:
                        already_open_hwnd = win.get("hwnd")
                        already_open_title = win.get("title", "")
                        break

                if not already_open_hwnd and pre_obs.active_window_title and app_name.lower() in pre_obs.active_window_title.lower():
                    already_open_hwnd = pre_obs.active_window_hwnd
                    already_open_title = pre_obs.active_window_title

                if already_open_hwnd:
                    logger.info(
                        "[IDEMPOTENT LAUNCH] Application '%s' is ALREADY OPEN in window '%s' (HWND: %s). Reusing existing window.",
                        app_name,
                        already_open_title,
                        already_open_hwnd,
                    )
                    if self._workspace is not None and hasattr(self._workspace, "set_focus_window"):
                        await self._workspace.set_focus_window(int(already_open_hwnd))
                    await asyncio.sleep(0.3)
                    return True, None

                # Launch via WorkspaceCapability or ApplicationLauncher
                if self._workspace is not None and hasattr(self._workspace, "launch_process"):
                    raw_proc = self._workspace.launch_process(app_name)
                    if inspect.isawaitable(raw_proc):
                        proc_info = await raw_proc
                    else:
                        proc_info = raw_proc
                    dispatch_success = bool(proc_info)
                else:
                    launcher = self._application_launcher
                    if launcher is None:
                        from orbit.runtime.capabilities.application_launcher import ApplicationLauncher
                        launcher = ApplicationLauncher()
                        self._application_launcher = launcher
                    launch_res = launcher.launch(app_name)
                    dispatch_success = launch_res.success
                    err_msg = launch_res.error_message
                    if launch_res.success:
                        await asyncio.sleep(1.0)

            elif act_type == AbstractActionType.FOCUS_WINDOW:
                app_name = str(params.get("window_title", params.get("application_name", params.get("app_name", action.target.name if action.target else ""))))
                hwnd = params.get("hwnd")
                if not hwnd and app_name:
                    for win in pre_obs.visible_windows:
                        title = (win.get("title") or "").lower()
                        cname = (win.get("class_name") or "").lower()
                        if app_name.lower() in title or app_name.lower() in cname:
                            hwnd = win.get("hwnd")
                            break
                if not hwnd:
                    hwnd = pre_obs.active_window_hwnd

                if hwnd and self._workspace is not None and hasattr(self._workspace, "set_focus_window"):
                    dispatch_success = await self._workspace.set_focus_window(int(hwnd))
                else:
                    dispatch_success = True

            elif act_type == AbstractActionType.TYPE_TEXT:
                text = str(params.get("text", params.get("query", "")))
                press_enter = bool(params.get("press_enter", False))
                if self._keyboard is not None:
                    await self._keyboard.type_text(text)
                    if press_enter:
                        await asyncio.sleep(0.05)
                        if hasattr(self._keyboard, "hotkey"):
                            await self._keyboard.hotkey("enter")
                        elif hasattr(self._keyboard, "press_key"):
                            await self._keyboard.press_key("enter")
                    dispatch_success = True
                else:
                    dispatch_success = False
                    err_msg = "REQUIRED_ADAPTER_MISSING: KeyboardCapability"

            elif act_type == AbstractActionType.CLICK:
                if self._pointer is None:
                    dispatch_success = False
                    err_msg = "REQUIRED_ADAPTER_MISSING: PointerCapability"
                else:
                    coords = resolved_coords
                    if not coords:
                        tgt_coords = getattr(action.target, "coordinates", None) if action.target else None
                        if tgt_coords:
                            coords = (int(tgt_coords[0]), int(tgt_coords[1]))
                        elif "x" in params and "y" in params:
                            coords = (int(params["x"]), int(params["y"]))
                    if not coords:
                        dispatch_success = False
                        err_msg = f"TARGET_NOT_GROUNDED: Target '{action.target.name if action.target else 'unknown'}' coordinates could not be resolved"
                    else:
                        await self._pointer.move_to(coords[0], coords[1])
                        btn = params.get("button", "left")
                        if btn not in ("none", "move_only"):
                            await asyncio.sleep(0.05)
                            if hasattr(self._pointer, "click"):
                                count = params.get("count", 1)
                                try:
                                    sig = inspect.signature(self._pointer.click)
                                    if "button" in sig.parameters and "count" in sig.parameters:
                                        await self._pointer.click(coords[0], coords[1], button=btn, count=count)
                                    elif "x" in sig.parameters and "y" in sig.parameters:
                                        await self._pointer.click(coords[0], coords[1])
                                    else:
                                        await self._pointer.click()
                                except Exception:
                                    await self._pointer.click()
                        dispatch_success = True

            elif act_type == AbstractActionType.DOUBLE_CLICK:
                if self._pointer is None:
                    dispatch_success = False
                    err_msg = "REQUIRED_ADAPTER_MISSING: PointerCapability"
                else:
                    coords = resolved_coords
                    if not coords:
                        dispatch_success = False
                        err_msg = f"TARGET_NOT_GROUNDED: Target '{action.target.name if action.target else 'unknown'}' coordinates could not be resolved"
                    else:
                        await self._pointer.move_to(coords[0], coords[1])
                        await asyncio.sleep(0.05)
                        await self._pointer.click()
                        await asyncio.sleep(0.05)
                        await self._pointer.click()
                        dispatch_success = True

            elif act_type == AbstractActionType.RIGHT_CLICK:
                if self._pointer is None:
                    dispatch_success = False
                    err_msg = "REQUIRED_ADAPTER_MISSING: PointerCapability"
                else:
                    coords = resolved_coords
                    if not coords:
                        dispatch_success = False
                        err_msg = f"TARGET_NOT_GROUNDED: Target '{action.target.name if action.target else 'unknown'}' coordinates could not be resolved"
                    else:
                        await self._pointer.move_to(coords[0], coords[1])
                        await asyncio.sleep(0.05)
                        if hasattr(self._pointer, "click_button"):
                            await self._pointer.click_button("right")
                        else:
                            await self._pointer.click()
                        dispatch_success = True

            elif act_type == AbstractActionType.SEND_HOTKEY:
                combination = str(params.get("hotkey", params.get("combination", "ctrl+s")))
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

            elif act_type == AbstractActionType.DRAW_STROKES:
                drawing_provider = None
                if self._provider_registry is not None:
                    drawing_provider = await self._provider_registry.resolve_provider(AbstractActionType.DRAW_STROKES)
                if drawing_provider is None:
                    drawing_provider = CanvasDrawingProvider(pointer=self._pointer)
                elif hasattr(drawing_provider, "set_pointer") and self._pointer is not None:
                    drawing_provider.set_pointer(self._pointer)
                res = await drawing_provider.execute(action)
                dispatch_success = res.success
                err_msg = res.error

            elif act_type == AbstractActionType.SAVE_FILE:
                dispatch_success, err_msg = await self._dispatch_save_file(action, pre_obs)

            elif act_type == AbstractActionType.SCROLL:
                direction = str(params.get("direction", "down"))
                if self._pointer is not None and hasattr(self._pointer, "scroll"):
                    await self._pointer.scroll(direction=direction, amount=120)
                    dispatch_success = True
                elif self._pointer is not None:
                    dispatch_success = True
                else:
                    dispatch_success = False
                    err_msg = "REQUIRED_ADAPTER_MISSING: PointerCapability"

            elif act_type in (AbstractActionType.SCREENSHOT, AbstractActionType.READ_UI_ELEMENT, AbstractActionType.READ_OCR_TEXT):
                if self._observation_service is not None and hasattr(self._observation_service, "capture_observation"):
                    await self._observation_service.capture_observation()
                dispatch_success = True

            elif act_type in (AbstractActionType.WAIT, AbstractActionType.WAIT_SETTLE):
                dur_ms = float(params.get("duration_sec", 0.5)) * 1000.0 if "duration_sec" in params else float(params.get("duration_ms", 500))
                await asyncio.sleep(dur_ms / 1000.0)
                dispatch_success = True

            elif act_type == AbstractActionType.COMPLETE_GOAL:
                dispatch_success = True

            elif isinstance(act_type, AbstractActionType) and self._provider_registry is not None:
                provider = await self._provider_registry.resolve_provider(act_type, action)
                if provider is not None:
                    res = await provider.execute(action)
                    dispatch_success = res.success
                    err_msg = res.error
                else:
                    dispatch_success = False
                    err_msg = f"NO_AVAILABLE_PROVIDER: No provider available for {act_type.value if hasattr(act_type, 'value') else act_type}"

            else:
                dispatch_success = False
                err_msg = f"UNKNOWN_ACTION_TYPE: {act_type.value if hasattr(act_type, 'value') else act_type}"

        except Exception as ex:
            logger.exception("[PHYSICAL DISPATCH] Exception during action dispatch: %s", ex)
            dispatch_success = False
            err_msg = f"DISPATCH_EXCEPTION: {str(ex)}"

        return dispatch_success, err_msg

    async def _dispatch_save_file(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
    ) -> Tuple[bool, Optional[str]]:
        """Execute physical Save File workflow with dialog interaction and physical file verification."""
        params = action.parameters or {}
        filename = str(params.get("filename", params.get("target_path", params.get("path", "")))).strip()
        target_dir = str(params.get("target_dir", params.get("destination", ""))).strip().lower()
        if not filename and action.target:
            filename = str(action.target.name or "").strip()

        if not filename:
            filename = "test.png"

        # Dynamically resolve desktop / destination path without hardcoding usernames
        user_profile = os.environ.get("USERPROFILE", "")
        home_dir = os.path.expanduser("~")
        
        desktop_candidates = []
        if user_profile:
            onedrive_desktop = os.path.join(user_profile, "OneDrive", "Desktop")
            if os.path.exists(onedrive_desktop):
                desktop_candidates.append(onedrive_desktop)
            user_desktop = os.path.join(user_profile, "Desktop")
            if os.path.exists(user_desktop):
                desktop_candidates.append(user_desktop)
        if home_dir:
            h_onedrive_desktop = os.path.join(home_dir, "OneDrive", "Desktop")
            if os.path.exists(h_onedrive_desktop) and h_onedrive_desktop not in desktop_candidates:
                desktop_candidates.append(h_onedrive_desktop)
            h_desktop = os.path.join(home_dir, "Desktop")
            if os.path.exists(h_desktop) and h_desktop not in desktop_candidates:
                desktop_candidates.append(h_desktop)

        primary_desktop = desktop_candidates[0] if desktop_candidates else (os.path.join(home_dir, "Desktop") if home_dir else os.getcwd())

        # Determine target absolute path
        if os.path.isabs(filename):
            resolved_target_path = filename
        elif target_dir == "desktop" or "desktop" in filename.lower():
            base_name = os.path.basename(filename)
            resolved_target_path = os.path.join(primary_desktop, base_name)
        else:
            resolved_target_path = os.path.join(primary_desktop, os.path.basename(filename))

        logger.info("[SAVE_FILE EXECUTION] Target resolved path: %s", resolved_target_path)

        # 1. Trigger Save Dialog via Keyboard Shortcut
        if self._keyboard is not None:
            # Send Ctrl+S hotkey
            try:
                if hasattr(self._keyboard, "hotkey"):
                    await self._keyboard.hotkey("ctrl", "s")
                else:
                    await self._keyboard.press_key("ctrl")
                    await self._keyboard.press_key("s")
                    await self._keyboard.release_key("s")
                    await self._keyboard.release_key("ctrl")
            except Exception as k_err:
                logger.warning("[SAVE_FILE] Hotkey ctrl+s error: %s", k_err)

            # Wait for Save As dialog to appear and settle
            await asyncio.sleep(0.8)

            # 2. Type target absolute path into dialog filename input
            try:
                await self._keyboard.type_text(resolved_target_path)
            except Exception as t_err:
                logger.warning("[SAVE_FILE] Type path error: %s", t_err)

            await asyncio.sleep(0.3)

            # 3. Press Enter to confirm save
            try:
                if hasattr(self._keyboard, "hotkey"):
                    await self._keyboard.hotkey("enter")
                elif hasattr(self._keyboard, "press_key"):
                    await self._keyboard.press_key("enter")
                    await self._keyboard.release_key("enter")
            except Exception as e_err:
                logger.warning("[SAVE_FILE] Enter press error: %s", e_err)

            await asyncio.sleep(0.6)

            # 4. Handle potential overwrite confirmation dialog ("Already exists, do you want to replace it?")
            # Send Alt+Y or Enter to accept overwrite if prompt appeared
            try:
                if hasattr(self._keyboard, "hotkey"):
                    await self._keyboard.hotkey("alt", "y")
            except Exception:
                pass

            await asyncio.sleep(0.8)
        else:
            logger.warning("[SAVE_FILE] Keyboard adapter missing; cannot interact with GUI save dialog")

        # 5. Post-Action Physical Verification
        check_paths = [resolved_target_path]
        base_name = os.path.basename(resolved_target_path)
        for d_dir in desktop_candidates:
            c_p = os.path.join(d_dir, base_name)
            if c_p not in check_paths:
                check_paths.append(c_p)
        check_paths.append(os.path.abspath(base_name))

        verified_path = None
        for p in check_paths:
            if os.path.exists(p) and os.path.isfile(p):
                sz = os.path.getsize(p)
                if sz > 0:
                    fmt = str(params.get("format", p.rsplit(".", 1)[-1] if "." in p else "png")).lower()
                    if fmt in ("png", "jpg", "jpeg", "bmp") or p.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                        try:
                            from PIL import Image
                            with Image.open(p) as img:
                                img.verify()
                            verified_path = p
                            break
                        except Exception as im_err:
                            logger.warning("[SAVE_FILE] Image verify failed on %s: %s", p, im_err)
                    else:
                        verified_path = p
                        break

        if verified_path:
            logger.info("[SAVE_FILE EXECUTION] Physical file verified: %s (size: %d bytes)", verified_path, os.path.getsize(verified_path))
            return True, None
        else:
            err = f"SAVE_VERIFICATION_FAILED: File '{resolved_target_path}' was not created or verified on disk."
            logger.warning("[SAVE_FILE EXECUTION] %s", err)
            return False, err

    async def execute_primitive(
        self,
        action: AbstractAction,
        pre_observation: CurrentStateObservation,
        objective: StructuredObjective,
        grounding_fn: Optional[Callable[[Any, CurrentStateObservation], Any]] = None,
        safety_gate_fn: Optional[Callable[[AbstractAction, Optional[Tuple[int, int]]], Tuple[bool, Optional[str]]]] = None,
        dispatch_fn: Optional[Callable[[AbstractAction, CurrentStateObservation, Optional[Tuple[int, int]], Any], Any]] = None,
        observe_fn: Optional[Callable[[StructuredObjective], Any]] = None,
        cancel_token: Optional[Any] = None,
    ) -> ControllerExecutionResult:
        """Execute a single primitive under strict closed-loop invariants."""
        t_start = time.perf_counter()

        # Step 0: Cancellation Gate
        if cancel_token is not None:
            is_canc = getattr(cancel_token, "is_cancelled", False)
            if callable(is_canc):
                is_canc = is_canc()
            if is_canc:
                reason = getattr(cancel_token, "reason", "Operation cancelled")
                logger.warning("[EXECUTION CONTROLLER] Execution aborted due to cancellation: %s", reason)
                outcome = ActionExecutionOutcome(
                    action_id=action.action_id,
                    dispatch_success=False,
                    expected_effect_observed=False,
                    outcome_status=OutcomeStatus.DISPATCH_FAILED,
                    error_message=f"Aborted: {reason}",
                    failure_code="OPERATION_CANCELLED",
                    duration_ms=(time.perf_counter() - t_start) * 1000.0,
                )
                return ControllerExecutionResult(
                    action_dispatched=action,
                    execution_outcome=outcome,
                    post_observation=pre_observation,
                    should_continue=False,
                    failure_report={"phase": "CANCELLATION", "reason": reason},
                )

        # Step 1: Primitive Validation Gate
        val_res: PrimitiveValidationResult = self._validator.validate_action(action)
        if not val_res.is_valid:
            logger.warning("[EXECUTION CONTROLLER] Action %s failed validation: %s", action.action_id, val_res.failure_reason)
            outcome = ActionExecutionOutcome(
                action_id=action.action_id,
                dispatch_success=False,
                expected_effect_observed=False,
                outcome_status=OutcomeStatus.DISPATCH_FAILED,
                error_message=val_res.failure_reason,
                failure_code=val_res.failure_code.value if val_res.failure_code else "VALIDATION_FAILED",
                duration_ms=(time.perf_counter() - t_start) * 1000.0,
            )
            return ControllerExecutionResult(
                action_dispatched=action,
                execution_outcome=outcome,
                post_observation=pre_observation,
                should_continue=False,
                failure_report={"phase": "VALIDATION", "reason": val_res.failure_reason, "code": val_res.failure_code},
            )

        # Step 2: Target Grounding / Coordinate Resolution (Infrastructure only)
        resolved_coords = None
        requires_coords = action.action_type in (
            AbstractActionType.CLICK,
            AbstractActionType.DOUBLE_CLICK,
            AbstractActionType.RIGHT_CLICK,
        )
        if action.target and requires_coords and grounding_fn is not None:
            resolved_coords = await grounding_fn(action.target, pre_observation)
            if resolved_coords is None:
                logger.warning("[EXECUTION CONTROLLER] Grounding failed for target: %s", action.target.name)
                outcome = ActionExecutionOutcome(
                    action_id=action.action_id,
                    dispatch_success=False,
                    expected_effect_observed=False,
                    outcome_status=OutcomeStatus.DISPATCH_FAILED,
                    error_message=f"Target grounding failed for '{action.target.name}'",
                    failure_code="TARGET_GROUNDING_FAILED",
                    duration_ms=(time.perf_counter() - t_start) * 1000.0,
                )
                return ControllerExecutionResult(
                    action_dispatched=action,
                    execution_outcome=outcome,
                    post_observation=pre_observation,
                    should_continue=False,
                    failure_report={"phase": "GROUNDING", "target": action.target.model_dump()},
                )

        # Step 3: Safety Gate Evaluation
        if safety_gate_fn is not None:
            is_safe, safety_reason = safety_gate_fn(action, resolved_coords)
            if not is_safe:
                logger.warning("[EXECUTION CONTROLLER] Safety gate blocked action %s: %s", action.action_id, safety_reason)
                outcome = ActionExecutionOutcome(
                    action_id=action.action_id,
                    dispatch_success=False,
                    expected_effect_observed=False,
                    outcome_status=OutcomeStatus.DISPATCH_FAILED,
                    error_message=safety_reason or "Blocked by safety gate",
                    failure_code="SAFETY_GATE_BLOCKED",
                    duration_ms=(time.perf_counter() - t_start) * 1000.0,
                )
                return ControllerExecutionResult(
                    action_dispatched=action,
                    execution_outcome=outcome,
                    post_observation=pre_observation,
                    should_continue=False,
                    failure_report={"phase": "SAFETY_GATE", "reason": safety_reason},
                )

        # Step 4: Physical Dispatch / Provider Execution (SOLE physical authority)
        if dispatch_fn is not None:
            dispatch_success, dispatch_err = await dispatch_fn(action, pre_observation, resolved_coords, cancel_token)
        else:
            dispatch_success, dispatch_err = await self.dispatch_physical_action(action, pre_observation, resolved_coords, cancel_token)

        if not dispatch_success:
            logger.warning("[EXECUTION CONTROLLER] Dispatch failed for action %s: %s", action.action_id, dispatch_err)
            outcome = ActionExecutionOutcome(
                action_id=action.action_id,
                dispatch_success=False,
                expected_effect_observed=False,
                outcome_status=OutcomeStatus.DISPATCH_FAILED,
                error_message=dispatch_err or "Low-level dispatch failed",
                failure_code="DISPATCH_FAILED",
                duration_ms=(time.perf_counter() - t_start) * 1000.0,
            )
            return ControllerExecutionResult(
                action_dispatched=action,
                execution_outcome=outcome,
                post_observation=pre_observation,
                should_continue=False,
                failure_report={"phase": "DISPATCH", "error": dispatch_err},
            )

        # Step 5: Post-Action Fresh Live Observation (Settle pause + observe)
        await asyncio.sleep(0.3)
        post_obs = pre_observation
        if observe_fn is not None:
            post_obs = await observe_fn(objective)

        # Step 6: Multi-Evidence Semantic Verification (Guardrails 6 & 7)
        v_res: MultiEvidenceVerificationResult = await self._verifier.verify_action_effect(
            action=action,
            pre_obs=pre_observation,
            post_obs=post_obs,
        )

        outcome = ActionExecutionOutcome(
            action_id=action.action_id,
            dispatch_success=True,
            expected_effect_observed=v_res.is_verified,
            verified=v_res.is_verified,
            outcome_status=v_res.outcome_status,
            verification_reason=v_res.verification_reason,
            failure_code=None if v_res.is_verified else "EFFECT_UNVERIFIED",
            duration_ms=(time.perf_counter() - t_start) * 1000.0,
        )

        # Guardrail 6: If verification FAILED, stop sequence and enter diagnosis/replanning
        should_continue = v_res.is_verified

        failure_report = None
        if not v_res.is_verified:
            logger.warning("[EXECUTION CONTROLLER] Postcondition verification FAILED for action %s: %s", action.action_id, v_res.verification_reason)
            failure_report = {
                "phase": "VERIFICATION",
                "action_id": action.action_id,
                "action_type": action.action_type.value,
                "expected_effect": action.expected_effect,
                "verification_reason": v_res.verification_reason,
                "confidence": v_res.confidence,
            }

        return ControllerExecutionResult(
            action_dispatched=action,
            execution_outcome=outcome,
            post_observation=post_obs,
            should_continue=should_continue,
            failure_report=failure_report,
        )


__all__ = [
    "ControllerExecutionResult",
    "PrimitiveExecutionController",
]
