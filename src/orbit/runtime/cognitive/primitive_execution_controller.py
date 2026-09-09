"""Primitive Execution Controller.

Guardrail 1: Single Execution Path
Every environment-changing action MUST go through:
PrimitiveComposer -> PrimitiveValidator -> PrimitiveExecutionController -> Target Grounding / Provider Resolution -> Safety Gate -> Executor.
No component may bypass PrimitiveExecutionController and directly execute an action.

Guardrail 6: Closed-Loop is a Hard Invariant
Never execute Action N+1 until Action N -> Observe -> Verify postcondition has completed.
If verification is FAILED or INCONCLUSIVE, stop the sequence and enter diagnosis/replanning.

Guardrail 16: No Silent Fallback Success
Missing executor/provider/grounding must result in an explicit failure or unavailable state.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

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
from orbit.runtime.cognitive.primitive_validator import PrimitiveValidator, PrimitiveValidationResult
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
    """Authoritative controller enforcing the single execution path and closed-loop invariant.

    Guarantees:
    1. Validation check via PrimitiveValidator.
    2. Resolution / grounding via target resolver or provider.
    3. Safety check before execution.
    4. Physical execution via registered capability or provider.
    5. Post-execution live observation capture.
    6. Multi-evidence semantic verification.
    7. Closed-loop enforcement: Action N+1 is forbidden if verification failed.
    """

    def __init__(
        self,
        validator: Optional[PrimitiveValidator] = None,
        verifier: Optional[MultiEvidenceActionVerifier] = None,
        provider_registry: Optional[EnvironmentProviderRegistry] = None,
    ):
        self._validator = validator or PrimitiveValidator()
        self._verifier = verifier or MultiEvidenceActionVerifier()
        self._provider_registry = provider_registry

    async def execute_primitive(
        self,
        action: AbstractAction,
        pre_observation: CurrentStateObservation,
        objective: StructuredObjective,
        grounding_fn: Callable[[Any, CurrentStateObservation], Any],
        safety_gate_fn: Callable[[AbstractAction, Optional[Tuple[int, int]]], Tuple[bool, Optional[str]]],
        dispatch_fn: Callable[[AbstractAction, CurrentStateObservation, Optional[Tuple[int, int]], Any], Any],
        observe_fn: Callable[[StructuredObjective], Any],
        cancel_token: Optional[Any] = None,
    ) -> ControllerExecutionResult:
        """Execute a single primitive under strict closed-loop invariants."""
        t_start = time.perf_counter()

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
        if action.target and requires_coords:
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

        # Step 4: Physical Dispatch / Provider Execution
        dispatch_success, dispatch_err = await dispatch_fn(action, pre_observation, resolved_coords, cancel_token)
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
