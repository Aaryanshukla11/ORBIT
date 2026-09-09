"""Strategy Execution Engine (M1.9 Component 3).

Authoritatively executes multi-stage StrategyOption objects by sequentially binding
inputs, resolving runtime executors, observing desktop deltas, and enforcing
stage-level verification contracts.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.infrastructure.event_bus import EventBus, EventType, RuntimeEvent
from orbit.runtime.cancellation import CancellationToken
from orbit.runtime.capabilities.execution.contracts import (
    CapabilityExecutionRequest,
    CapabilityExecutionResult,
    StageOutcomeStatus,
)
from orbit.runtime.capabilities.execution.executor_registry import CapabilityExecutorRegistry
from orbit.runtime.capabilities.execution.output_binding import StageOutputResolver
from orbit.runtime.capabilities.execution.stage_recovery import StageRecoveryManager
from orbit.runtime.capabilities.execution.stage_verifier import StageOutcomeVerifier
from orbit.runtime.capabilities.models import StrategyOption, StrategyStage
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.cognitive.observer import CurrentStateObserver

logger = logging.getLogger(__name__)


class StrategyExecutionResult(BaseModel):
    """Authoritative result of executing a complete StrategyOption."""

    strategy_id: str = Field(..., description="Executed strategy identifier")
    strategy_name: str = Field(..., description="Executed strategy name")
    is_success: bool = Field(..., description="Whether all stages executed and verified successfully")
    total_stages: int = Field(default=0, description="Total stages declared in strategy")
    completed_stages_count: int = Field(default=0, description="Number of stages successfully executed")
    stage_results: List[CapabilityExecutionResult] = Field(default_factory=list, description="Per-stage execution records")
    final_stage_status: StageOutcomeStatus = Field(default=StageOutcomeStatus.PENDING)
    stage_outputs: Dict[str, Any] = Field(default_factory=dict, description="Accumulated pipeline stage outputs")
    failure_code: Optional[str] = Field(default=None)
    failure_reason: Optional[str] = Field(default=None)
    duration_ms: float = Field(default=0.0)


class StrategyExecutionEngine:
    """Production engine executing selected strategies stage-by-stage against real capabilities."""

    def __init__(
        self,
        executor_registry: CapabilityExecutorRegistry,
        observer: Optional[CurrentStateObserver] = None,
        event_bus: Optional[EventBus] = None,
        recovery_manager: Optional[StageRecoveryManager] = None,
    ) -> None:
        self._registry = executor_registry
        self._observer = observer
        self._event_bus = event_bus
        self._recovery = recovery_manager or StageRecoveryManager(max_recovery_attempts=2)

    @property
    def registry(self) -> CapabilityExecutorRegistry:
        return self._registry

    def can_execute_strategy(self, strategy: StrategyOption) -> bool:
        """Verify whether every required capability and stage in the strategy has an executable executor."""
        if not strategy.stages:
            return False

        for stage in strategy.stages:
            cid = stage.capability_id.upper()
            if not self._registry.is_executable(cid):
                logger.warning(
                    "[StrategyExecutionEngine] Strategy '%s' rejected: capability '%s' is not executable in registry",
                    strategy.name,
                    cid,
                )
                return False
        return True

    async def execute_strategy(
        self,
        strategy: StrategyOption,
        objective: StructuredObjective,
        context: Optional[Dict[str, Any]] = None,
        cancel_token: Optional[CancellationToken] = None,
        session_id: str = "default_session",
    ) -> StrategyExecutionResult:
        """Authoritatively execute a multi-stage StrategyOption end-to-end."""
        t_start = time.perf_counter()
        context = dict(context or {})
        stage_outputs: Dict[str, Any] = {}
        stage_results: List[CapabilityExecutionResult] = []

        logger.info(
            "[StrategyExecutionEngine] Starting execution of strategy '%s' (%d stages)",
            strategy.name,
            len(strategy.stages),
        )

        # Telemetry: Strategy Started
        await self._publish_telemetry(
            session_id=session_id,
            event_type=EventType.PLAN_UPDATED,
            payload={
                "strategy_id": strategy.strategy_id,
                "strategy_name": strategy.name,
                "stages_count": len(strategy.stages),
                "lifecycle": "STARTED",
            },
        )

        for stage_idx, stage in enumerate(strategy.stages):
            # 1. Cancellation check
            if cancel_token and cancel_token.is_cancelled:
                logger.info("[StrategyExecutionEngine] Cancellation received at stage %d", stage_idx)
                return StrategyExecutionResult(
                    strategy_id=strategy.strategy_id,
                    strategy_name=strategy.name,
                    is_success=False,
                    total_stages=len(strategy.stages),
                    completed_stages_count=len(stage_results),
                    stage_results=stage_results,
                    final_stage_status=StageOutcomeStatus.FAILED,
                    stage_outputs=stage_outputs,
                    failure_code="TASK_CANCELLED",
                    failure_reason=cancel_token.reason or "Cancelled by operator",
                    duration_ms=(time.perf_counter() - t_start) * 1000.0,
                )

            # 2. Lookup Executor
            cid = stage.capability_id.upper()
            executor = self._registry.get_executor(cid)
            if executor is None or not executor.is_available():
                logger.error("[StrategyExecutionEngine] Executor missing or unavailable for '%s'", cid)
                return StrategyExecutionResult(
                    strategy_id=strategy.strategy_id,
                    strategy_name=strategy.name,
                    is_success=False,
                    total_stages=len(strategy.stages),
                    completed_stages_count=len(stage_results),
                    stage_results=stage_results,
                    final_stage_status=StageOutcomeStatus.FAILED,
                    stage_outputs=stage_outputs,
                    failure_code="CAPABILITY_EXECUTOR_NOT_FOUND" if executor is None else "CAPABILITY_UNAVAILABLE",
                    failure_reason=f"Capability executor '{cid}' is unavailable at runtime",
                    duration_ms=(time.perf_counter() - t_start) * 1000.0,
                )

            # 3. Dynamic Output Binding
            binding_ok, resolved_params, binding_err = StageOutputResolver.resolve_parameters(
                raw_parameters=stage.parameters,
                stage_outputs=stage_outputs,
            )
            if not binding_ok:
                logger.error("[StrategyExecutionEngine] Stage %d parameter binding failed: %s", stage_idx, binding_err)
                return StrategyExecutionResult(
                    strategy_id=strategy.strategy_id,
                    strategy_name=strategy.name,
                    is_success=False,
                    total_stages=len(strategy.stages),
                    completed_stages_count=len(stage_results),
                    stage_results=stage_results,
                    final_stage_status=StageOutcomeStatus.FAILED,
                    stage_outputs=stage_outputs,
                    failure_code="STAGE_INPUT_BINDING_FAILED",
                    failure_reason=binding_err,
                    duration_ms=(time.perf_counter() - t_start) * 1000.0,
                )

            # 4. Pre-Action Desktop Observation
            pre_obs: Optional[CurrentStateObservation] = None
            if self._observer is not None:
                try:
                    pre_obs = await self._observer.observe(objective)
                    context["current_observation"] = pre_obs
                except Exception as ex:
                    logger.debug("Pre-observation capture notice: %s", ex)

            # Telemetry: Stage Running
            await self._publish_telemetry(
                session_id=session_id,
                event_type=EventType.ACTION_STAGE_CHANGED,
                payload={
                    "stage_index": stage_idx,
                    "stage_name": stage.name,
                    "capability_id": cid,
                    "status": "RUNNING",
                },
            )

            # 5. Execute Capability
            req = CapabilityExecutionRequest(
                capability_id=cid,
                stage_index=stage_idx,
                parameters=resolved_params,
                context=context,
                cancel_token=cancel_token,
            )
            exec_res = await executor.execute(req)

            # 6. Post-Action Desktop Observation
            post_obs: Optional[CurrentStateObservation] = None
            if self._observer is not None:
                try:
                    post_obs = await self._observer.observe(objective)
                except Exception as ex:
                    logger.debug("Post-observation capture notice: %s", ex)

            # 7. Stage-Level Outcome Verification
            outcome_status = StageOutcomeVerifier.verify_stage_outcome(
                capability_id=cid,
                exec_result=exec_res,
                pre_observation=pre_obs,
                post_observation=post_obs,
                parameters=resolved_params,
            )
            exec_res.stage_status = outcome_status

            # 8. Recovery Handling if Unverified
            if outcome_status in (StageOutcomeStatus.EFFECT_UNVERIFIED, StageOutcomeStatus.FAILED):
                if self._recovery.can_attempt_recovery(stage_idx):
                    logger.warning("[StrategyExecutionEngine] Stage %d unverified; triggering recovery", stage_idx)
                    rec_res = await self._recovery.attempt_recovery(
                        executor=executor,
                        request=req,
                        observer=self._observer,
                    )
                    # Re-verify post-recovery
                    if self._observer is not None:
                        try:
                            post_obs = await self._observer.observe(objective)
                        except Exception:
                            pass
                    outcome_status = StageOutcomeVerifier.verify_stage_outcome(
                        capability_id=cid,
                        exec_result=rec_res,
                        pre_observation=pre_obs,
                        post_observation=post_obs,
                        parameters=resolved_params,
                    )
                    rec_res.stage_status = outcome_status
                    exec_res = rec_res

            # Fail closed if stage failed or remains unverified
            if not exec_res.execution_success or outcome_status not in (
                StageOutcomeStatus.DISPATCHED,
                StageOutcomeStatus.EFFECT_VERIFIED,
            ):
                logger.error(
                    "[StrategyExecutionEngine] Stage %d ('%s') failed with status: %s",
                    stage_idx,
                    stage.name,
                    outcome_status.value,
                )
                stage_results.append(exec_res)
                await self._publish_telemetry(
                    session_id=session_id,
                    event_type=EventType.ACTION_STAGE_CHANGED,
                    payload={
                        "stage_index": stage_idx,
                        "stage_name": stage.name,
                        "status": outcome_status.value,
                        "failure_code": exec_res.failure_code or "STAGE_OUTCOME_UNVERIFIED",
                    },
                )
                return StrategyExecutionResult(
                    strategy_id=strategy.strategy_id,
                    strategy_name=strategy.name,
                    is_success=False,
                    total_stages=len(strategy.stages),
                    completed_stages_count=len(stage_results) - 1,
                    stage_results=stage_results,
                    final_stage_status=outcome_status,
                    stage_outputs=stage_outputs,
                    failure_code=exec_res.failure_code or "STAGE_OUTCOME_UNVERIFIED",
                    failure_reason=exec_res.failure_reason or f"Expected effect for stage '{stage.name}' was not observed",
                    duration_ms=(time.perf_counter() - t_start) * 1000.0,
                )

            # 9. Store Stage Output into Pipeline Context
            stage_key = f"stage_{stage_idx}"
            cap_key = f"stages.{cid}"
            stage_outputs[stage_key] = exec_res.output
            stage_outputs[cap_key] = exec_res.output
            stage_results.append(exec_res)

            # Telemetry: Stage Completed
            await self._publish_telemetry(
                session_id=session_id,
                event_type=EventType.ACTION_STAGE_CHANGED,
                payload={
                    "stage_index": stage_idx,
                    "stage_name": stage.name,
                    "status": outcome_status.value,
                    "output": exec_res.output,
                },
            )

        # Telemetry: Strategy Completed
        await self._publish_telemetry(
            session_id=session_id,
            event_type=EventType.PLAN_UPDATED,
            payload={
                "strategy_id": strategy.strategy_id,
                "strategy_name": strategy.name,
                "stages_completed": len(stage_results),
                "lifecycle": "COMPLETED",
            },
        )

        return StrategyExecutionResult(
            strategy_id=strategy.strategy_id,
            strategy_name=strategy.name,
            is_success=True,
            total_stages=len(strategy.stages),
            completed_stages_count=len(stage_results),
            stage_results=stage_results,
            final_stage_status=StageOutcomeStatus.EFFECT_VERIFIED,
            stage_outputs=stage_outputs,
            duration_ms=(time.perf_counter() - t_start) * 1000.0,
        )

    async def _publish_telemetry(
        self,
        session_id: str,
        event_type: EventType,
        payload: Dict[str, Any],
    ) -> None:
        if self._event_bus is not None:
            try:
                from uuid import uuid4
                evt = RuntimeEvent(
                    event_id=f"evt_{uuid4().hex[:12]}",
                    event_type=event_type,
                    session_id=session_id,
                    correlation_id=payload.get("strategy_id", "strategy"),
                    timestamp=datetime.now(timezone.utc),
                    payload=payload,
                )
                await self._event_bus.publish(evt)
            except Exception as ex:
                logger.debug("Telemetry publish notice: %s", ex)
