"""Core Plan-to-Execution bridge orchestrator (M1.8 Step 3).

Coordinates dependency-aware topological plan dispatch through ClosedLoopExecutionEngine.
Guarantees per-step fresh observation, target localization, generation safety,
preemption protection, and comprehensive audit telemetry.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional, Set

from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.cancellation import CancellationToken
from orbit.runtime.execution import (
    ClosedLoopExecutionEngine,
    ClosedLoopExecutionResult,
    ExecutionPolicy,
    ExecutionState,
)
from orbit.runtime.execution.context import (
    CancellationReason,
    DispatchStage,
    ExecutionContext,
    PreemptionRecord,
)
from orbit.runtime.plan_execution.compiler import PlanStepCompiler
from orbit.runtime.plan_execution.models import (
    PlanExecutionContext,
    PlanExecutionResult,
    PlanExecutionStatus,
    PlanStepExecutionResult,
    PlanStepExecutionStatus,
)
from orbit.runtime.plan_execution.scheduler import PlanExecutionScheduler
from orbit.runtime.plan_execution.validator import PlanExecutionValidator
from orbit.runtime.planning.models import ExecutableTaskPlan, PlanStep
from orbit.runtime.replanning.models import FailureCategory, ReplanReason
from orbit.runtime.replanning.replanner import DynamicReplanner
from orbit.runtime.targeting.models import TargetIntent

logger = logging.getLogger(__name__)


class PlanExecutor:
    """Orchestrates multi-step ExecutableTaskPlans through closed-loop execution.

    .. deprecated::
        Superseded in production by the unified AI-native `AgentExecutionLoop` and `ModelRouter`.
        Retained for backward compatibility, testing, and legacy DAG step execution.
    """

    def __init__(
        self,
        execution_engine: ClosedLoopExecutionEngine,
        compiler: Optional[PlanStepCompiler] = None,
        validator: Optional[PlanExecutionValidator] = None,
        replanner: Optional[DynamicReplanner] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._execution_engine = execution_engine
        self._compiler = compiler or PlanStepCompiler()
        self._validator = validator or PlanExecutionValidator()
        self._replanner = replanner
        self._event_bus = event_bus

    @property
    def execution_engine(self) -> ClosedLoopExecutionEngine:
        return self._execution_engine

    @property
    def compiler(self) -> PlanStepCompiler:
        return self._compiler

    @property
    def validator(self) -> PlanExecutionValidator:
        return self._validator

    @property
    def replanner(self) -> Optional[DynamicReplanner]:
        return self._replanner

    async def execute_plan(
        self,
        plan: ExecutableTaskPlan,
        session_id: str,
        task_id: Optional[str] = None,
        policy: Optional[ExecutionPolicy] = None,
        cancel_token: Optional[CancellationToken] = None,
        context: Optional[ExecutionContext] = None,
    ) -> PlanExecutionResult:
        """Execute a validated ExecutableTaskPlan step-by-step through ClosedLoopExecutionEngine."""
        t_start = time.perf_counter()
        start_utc = datetime.now(timezone.utc)
        effective_task_id = task_id or plan.task_id

        if policy is not None and isinstance(policy, dict):
            policy = ExecutionPolicy(**policy)

        # 1. Pre-Execution Plan Validation
        val_res = self._validator.validate(plan)
        if not val_res.is_valid:
            logger.error("Plan %s rejected during pre-execution validation: %s", plan.plan_id, val_res.error_message)
            return PlanExecutionResult(
                plan_id=plan.plan_id,
                task_id=effective_task_id,
                final_status=PlanExecutionStatus.FAILED,
                is_success=False,
                total_steps=len(plan.steps),
                failure_code=val_res.error_code or "INVALID_PLAN",
                failure_reason=val_res.error_message or "Pre-execution plan validation failed",
                start_time_utc=start_utc,
                end_time_utc=datetime.now(timezone.utc),
                elapsed_duration_ms=0.0,
                diagnostics={"validation_diagnostics": val_res.diagnostics},
            )

        # 2. Setup Context & Scheduler
        plan_ctx = PlanExecutionContext(
            plan=plan,
            session_id=session_id,
            task_id=effective_task_id,
            parent_token=cancel_token,
            takeover_checker=self._execution_engine.is_human_takeover_active,
        )
        if context is not None and context.is_cancelled:
            plan_ctx.raw_context.cancel(context.cancellation_reason or CancellationReason.OPERATOR_CANCEL)

        current_plan = plan
        completed_step_ids: Set[str] = set()
        scheduler = PlanExecutionScheduler(current_plan)
        step_results_ordered: List[PlanStepExecutionResult] = []

        logger.info(
            "Starting execution for plan %s (task_id: %s, %d steps)",
            current_plan.plan_id, effective_task_id, scheduler.total_steps,
        )

        # 3. Sequential Closed-Loop Dispatch Loop
        while not scheduler.is_complete:
            # 3.1 Preemption & Takeover Guards
            if plan_ctx.is_cancelled:
                reason_msg = plan_ctx.raw_context.cancellation_message or "Execution cancelled"
                logger.warning("Plan execution cancelled: %s", reason_msg)
                scheduler.mark_cancelled(reason=reason_msg)
                if plan_ctx.raw_context.last_preemption_record is None:
                    rec = PreemptionRecord(
                        execution_id=effective_task_id,
                        reason=plan_ctx.raw_context.cancellation_reason or CancellationReason.OPERATOR_CANCEL,
                        state_at_preemption="PLAN_SCHEDULING",
                        message=reason_msg,
                    )
                    plan_ctx.raw_context.record_preemption(rec)
                break

            if await plan_ctx.is_takeover_active():
                logger.warning("Human takeover active; preempting plan execution fail-closed")
                plan_ctx.raw_context.cancel(
                    reason=CancellationReason.HUMAN_TAKEOVER,
                    message="Human takeover active; execution preempted",
                )
                scheduler.mark_cancelled(reason="Human takeover active")
                if plan_ctx.raw_context.last_preemption_record is None:
                    rec = PreemptionRecord(
                        execution_id=effective_task_id,
                        reason=CancellationReason.HUMAN_TAKEOVER,
                        state_at_preemption="PLAN_SCHEDULING",
                        message="Human takeover active; execution preempted",
                    )
                    plan_ctx.raw_context.record_preemption(rec)
                break

            # 3.2 Select Next Ready Step
            step = scheduler.get_next_ready_step()
            if step is None:
                # No ready steps remaining (either complete, blocked, or waiting)
                break

            scheduler.mark_running(step.step_id)
            step_start_utc = datetime.now(timezone.utc)
            t_step_start = time.perf_counter()

            # 3.3 Compile Step to Runtime Action
            compiled_action = self._compiler.compile(step)

            if not compiled_action.is_supported:
                fail_reason = compiled_action.rejection_reason or f"Action {step.action_type.value} is unsupported"
                logger.warning("Step %s (%s) unsupported: %s", step.step_id, step.action_type.value, fail_reason)
                step_res = PlanStepExecutionResult(
                    step_id=step.step_id,
                    step_index=step.step_index,
                    action_type=step.action_type,
                    status=PlanStepExecutionStatus.UNSUPPORTED,
                    compiled_action=compiled_action,
                    failure_reason=fail_reason,
                    failure_code="UNSUPPORTED_ACTION",
                    dependencies=step.dependencies,
                    start_time_utc=step_start_utc,
                    end_time_utc=datetime.now(timezone.utc),
                    duration_ms=(time.perf_counter() - t_step_start) * 1000.0,
                )
                step_results_ordered.append(step_res)
                plan_ctx.record_step_result(step_res)
                scheduler.mark_unsupported(step.step_id, reason=fail_reason)
                # Fail-closed on unsupported step
                break

            # 3.4 Execute via ClosedLoopExecutionEngine
            target_intent = compiled_action.target_intent or TargetIntent()
            exec_res: ClosedLoopExecutionResult = await self._execution_engine.execute_task_action(
                session_id=session_id,
                task_id=f"{effective_task_id}_{step.step_id}",
                prompt=step.description,
                target_intent=target_intent,
                action_type=compiled_action.action_type,
                action_parameters=compiled_action.action_parameters,
                expected_outcome=compiled_action.expected_outcome,
                policy=policy,
                cancel_token=plan_ctx.token,
                context=plan_ctx.raw_context,
                start_time=t_step_start,
            )

            t_step_end = time.perf_counter()
            step_duration_ms = (t_step_end - t_step_start) * 1000.0
            step_end_utc = datetime.now(timezone.utc)

            # 3.5 Record Step Result & Update Scheduler
            if exec_res.is_success:
                step_res = PlanStepExecutionResult(
                    step_id=step.step_id,
                    step_index=step.step_index,
                    action_type=step.action_type,
                    status=PlanStepExecutionStatus.SUCCEEDED,
                    compiled_action=compiled_action,
                    execution_result=exec_res,
                    verification_result=exec_res.verification_result,
                    resolved_target=exec_res.resolved_target,
                    desktop_generation_id=exec_res.resolved_target.desktop_generation_id if exec_res.resolved_target else None,
                    is_dispatched=exec_res.is_action_dispatched,
                    start_time_utc=step_start_utc,
                    end_time_utc=step_end_utc,
                    duration_ms=step_duration_ms,
                    dependencies=step.dependencies,
                )
                step_results_ordered.append(step_res)
                plan_ctx.record_step_result(step_res)
                completed_step_ids.add(step.step_id)
                scheduler.mark_succeeded(step.step_id)

                # Record execution checkpoint if replanner is configured
                if self._replanner is not None:
                    target_app = (
                        step.target.identifier
                        if step.target and step.target.semantic_type == "application"
                        else None
                    )
                    self._replanner.checkpoint_manager.create_checkpoint(
                        step=step,
                        completed_step_ids=completed_step_ids,
                        desktop_generation_id=exec_res.resolved_target.desktop_generation_id if exec_res.resolved_target else None,
                        window_identity=target_app,
                        application_name=target_app,
                        verified_state=exec_res.verification_result.model_dump() if exec_res.verification_result else {},
                        execution_evidence={
                            "is_dispatched": exec_res.is_action_dispatched,
                            "final_state": exec_res.final_state.value,
                        },
                    )
            else:
                fail_reason = exec_res.failure_reason or f"Step execution failed in state {exec_res.final_state.value}"
                fail_code = exec_res.failure_code or exec_res.final_state.value
                terminal_step_status = (
                    PlanStepExecutionStatus.CANCELLED
                    if exec_res.final_state in {ExecutionState.CANCELLED, ExecutionState.HUMAN_TAKEOVER}
                    else PlanStepExecutionStatus.FAILED
                )
                step_res = PlanStepExecutionResult(
                    step_id=step.step_id,
                    step_index=step.step_index,
                    action_type=step.action_type,
                    status=terminal_step_status,
                    compiled_action=compiled_action,
                    execution_result=exec_res,
                    verification_result=exec_res.verification_result,
                    resolved_target=exec_res.resolved_target,
                    failure_reason=fail_reason,
                    failure_code=fail_code,
                    desktop_generation_id=exec_res.resolved_target.desktop_generation_id if exec_res.resolved_target else None,
                    is_dispatched=exec_res.is_action_dispatched,
                    start_time_utc=step_start_utc,
                    end_time_utc=step_end_utc,
                    duration_ms=step_duration_ms,
                    dependencies=step.dependencies,
                )
                step_results_ordered.append(step_res)
                plan_ctx.record_step_result(step_res)

                if terminal_step_status == PlanStepExecutionStatus.CANCELLED:
                    scheduler.mark_cancelled(reason=fail_reason)
                    break

                # Attempt dynamic replanning if replanner is configured
                if self._replanner is not None:
                    logger.info("Attempting dynamic replanning for failed step %s...", step.step_id)
                    repair_result = await self._replanner.attempt_replan(
                        failed_step=step,
                        step_result=step_res,
                        completed_step_ids=completed_step_ids,
                        current_plan=current_plan,
                        session_id=session_id,
                        cancel_token=plan_ctx.token,
                        context=plan_ctx.raw_context,
                    )

                    if repair_result.is_success and repair_result.repaired_plan is not None:
                        logger.info(
                            "Dynamic replan succeeded (rev %d). Transitioning execution to repaired plan %s with %d steps.",
                            repair_result.revision_id,
                            repair_result.repaired_plan.plan_id,
                            len(repair_result.repaired_plan.steps),
                        )
                        current_plan = repair_result.repaired_plan
                        # Update completed steps set if backtracking pruned any
                        if repair_result.backtracked_step_ids:
                            completed_step_ids = set(repair_result.preserved_step_ids)
                            if repair_result.checkpoint:
                                self._replanner.checkpoint_manager.invalidate_after(repair_result.checkpoint.step_id)

                        # Rebuild scheduler with repaired plan
                        scheduler = PlanExecutionScheduler(current_plan)
                        for done_id in completed_step_ids:
                            if any(s.step_id == done_id for s in current_plan.steps):
                                scheduler.mark_succeeded(done_id)
                        # Continue execution loop with new scheduler and plan
                        continue
                    else:
                        logger.warning(
                            "Dynamic replan failed or was terminal (%s): %s",
                            repair_result.failure_code,
                            repair_result.failure_reason,
                        )
                        step_res.failure_reason = f"{fail_reason} | Replan rejected: {repair_result.failure_reason}"
                        if repair_result.failure_code:
                            step_res.failure_code = repair_result.failure_code

                scheduler.mark_failed(step.step_id, reason=step_res.failure_reason or fail_reason)
                # Stop further execution (fail-closed on unrecoverable failure)
                break

        # 4. Fill in Audit Records for Unexecuted / Blocked Steps
        for step in current_plan.steps:
            if step.step_id not in [r.step_id for r in step_results_ordered]:
                status = scheduler.get_step_status(step.step_id)
                fail_reason = scheduler._step_failure_reasons.get(step.step_id)
                step_res = PlanStepExecutionResult(
                    step_id=step.step_id,
                    step_index=step.step_index,
                    action_type=step.action_type,
                    status=status,
                    failure_reason=fail_reason,
                    failure_code="BLOCKED_BY_PREDECESSOR" if status == PlanStepExecutionStatus.BLOCKED else ("CANCELLED" if status == PlanStepExecutionStatus.CANCELLED else None),
                    dependencies=step.dependencies,
                    start_time_utc=datetime.now(timezone.utc),
                    end_time_utc=datetime.now(timezone.utc),
                    duration_ms=0.0,
                )
                step_results_ordered.append(step_res)
                plan_ctx.record_step_result(step_res)

        # 5. Compute Aggregate Plan Execution Result
        t_end = time.perf_counter()
        total_ms = (t_end - t_start) * 1000.0
        end_utc = datetime.now(timezone.utc)

        completed_count = sum(1 for s in current_plan.steps if scheduler.get_step_status(s.step_id) == PlanStepExecutionStatus.SUCCEEDED)
        failed_count = sum(1 for s in current_plan.steps if scheduler.get_step_status(s.step_id) == PlanStepExecutionStatus.FAILED)
        blocked_count = sum(1 for s in current_plan.steps if scheduler.get_step_status(s.step_id) == PlanStepExecutionStatus.BLOCKED)
        skipped_count = sum(1 for s in current_plan.steps if scheduler.get_step_status(s.step_id) == PlanStepExecutionStatus.SKIPPED)
        cancelled_count = sum(1 for s in current_plan.steps if scheduler.get_step_status(s.step_id) == PlanStepExecutionStatus.CANCELLED)
        unsupported_count = sum(1 for s in current_plan.steps if scheduler.get_step_status(s.step_id) == PlanStepExecutionStatus.UNSUPPORTED)

        is_all_success = scheduler.all_succeeded

        if is_all_success:
            final_status = PlanExecutionStatus.SUCCEEDED
            plan_fail_code = None
            plan_fail_msg = None
        elif cancelled_count > 0 or plan_ctx.is_cancelled or (plan_ctx.raw_context.last_preemption_record is not None):
            final_status = PlanExecutionStatus.CANCELLED
            plan_fail_code = "PLAN_CANCELLED" if not plan_ctx.raw_context.last_preemption_record else plan_ctx.raw_context.last_preemption_record.reason.value
            plan_fail_msg = plan_ctx.raw_context.cancellation_message or "Plan execution was cancelled or preempted"
        elif unsupported_count > 0:
            final_status = PlanExecutionStatus.UNSUPPORTED
            plan_fail_code = "UNSUPPORTED_PLAN_STEP"
            unsupported_steps = [r for r in step_results_ordered if r.status == PlanStepExecutionStatus.UNSUPPORTED]
            plan_fail_msg = unsupported_steps[0].failure_reason if unsupported_steps else "Plan contains unsupported steps"
        elif blocked_count > 0 and failed_count == 0:
            final_status = PlanExecutionStatus.BLOCKED
            plan_fail_code = "PLAN_BLOCKED"
            plan_fail_msg = "Plan execution blocked due to unresolved step dependencies"
        else:
            final_status = PlanExecutionStatus.FAILED
            first_failed = next((r for r in step_results_ordered if r.status == PlanStepExecutionStatus.FAILED), None)
            plan_fail_code = first_failed.failure_code if first_failed else "PLAN_EXECUTION_FAILED"
            plan_fail_msg = first_failed.failure_reason if first_failed else "One or more plan steps failed"

        replan_records = self._replanner.history.records if self._replanner else []

        return PlanExecutionResult(
            plan_id=current_plan.plan_id,
            task_id=effective_task_id,
            final_status=final_status,
            is_success=is_all_success,
            total_steps=len(current_plan.steps),
            completed_steps=completed_count,
            failed_steps=failed_count,
            blocked_steps=blocked_count,
            skipped_steps=skipped_count,
            step_results=step_results_ordered,
            start_time_utc=start_utc,
            end_time_utc=end_utc,
            elapsed_duration_ms=total_ms,
            failure_reason=plan_fail_msg,
            failure_code=plan_fail_code,
            preemption_record=plan_ctx.raw_context.last_preemption_record,
            diagnostics={
                "completed_count": completed_count,
                "failed_count": failed_count,
                "blocked_count": blocked_count,
                "cancelled_count": cancelled_count,
                "unsupported_count": unsupported_count,
                "total_replans": len(replan_records),
                "successful_replans": self._replanner.successful_replans if self._replanner else 0,
                "replan_history": [r.model_dump() for r in replan_records],
            },
        )
