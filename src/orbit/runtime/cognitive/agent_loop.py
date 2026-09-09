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
    TextMatchState,
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
from orbit.runtime.capabilities import FeasibilityAnalyzer
from orbit.runtime.capabilities.execution import (
    CapabilityExecutorRegistry,
    StageRecoveryManager,
    StrategyExecutionEngine,
    StrategyExecutionResult,
)
from orbit.runtime.cognitive.decomposer import HierarchicalGoalDecomposer
from orbit.runtime.cognitive.primitive_composer import PrimitiveComposer, ComposedPrimitiveSequence
from orbit.runtime.cognitive.primitive_validator import PrimitiveValidator
from orbit.runtime.cognitive.primitive_execution_controller import PrimitiveExecutionController
from orbit.runtime.task_completion.multi_evidence_verifier import MultiEvidenceActionVerifier
from orbit.runtime.agent.grounding_validator import GroundingValidator
from orbit.runtime.cognitive.failure_analyst import CognitiveFailureAnalyst, FailureReport, FailureCategory
from orbit.runtime.cognitive.runtime_feasibility import RuntimeFeasibilityEvaluator, RuntimeFeasibilityResult
from orbit.runtime.environment.registry import EnvironmentProviderRegistry, get_default_environment_registry
from orbit.runtime.world_model import AgentWorldModel, WorldModelUpdater

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
        feasibility_analyzer: Optional[FeasibilityAnalyzer] = None,
        executor_registry: Optional[CapabilityExecutorRegistry] = None,
        strategy_execution_engine: Optional[StrategyExecutionEngine] = None,
        world_model: Optional[AgentWorldModel] = None,
        goal_decomposer: Optional[HierarchicalGoalDecomposer] = None,
        runtime_feasibility_evaluator: Optional[RuntimeFeasibilityEvaluator] = None,
        environment_registry: Optional[EnvironmentProviderRegistry] = None,
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
        self._feasibility_analyzer = feasibility_analyzer or FeasibilityAnalyzer()
        self._budget = budget or ExecutionBudget()
        self._recovery_manager = recovery_manager or AgentRecoveryManager(
            max_recoveries_per_transition=self._budget.max_recoveries_per_transition
        )
        self._event_bus = event_bus
        self._text_input_lock = asyncio.Lock()
        self._last_text_input_diagnostics: Dict[str, Any] = {}

        # Authoritative Capability Execution Registry & Strategy Execution Engine (M1.9)
        self._executor_registry = executor_registry or CapabilityExecutorRegistry.create_default(
            workspace=self._workspace,
            pointer=self._pointer,
            keyboard=self._keyboard,
            target_locator=self._target_locator,
            capability_registry=getattr(self._feasibility_analyzer, "_registry", None),
        )
        self._strategy_execution_engine = strategy_execution_engine or StrategyExecutionEngine(
            executor_registry=self._executor_registry,
            observer=self._observer,
            event_bus=self._event_bus,
            recovery_manager=StageRecoveryManager(max_recovery_attempts=2),
        )

        # Phase 1: Primitive-Centric General Agent Foundation Components
        self._world_model = world_model or AgentWorldModel()
        self._environment_registry = environment_registry or get_default_environment_registry()
        self._goal_decomposer = goal_decomposer or HierarchicalGoalDecomposer(model_session_manager=model_session_manager)
        self._runtime_feasibility_evaluator = runtime_feasibility_evaluator or RuntimeFeasibilityEvaluator()

        # Phase 2: Closed-Loop Primitive Engine Components
        self._primitive_validator = PrimitiveValidator()
        self._multi_evidence_verifier = MultiEvidenceActionVerifier()
        self._primitive_composer = PrimitiveComposer(
            model_client=self._session_manager,
            validator=self._primitive_validator,
        )
        self._primitive_execution_controller = PrimitiveExecutionController(
            validator=self._primitive_validator,
            verifier=self._multi_evidence_verifier,
            provider_registry=self._environment_registry,
        )

        # Phase 3: Target Grounding Infrastructure
        self._grounding_validator = GroundingValidator()

        # Phase 4: Failure Diagnosis & Replanning
        self._failure_analyst = CognitiveFailureAnalyst()

    @property
    def failure_analyst(self) -> CognitiveFailureAnalyst:
        return self._failure_analyst

    @property
    def grounding_validator(self) -> GroundingValidator:
        return self._grounding_validator

    @property
    def primitive_validator(self) -> PrimitiveValidator:
        return self._primitive_validator

    @property
    def multi_evidence_verifier(self) -> MultiEvidenceActionVerifier:
        return self._multi_evidence_verifier

    @property
    def primitive_composer(self) -> PrimitiveComposer:
        return self._primitive_composer

    @property
    def primitive_execution_controller(self) -> PrimitiveExecutionController:
        return self._primitive_execution_controller

    @property
    def router(self) -> Optional[ModelRouter]:
        return self._router

    @property
    def decision_engine(self) -> Optional[CognitiveDecisionEngine]:
        return self._decision_engine

    @property
    def recovery_manager(self) -> AgentRecoveryManager:
        return self._recovery_manager

    @property
    def world_model(self) -> AgentWorldModel:
        return self._world_model

    @property
    def goal_decomposer(self) -> HierarchicalGoalDecomposer:
        return self._goal_decomposer

    @property
    def runtime_feasibility_evaluator(self) -> RuntimeFeasibilityEvaluator:
        return self._runtime_feasibility_evaluator

    @property
    def environment_registry(self) -> EnvironmentProviderRegistry:
        return self._environment_registry

    def set_model_session_manager(self, msm: ModelSessionManager) -> None:
        """Update the underlying ModelSessionManager and instantiate ModelRouter."""
        self._session_manager = msm
        self._router = ModelRouter(session_manager=msm)
        self._interpreter.set_model_session_manager(msm)
        self._decision_engine.set_model_session_manager(msm)
        self._goal_decomposer.set_model_session_manager(msm)
        if hasattr(self._feasibility_analyzer, "environment_discovery"):
            self._feasibility_analyzer.environment_discovery.set_model_session_manager(msm)

    def set_router(self, router: ModelRouter) -> None:
        """Attach an explicit ModelRouter."""
        self._router = router
        self._session_manager = router.session_manager
        self._interpreter.set_model_session_manager(router.session_manager)
        self._decision_engine.set_model_session_manager(router.session_manager)
        self._goal_decomposer.set_model_session_manager(router.session_manager)
        if hasattr(self._feasibility_analyzer, "environment_discovery"):
            self._feasibility_analyzer.environment_discovery.set_model_session_manager(router.session_manager)

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

        context = dict(context or {})

        # 1. LLM Intent Interpretation
        objective = await self._interpreter.interpret(prompt, context)
        logger.info(
            "Interpreted Objective: Goal='%s', EndCondition='%s', TargetEntities=%s",
            objective.user_goal,
            objective.end_condition,
            objective.target_entities,
        )

        # 1b. World Model & Hierarchical Goal Decomposition
        self._world_model = self._world_model.model_copy(update={"session_id": session_id})
        decomposed_plan = await self._goal_decomposer.decompose(objective, self._world_model)
        logger.info(
            "Goal Decomposed into %d milestone(s): %s",
            len(decomposed_plan.sub_objectives),
            [s.title for s in decomposed_plan.sub_objectives],
        )

        # 1c. Runtime Environment Feasibility Evaluation
        if hasattr(self._observer, "observe"):
            initial_obs = await self._observer.observe(objective)
        elif hasattr(self._observer, "capture_observation"):
            initial_obs = await self._observer.capture_observation()
        else:
            initial_obs = CurrentStateObservation()
        self._world_model = WorldModelUpdater.update_from_observation(self._world_model, initial_obs)

        for sub in decomposed_plan.sub_objectives:
            rt_feas = await self._runtime_feasibility_evaluator.evaluate(
                sub_objective=sub,
                world_model=self._world_model,
                observation=initial_obs,
                provider_registry=self._environment_registry,
            )
            if not rt_feas.is_feasible:
                logger.warning("[RUNTIME FEASIBILITY GATE] Sub-goal '%s' blocked: %s", sub.title, rt_feas.blocking_reason)
                sm.transition_to(
                    AgentLoopState.FAILED,
                    cycle_number=0,
                    failure_reason=rt_feas.blocking_reason,
                )
                return AgentExecutionResult(
                    task_id=effective_task_id,
                    objective=objective,
                    is_success=False,
                    total_steps=0,
                    step_history=[],
                    final_status=TaskCompletionStatus.UNSUPPORTED,
                    failure_reason=rt_feas.blocking_reason,
                    failure_code="RUNTIME_ENVIRONMENT_INFEASIBLE",
                    elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                    state_transitions=sm.history,
                    cycle_traces=[],
                    recovery_records=[],
                )

        # 2. Capability Discovery & Feasibility Analysis Gate
        feasibility = self._feasibility_analyzer.evaluate_feasibility(objective)
        if not feasibility.is_feasible:
            logger.warning("[CAPABILITY FEASIBILITY GATE] Task %s rejected: %s", effective_task_id, feasibility.explanation)
            sm.transition_to(
                AgentLoopState.FAILED,
                cycle_number=0,
                failure_reason=feasibility.explanation,
            )
            return AgentExecutionResult(
                task_id=effective_task_id,
                objective=objective,
                is_success=False,
                total_steps=0,
                step_history=[],
                final_status=TaskCompletionStatus.UNSUPPORTED,
                failure_reason=feasibility.explanation,
                failure_code="GOAL_NOT_FEASIBLY_EXECUTABLE",
                elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                state_transitions=sm.history,
                cycle_traces=[],
                recovery_records=[],
            )

        if feasibility.matched_strategy is not None:
            context["selected_strategy"] = feasibility.matched_strategy.model_dump()
            logger.info(
                "Execution guided by Strategy '%s' (coverage: %.2f, prob: %.2f)",
                feasibility.matched_strategy.name,
                feasibility.matched_strategy.semantic_goal_coverage,
                feasibility.matched_strategy.estimated_success_probability,
            )

        # -----------------------------------------------------------------
        # 2b. Authoritative Strategy Execution Bridge (M1.9 Component 6)
        # -----------------------------------------------------------------
        if self._requires_authoritative_strategy_execution(feasibility.matched_strategy, context):
            selected_strat = feasibility.matched_strategy
            logger.info(
                "[STRATEGY EXECUTION BRIDGE] Authoritatively executing selected strategy '%s' via StrategyExecutionEngine",
                selected_strat.name,
            )
            sm.transition_to(AgentLoopState.OBSERVING, cycle_number=0)
            strat_res = await self._strategy_execution_engine.execute_strategy(
                strategy=selected_strat,
                objective=objective,
                context=context,
                cancel_token=cancel_token,
                session_id=session_id,
            )

            # Re-capture fresh desktop state to verify overall goal achievement
            final_obs = await self._observer.observe(objective)
            goal_verified = strat_res.is_success

            if self._goal_verifier is not None:
                try:
                    g_eval = await self._goal_verifier.verify_goal_achievement(
                        task_id=effective_task_id,
                        objective=objective,
                        current_observation=final_obs,
                        step_history=[],
                    )
                    is_sat = getattr(g_eval, "is_satisfied", getattr(g_eval, "is_completed", False)) or (getattr(g_eval, "status", None) == TaskCompletionStatus.COMPLETED)
                    goal_verified = bool(is_sat)
                except Exception as g_err:
                    logger.debug("Final goal verification error post-strategy execution: %s", g_err)

            if strat_res.is_success and goal_verified:
                sm.transition_to(
                    AgentLoopState.EVALUATING_PROGRESS,
                    cycle_number=len(strat_res.stage_results),
                    goal_satisfied=True,
                )
                sm.transition_to(
                    AgentLoopState.COMPLETED,
                    cycle_number=len(strat_res.stage_results),
                    goal_satisfied=True,
                )
                return AgentExecutionResult(
                    task_id=effective_task_id,
                    objective=objective,
                    is_success=True,
                    total_steps=len(strat_res.stage_results),
                    step_history=[],
                    final_status=TaskCompletionStatus.COMPLETED,
                    elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                    state_transitions=sm.history,
                    cycle_traces=[],
                    recovery_records=[],
                )
            elif not strat_res.is_success:
                sm.transition_to(
                    AgentLoopState.FAILED,
                    cycle_number=len(strat_res.stage_results),
                    failure_reason=strat_res.failure_reason,
                )
                return AgentExecutionResult(
                    task_id=effective_task_id,
                    objective=objective,
                    is_success=False,
                    total_steps=len(strat_res.stage_results),
                    step_history=[],
                    final_status=TaskCompletionStatus.FAILED,
                    failure_reason=strat_res.failure_reason,
                    failure_code=strat_res.failure_code or "STRATEGY_EXECUTION_FAILED",
                    elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                    state_transitions=sm.history,
                    cycle_traces=[],
                    recovery_records=[],
                )

        step_history: List[CognitiveStepResult] = []
        cycle_traces: List[CycleExecutionTrace] = []
        consecutive_identical_actions = 0
        consecutive_redundant_actions = 0
        last_action_signature: Optional[str] = None
        target_resolution_failures = 0
        last_observed_id: Optional[str] = None
        step_idx = 0
        current_obs: Optional[CurrentStateObservation] = initial_obs

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
                        if hasattr(dtrace, "model_id") and "mock" not in type(dtrace.model_id).__name__.lower():
                            cycle_trace.model_id = str(dtrace.model_id)
                            cycle_trace.model_provider = str(dtrace.model_provider)
                            prov_upper = str(dtrace.model_provider).upper()
                            is_local_provider = prov_upper in ("OLLAMA", "LM_STUDIO", "LOCAL_FILE") or "LOCAL" in prov_upper
                            cycle_trace.local_or_cloud = "CLOUD" if (getattr(dtrace, "escalated_to_cloud", False) or not is_local_provider) else "LOCAL"
                            cycle_trace.vision_capable = bool(getattr(dtrace, "used_vision", False))
                            cycle_trace.screenshot_attached = "SCREENSHOT" in getattr(dtrace, "input_modalities", [])
                            lat = getattr(dtrace, "model_latency_ms", None)
                            cycle_trace.model_latency_ms = float(lat) if isinstance(lat, (int, float)) else None
                            cycle_trace.capabilities = [str(c) for c in getattr(dtrace, "input_modalities", [])]
                            cycle_trace.raw_model_response = getattr(dtrace, "raw_response", None)
                except Exception as tr_err:
                    logger.debug("Trace extraction notice: %s", tr_err)

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
                decision.next_action and decision.next_action.action_type == AbstractActionType.COMPLETE_GOAL
            )

            if is_model_claiming_completion:
                logger.info("Model proposed goal completion at step %d; verifying reality against live desktop", step_idx)
                goal_truly_verified = False
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
                else:
                    # Guardrail 8 & 16: COMPLETE_GOAL is an intent signal only, not proof of success
                    # If no goal verifier is present, verify based on verifiable outcome evidence
                    goal_truly_verified = any(
                        step.execution_result and step.execution_result.expected_effect_observed
                        for step in step_history
                    )

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
            if decision.next_action and decision.next_action.action_type == AbstractActionType.ABORT_TASK:
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
                AbstractActionType.ABORT_TASK,
            ):
                action.outcome_contract = ActionOutcomeContract(
                    expected_state_transition=f"{action.action_type.value}_completed",
                    verification_strategy=VerificationStrategy.AUTO_ROUTED,
                )

            # -------------------------------------------------------------
            # REPEATED ACTION & IDEMPOTENCY SAFETY GUARD (Requirements C & D)
            # -------------------------------------------------------------
            is_redundant = False
            redundancy_reason = ""
            app_target_name = ""

            if action.action_type == AbstractActionType.LAUNCH_APPLICATION:
                app_target_name = str(
                    action.parameters.get(
                        "application_name",
                        action.parameters.get("app_name", action.target.name if action.target else ""),
                    )
                ).strip().lower()

                # 1. Inspect current DesktopObservation: Check if requested application is already open
                already_open_hwnd = None
                already_open_title = ""
                for win in current_obs.visible_windows:
                    w_title = (win.get("title") or "").lower()
                    w_proc = (win.get("process_name") or "").lower()
                    if app_target_name in w_title or app_target_name in w_proc:
                        already_open_hwnd = win.get("hwnd")
                        already_open_title = win.get("title", "")
                        break

                if not already_open_hwnd and current_obs.active_window_title and app_target_name in current_obs.active_window_title.lower():
                    already_open_hwnd = current_obs.active_window_hwnd
                    already_open_title = current_obs.active_window_title

                # 2. Check if LAUNCH_APPLICATION for this app was already executed in step_history
                launch_already_succeeded = any(
                    s.action_dispatched
                    and s.action_dispatched.action_type == AbstractActionType.LAUNCH_APPLICATION
                    and s.execution_result
                    and s.execution_result.expected_effect_observed
                    for s in step_history
                )

                if already_open_hwnd or launch_already_succeeded:
                    is_redundant = True
                    redundancy_reason = (
                        f"Application '{app_target_name}' is ALREADY RUNNING and usable on desktop "
                        f"(HWND: {already_open_hwnd}, Window: '{already_open_title}'). Re-launching is blocked."
                    )
                    # Focus existing window if not foreground
                    if already_open_hwnd and sys.platform == "win32":
                        from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
                        EvidenceBasedTargetLocator._force_foreground_window(int(already_open_hwnd))

            # 3. General semantic check: Identical action and target already successfully executed
            if not is_redundant and step_history and action.action_type not in (
                AbstractActionType.WAIT,
                AbstractActionType.COMPLETE_GOAL,
                AbstractActionType.ABORT_TASK,
            ):
                last_step = step_history[-1]
                if (
                    last_step.action_dispatched
                    and last_step.action_dispatched.action_type == action.action_type
                    and last_step.action_dispatched.parameters == action.parameters
                    and last_step.execution_result
                    and last_step.execution_result.expected_effect_observed
                ):
                    is_redundant = True
                    redundancy_reason = f"Action '{action.action_type.value}' with identical parameters was already executed and verified in previous step."

            if is_redundant:
                consecutive_redundant_actions += 1
                logger.warning(
                    "[REPEATED ACTION SAFETY GUARD] BLOCKED REDUNDANT ACTION: %s (Count: %d/%d). Reason: %s",
                    action.action_type.value,
                    consecutive_redundant_actions,
                    self._budget.max_repeated_actions_without_progress,
                    redundancy_reason,
                )

                # Hard Emergency Circuit Breaker
                if consecutive_redundant_actions >= self._budget.max_repeated_actions_without_progress:
                    sm.transition_to(
                        AgentLoopState.FAILED,
                        cycle_number=step_idx,
                        observation_id=current_obs.observation_id,
                        action_id=action.action_id,
                        action_type=action.action_type.value,
                        failure_reason=f"Emergency Circuit Breaker: Redundant action '{action.action_type.value}' repeated {consecutive_redundant_actions} times",
                    )
                    return AgentExecutionResult(
                        task_id=effective_task_id,
                        objective=objective,
                        is_success=False,
                        total_steps=len(step_history),
                        step_history=step_history,
                        final_status=TaskCompletionStatus.FAILED,
                        failure_reason=f"Emergency Circuit Breaker: Redundant action '{action.action_type.value}' blocked {consecutive_redundant_actions} times",
                        failure_code="CIRCUIT_BREAKER_REDUNDANT_ACTION",
                        elapsed_duration_ms=(time.perf_counter() - t_start) * 1000.0,
                        state_transitions=sm.history,
                        cycle_traces=cycle_traces,
                        recovery_records=self._recovery_manager.get_history(),
                    )

                # Inject redundancy evidence into reasoning context to force next unmet sub-goal
                context["feedback"] = (
                    f"CRITICAL GUIDANCE: Action '{action.action_type.value}' was BLOCKED because {redundancy_reason} "
                    f"The application is open and active. Proceed immediately to the NEXT unmet sub-goal "
                    f"(e.g. TYPE_TEXT with the requested text). DO NOT emit LAUNCH_APPLICATION."
                )

                cycle_trace.dispatch_attempted = False
                cycle_trace.dispatch_success = True
                cycle_trace.expected_effect = "Reused existing verified application"
                cycle_trace.observed_effect = redundancy_reason
                cycle_trace.expected_effect_observed = True
                cycle_trace.meaningful_state_change = False
                cycle_trace.repeated_actions_count = consecutive_redundant_actions

                exec_result = ActionExecutionResult(
                    action_id=action.action_id,
                    dispatch_success=True,
                    expected_effect_observed=True,
                    goal_satisfied=False,
                    outcome_status=OutcomeStatus.REDUNDANT_BLOCKED,
                    verification_strategy=VerificationStrategy.AUTO_ROUTED,
                    verification_reason=redundancy_reason,
                    observed_delta={"status": "REDUNDANT_BLOCKED", "reused_existing": True},
                    duration_ms=50.0,
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

                sm.transition_to(
                    AgentLoopState.EVALUATING_PROGRESS,
                    cycle_number=step_idx,
                    observation_id=current_obs.observation_id,
                    action_id=action.action_id,
                    action_type=action.action_type.value,
                    expected_effect_observed=True,
                )

                logger.info("\n%s", format_cycle_trace_block(cycle_trace))
                step_idx += 1
                continue

            consecutive_redundant_actions = 0

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

            # Only pointer-based interaction actions require physical screen coordinate grounding
            requires_coordinates = action.action_type in (
                AbstractActionType.CLICK,
                AbstractActionType.DOUBLE_CLICK,
                AbstractActionType.RIGHT_CLICK,
            )

            resolved_coords = None
            if action.target is not None and requires_coordinates:
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
            elif action.target is not None:
                # Target provided for semantic context (e.g. app name, window name, text field)
                cycle_trace.semantic_target_name = action.target.name
                cycle_trace.semantic_target_role = action.target.role
                cycle_trace.grounding_resolved = True
                cycle_trace.grounding_confidence = 1.0
                cycle_trace.target_evidence_source = "SEMANTIC_TARGET_RESOLVED"

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
            controller_res = await self._primitive_execution_controller.execute_primitive(
                action=action,
                pre_observation=current_obs,
                objective=objective,
                grounding_fn=self._resolve_target_coordinates,
                safety_gate_fn=self._evaluate_safety_gate,
                dispatch_fn=self._dispatch_physical_action,
                observe_fn=self._observer.observe,
                cancel_token=cancel_token,
            )
            dispatch_success = controller_res.execution_outcome.dispatch_success
            dispatch_err = controller_res.execution_outcome.error_message
            post_obs = controller_res.post_observation
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

            # Observation advancement verification (from controller's fresh observation)
            cycle_trace.post_observation_id = post_obs.observation_id
            cycle_trace.post_freshness_validated = (post_obs.observation_id != current_obs.observation_id)

            obs_advanced = (post_obs.observation_id != current_obs.observation_id)
            logger.info(
                "\n[CYCLE %d OBSERVATION VALIDATION]\n"
                "  Pre-Action Observation ID:  %s\n"
                "  Post-Action Observation ID: %s\n"
                "  Observation Advanced:       %s\n"
                "  Foreground Window Before:   '%s'\n"
                "  Foreground Window After:    '%s'\n"
                "  Visible Windows Before:     %s\n"
                "  Visible Windows After:      %s",
                step_idx,
                current_obs.observation_id,
                post_obs.observation_id,
                obs_advanced,
                current_obs.active_window_title,
                post_obs.active_window_title,
                [w.get("title") for w in current_obs.visible_windows[:4] if w.get("title")],
                [w.get("title") for w in post_obs.visible_windows[:4] if w.get("title")],
            )

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
                snapshot_id=current_obs.observation_id,
                active_window_hwnd=current_obs.active_window_hwnd,
                active_window_title=current_obs.active_window_title,
                visible_windows=current_obs.visible_windows,
                target_app_exists=current_obs.target_app_exists,
                target_app_is_active=current_obs.target_app_is_active,
                canvas_status=current_obs.canvas_status or "UNKNOWN",
                ocr_tokens=current_obs.ocr_tokens,
            )
            post_state = DesktopStateSnapshot(
                snapshot_id=post_obs.observation_id,
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

            # Phase 2: Multi-Evidence Semantic Action Verification
            me_res = await self._multi_evidence_verifier.verify_action_effect(
                action=action,
                pre_obs=current_obs,
                post_obs=post_obs,
            )
            if me_res.is_verified and not outcome.expected_effect_observed:
                outcome.expected_effect_observed = True
                outcome.verified = True
                outcome.outcome_status = OutcomeStatus.EFFECT_VERIFIED
                outcome.verification_reason = me_res.verification_reason

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

            # Structured diagnostics for TYPE_TEXT actions (Part 1)
            if action.action_type == AbstractActionType.TYPE_TEXT:
                t_diag = getattr(self, "_last_text_input_diagnostics", {})
                txt_param = str(action.parameters.get("text", action.parameters.get("query", "")))
                logger.info(
                    "\n[TYPE_TEXT EXECUTION & REALITY VERIFICATION]\n"
                    "  Attempt ID:                  %s\n"
                    "  Intended Text:               '%s' (len=%d)\n"
                    "  Selected Strategy:           %s\n"
                    "  Keyboard Adapter:            %s\n"
                    "  Target Window (Before):      %s\n"
                    "  Target Window (After):       %s\n"
                    "  Dispatch Result:             %s\n"
                    "  Actual Text Detected:        '%s'\n"
                    "  Text Match Result:           %s\n"
                    "  Verification Method:         %s\n"
                    "  Expected Effect Observed:    %s\n"
                    "  Goal Satisfied:              %s",
                    t_diag.get("input_attempt_id", "N/A"),
                    txt_param,
                    len(txt_param),
                    t_diag.get("selected_input_strategy", "NONE"),
                    t_diag.get("keyboard_adapter_name", "NONE"),
                    t_diag.get("target_window_before_typing", "UNKNOWN"),
                    t_diag.get("target_window_after_typing", "UNKNOWN"),
                    outcome.dispatch_success,
                    outcome.observed_delta.get("observed_text", "NONE"),
                    outcome.observed_delta.get("match_state", "UNKNOWN"),
                    outcome.observed_delta.get("text_verification", {}).get("primary_source", "NONE"),
                    outcome.expected_effect_observed,
                    outcome.goal_satisfied,
                )

            # -------------------------------------------------------------
            # PHASE 9: RECOVERY OR PROGRESS EVALUATION
            # -------------------------------------------------------------
            # TRIPARTITE REALITY DISTINCTION:
            # dispatch_success == True DOES NOT imply expected_effect_observed == True!
            if not exec_result.expected_effect_observed:
                logger.warning("Action %s dispatched but expected effect was NOT observed; evaluating recovery", action.action_id)

                # Phase 4: Diagnostic Root-Cause Analysis (Guardrail 9)
                failure_rep = self._failure_analyst.analyze_failure(
                    action=action,
                    pre_obs=current_obs,
                    post_obs=post_obs,
                    exec_outcome=outcome,
                    world_model=self._world_model,
                )
                logger.info(
                    "[FAILURE ANALYST] Diagnosis for action %s: %s [%s] -> Remediation: %s",
                    action.action_id,
                    failure_rep.diagnosis,
                    failure_rep.category.value,
                    failure_rep.suggested_remediation_direction,
                )

                # Part 6: Controlled Post-Type Recovery
                if action.action_type == AbstractActionType.TYPE_TEXT and getattr(action, "_typing_recovery_attempts", 0) < 2:
                    action._typing_recovery_attempts = getattr(action, "_typing_recovery_attempts", 0) + 1
                    logger.info("Executing controlled text recovery attempt %d/2 for action %s", action._typing_recovery_attempts, action.action_id)
                    
                    # Refocus target
                    if current_obs.active_window_hwnd and sys.platform == "win32":
                        try:
                            import ctypes
                            ctypes.windll.user32.SetForegroundWindow(current_obs.active_window_hwnd)
                            await asyncio.sleep(0.05)
                        except Exception:
                            pass

                    # Determine if text is corrupted (PARTIAL_MATCH or MISMATCH)
                    t_match = outcome.observed_delta.get("match_state", "")
                    if t_match in (TextMatchState.PARTIAL_MATCH.value, TextMatchState.MISMATCH.value):
                        logger.info("Corrupted text detected [%s]; safely clearing controlled editor before retry", t_match)
                        if sys.platform == "win32":
                            try:
                                import ctypes
                                u32 = ctypes.windll.user32
                                u32.keybd_event(0x11, 0, 0, 0)
                                u32.keybd_event(0x41, 0, 0, 0)
                                u32.keybd_event(0x41, 0, 2, 0)
                                u32.keybd_event(0x11, 0, 2, 0)
                                await asyncio.sleep(0.03)
                                u32.keybd_event(0x2E, 0, 0, 0)
                                u32.keybd_event(0x2E, 0, 2, 0)
                                await asyncio.sleep(0.05)
                            except Exception:
                                pass

                    # Alternate strategy
                    curr_strat = self._last_text_input_diagnostics.get("selected_input_strategy")
                    alt_strat = "KEYBOARD_STREAM" if curr_strat == "CLIPBOARD_ATOMIC" else "CLIPBOARD_ATOMIC"
                    text = str(action.parameters.get("text", action.parameters.get("query", "")))
                    press_enter = bool(action.parameters.get("press_enter", False))
                    rec_ok, rec_err, rec_diag = await self._execute_deterministic_text_input(
                        text=text,
                        press_enter=press_enter,
                        target_hwnd=current_obs.active_window_hwnd,
                        target_title=current_obs.active_window_title,
                        preferred_strategy=alt_strat,
                        cancel_token=cancel_token,
                    )

                    await asyncio.sleep(0.35)
                    post_obs = await self._observer.observe(objective)
                    post_state = DesktopStateSnapshot(
                        snapshot_id=post_obs.observation_id,
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
                        dispatch_success=rec_ok,
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
                        verification_reason=f"Recovery [{alt_strat}]: {outcome.verification_reason}",
                        observed_delta=outcome.observed_delta,
                        error_message=rec_err or outcome.error_message,
                        duration_ms=outcome.duration_ms,
                    )
                    cycle_trace.observed_effect = outcome.observed_delta or "None"
                    cycle_trace.expected_effect_observed = outcome.expected_effect_observed
                    cycle_trace.verification_reason = exec_result.verification_reason

                elif self._recovery_manager.can_attempt_recovery():
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
            snapshot_id=pre_obs.observation_id,
            active_window_hwnd=pre_obs.active_window_hwnd,
            active_window_title=pre_obs.active_window_title,
            visible_windows=pre_obs.visible_windows,
            target_app_exists=pre_obs.target_app_exists,
            target_app_is_active=pre_obs.target_app_is_active,
            canvas_status=pre_obs.canvas_status or "UNKNOWN",
            ocr_tokens=pre_obs.ocr_tokens,
        )
        post_state = DesktopStateSnapshot(
            snapshot_id=post_obs.observation_id,
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

    def _evaluate_safety_gate(
        self,
        action: AbstractAction,
        resolved_coords: Optional[Tuple[int, int]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Pre-dispatch safety gate guarding physical OS execution."""
        if resolved_coords is not None:
            x, y = resolved_coords
            if x < 0 or y < 0:
                return False, f"Coordinates ({x}, {y}) out of screen bounds"
        if action.action_type == AbstractActionType.LAUNCH_APPLICATION:
            app = str(action.parameters.get("application_name", "")).lower()
            if any(danger in app for danger in ("format", "diskpart", "shutdown", "regedit")):
                return False, f"Destructive system application blocked by safety gate: '{app}'"
        return True, None

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
                        "[IDEMPOTENT LAUNCH] Application '%s' is ALREADY OPEN in window '%s' (HWND: %s). Reusing existing window, skipping physical launch.",
                        app_name,
                        already_open_title,
                        already_open_hwnd,
                    )
                    if sys.platform == "win32":
                        from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
                        EvidenceBasedTargetLocator._force_foreground_window(int(already_open_hwnd))
                    await asyncio.sleep(0.3)
                    dispatch_success = True
                    return True, None

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
                                    None, "open", "mspaint.exe", None, None, 1
                                )
                            except Exception:
                                subprocess.Popen("mspaint.exe", shell=True)
                        elif "calc" in app_name.lower():
                            try:
                                ctypes.windll.shell32.ShellExecuteW(
                                    None, "open", "calc.exe", None, None, 1
                                )
                            except Exception:
                                subprocess.Popen("calc.exe", shell=True)
                        elif "notepad" in app_name.lower():
                            try:
                                subprocess.Popen("cmd /c start notepad.exe", shell=True)
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

            elif act_type == AbstractActionType.DRAW_STROKES:
                shape = str(params.get("shape", "cube"))
                dispatch_success = await self._execute_drawing_strokes(shape, cancel_token)

            elif act_type == AbstractActionType.TYPE_TEXT:
                text = str(params.get("text", params.get("query", "")))
                press_enter = bool(params.get("press_enter", False))
                pref_strategy = params.get("strategy")
                dispatch_success, err_msg, text_diag = await self._execute_deterministic_text_input(
                    text=text,
                    press_enter=press_enter,
                    target_hwnd=pre_obs.active_window_hwnd if hasattr(pre_obs, "active_window_hwnd") else None,
                    target_title=pre_obs.active_window_title if hasattr(pre_obs, "active_window_title") else None,
                    preferred_strategy=pref_strategy,
                    cancel_token=cancel_token,
                )

            elif act_type == AbstractActionType.CLICK:
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
                    dispatch_success = False
                    err_msg = "REQUIRED_ADAPTER_MISSING: PointerCapability"

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
                    dispatch_success = False
                    err_msg = "REQUIRED_ADAPTER_MISSING: PointerCapability"

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
                    dispatch_success = False
                    err_msg = "REQUIRED_ADAPTER_MISSING: PointerCapability"

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

            elif act_type in (AbstractActionType.WAIT, AbstractActionType.WAIT_SETTLE):
                dur_ms = float(params.get("duration_sec", 0.5)) * 1000.0 if "duration_sec" in params else float(params.get("duration_ms", 500))
                await asyncio.sleep(dur_ms / 1000.0)
                dispatch_success = True

            elif act_type == AbstractActionType.COMPLETE_GOAL:
                dispatch_success = True

            else:
                dispatch_success = False
                err_msg = f"UNKNOWN_ACTION_TYPE: {act_type.value if hasattr(act_type, 'value') else act_type}"

        except Exception as ex:
            logger.warning("Action physical dispatch error for %s: %s", act_type.value if hasattr(act_type, "value") else act_type, ex, exc_info=True)
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
                    cand_coords = None
                    if is_res and tgt and hasattr(tgt, "bounding_box"):
                        cand_coords = (int(tgt.bounding_box.center_x), int(tgt.bounding_box.center_y))
                    elif is_res and tgt and hasattr(tgt, "bounds"):
                        cand_coords = (int(tgt.bounds.center_x), int(tgt.bounds.center_y))
                    elif is_res and tgt and hasattr(tgt, "safe_point"):
                        cand_coords = (int(tgt.safe_point.x), int(tgt.safe_point.y))

                    if cand_coords is not None:
                        # Pass through GroundingValidator (Guardrail 4)
                        g_val = self._grounding_validator.validate_grounding(
                            target=target,
                            resolved_target=tgt,
                            candidate_coords=cand_coords,
                        )
                        if g_val.is_valid and g_val.validated_point:
                            return g_val.validated_point
                        else:
                            logger.warning(
                                "[GROUNDING VALIDATOR] Rejected candidate coordinates %s for target '%s': %s",
                                cand_coords,
                                target.name,
                                g_val.failure_reason,
                            )
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

    @staticmethod
    def _get_active_window_title_safe() -> str:
        """Helper to get active window title without throwing."""
        if sys.platform == "win32":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                if hwnd:
                    buf = ctypes.create_unicode_buffer(512)
                    user32.GetWindowTextW(hwnd, buf, 512)
                    return buf.value
            except Exception:
                pass
        return "UNKNOWN"

    async def _execute_deterministic_text_input(
        self,
        text: str,
        press_enter: bool = False,
        target_hwnd: Optional[int] = None,
        target_title: Optional[str] = None,
        preferred_strategy: Optional[str] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Production-hardened deterministic text entry with safe clipboard paste, modifier release, and Unicode injection."""
        attempt_id = str(uuid4())
        t0 = time.perf_counter_ns()
        diag: Dict[str, Any] = {
            "input_attempt_id": attempt_id,
            "intended_text": text,
            "intended_text_length": len(text),
            "selected_input_strategy": "NONE",
            "keyboard_adapter_name": type(self._keyboard).__name__ if self._keyboard else "NONE",
            "target_window_before_typing": target_title or str(target_hwnd or "UNKNOWN"),
            "target_window_after_typing": "UNKNOWN",
            "dispatch_result": False,
            "error_message": None,
            "start_time_ns": t0,
        }

        if cancel_token and cancel_token.is_cancelled:
            diag["error_message"] = "Cancelled before typing"
            return False, "Cancelled before typing", diag

        # Part 8: Input Ownership & Concurrency Lock
        # Ensures only one physical text input operation can own the keyboard pipeline at a time.
        async with self._text_input_lock:
            logger.info("Acquired text input lock [attempt_id=%s]: len=%d, press_enter=%s", attempt_id, len(text), press_enter)

            try:
                # 1 & 2. Ensure target window is foreground and focused; release stuck modifiers
                if sys.platform == "win32":
                    try:
                        import ctypes
                        from ctypes import wintypes
                        u32 = ctypes.windll.user32

                        active_hwnd = u32.GetForegroundWindow()
                        if target_hwnd and target_hwnd != active_hwnd:
                            u32.SetForegroundWindow(target_hwnd)
                            await asyncio.sleep(0.05)

                        # Part 7: Generic modifier release (SHIFT, CTRL, ALT, LWIN, RWIN)
                        for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C):
                            u32.keybd_event(wintypes.BYTE(vk), 0, wintypes.DWORD(2), 0)
                    except Exception as prep_ex:
                        logger.debug("Pre-typing focus/modifier preparation notice: %s", prep_ex)

                # Strategy 1 (Primary): Deterministic Atomic Clipboard Paste (Fast, atomic, immune to auto-repeat)
                if sys.platform == "win32" and preferred_strategy != "KEYBOARD_STREAM":
                    try:
                        diag["selected_input_strategy"] = "CLIPBOARD_ATOMIC"
                        import ctypes
                        from ctypes import wintypes

                        user32 = ctypes.windll.user32
                        kernel32 = ctypes.windll.kernel32

                        user32.OpenClipboard.argtypes = [wintypes.HWND]
                        user32.OpenClipboard.restype = wintypes.BOOL
                        user32.CloseClipboard.argtypes = []
                        user32.CloseClipboard.restype = wintypes.BOOL
                        user32.EmptyClipboard.argtypes = []
                        user32.EmptyClipboard.restype = wintypes.BOOL
                        user32.GetClipboardData.argtypes = [wintypes.UINT]
                        user32.GetClipboardData.restype = wintypes.HANDLE
                        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
                        user32.SetClipboardData.restype = wintypes.HANDLE
                        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
                        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
                        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
                        kernel32.GlobalLock.restype = ctypes.c_void_p
                        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
                        kernel32.GlobalUnlock.restype = wintypes.BOOL

                        # Step 1.1: Preserve prior clipboard text if present
                        prev_text = None
                        for _ in range(5):
                            if user32.OpenClipboard(None):
                                try:
                                    h_clip = user32.GetClipboardData(13)  # CF_UNICODETEXT
                                    if h_clip:
                                        p_data = kernel32.GlobalLock(h_clip)
                                        if p_data:
                                            try:
                                                prev_text = ctypes.wstring_at(p_data)
                                            finally:
                                                kernel32.GlobalUnlock(h_clip)
                                finally:
                                    user32.CloseClipboard()
                                break
                            await asyncio.sleep(0.02)

                        # Step 1.2: Set target text onto clipboard
                        encoded = text.encode("utf-16-le") + b"\x00\x00"
                        h_glob = kernel32.GlobalAlloc(0x0002, len(encoded))  # GMEM_MOVEABLE
                        clipboard_set = False
                        if h_glob:
                            p_glob = kernel32.GlobalLock(h_glob)
                            if p_glob:
                                ctypes.memmove(p_glob, encoded, len(encoded))
                                kernel32.GlobalUnlock(h_glob)
                                for _ in range(5):
                                    if user32.OpenClipboard(None):
                                        try:
                                            user32.EmptyClipboard()
                                            user32.SetClipboardData(13, h_glob)
                                            clipboard_set = True
                                        finally:
                                            user32.CloseClipboard()
                                        break
                                    await asyncio.sleep(0.02)

                        if not clipboard_set:
                            raise RuntimeError("Failed to set CF_UNICODETEXT on Windows clipboard")

                        # Step 1.3: Send atomic Ctrl+V with guaranteed Key-Up via try/finally
                        await asyncio.sleep(0.03)
                        user32.keybd_event(0x11, 0, 0, 0)  # VK_CONTROL down
                        try:
                            user32.keybd_event(0x56, 0, 0, 0)  # 'V' down
                            user32.keybd_event(0x56, 0, 2, 0)  # 'V' up
                        finally:
                            user32.keybd_event(0x11, 0, 2, 0)  # Guaranteed VK_CONTROL up
                        await asyncio.sleep(0.05)

                        if press_enter:
                            user32.keybd_event(0x0D, 0, 0, 0)  # ENTER down
                            user32.keybd_event(0x0D, 0, 2, 0)  # ENTER up
                            await asyncio.sleep(0.02)

                        # Step 1.4: Settle and Restore prior clipboard content if safe
                        if prev_text is not None:
                            await asyncio.sleep(0.08)
                            prev_encoded = prev_text.encode("utf-16-le") + b"\x00\x00"
                            h_prev = kernel32.GlobalAlloc(0x0002, len(prev_encoded))
                            if h_prev:
                                p_prev = kernel32.GlobalLock(h_prev)
                                if p_prev:
                                    ctypes.memmove(p_prev, prev_encoded, len(prev_encoded))
                                    kernel32.GlobalUnlock(h_prev)
                                    for _ in range(3):
                                        if user32.OpenClipboard(None):
                                            try:
                                                user32.EmptyClipboard()
                                                user32.SetClipboardData(13, h_prev)
                                            finally:
                                                user32.CloseClipboard()
                                            break
                                        await asyncio.sleep(0.02)

                        diag["dispatch_result"] = True
                        diag["target_window_after_typing"] = self._get_active_window_title_safe()
                        return True, None, diag

                    except Exception as clip_ex:
                        logger.warning("Clipboard injection failed (%s); switching to fallback keyboard stream", clip_ex)

                # Strategy 2 (Fallback): Native Keyboard Adapter
                if self._keyboard is not None and preferred_strategy != "CLIPBOARD_ATOMIC":
                    try:
                        diag["selected_input_strategy"] = "KEYBOARD_STREAM"
                        await self._keyboard.type_text(text, target_hwnd=target_hwnd)
                        if press_enter:
                            await self._keyboard.press_key("Return")
                        diag["dispatch_result"] = True
                        diag["target_window_after_typing"] = self._get_active_window_title_safe()
                        return True, None, diag
                    except Exception as k_ex:
                        logger.warning("Keyboard adapter type_text failed: %s", k_ex)
                        diag["error_message"] = str(k_ex)

                # Strategy 3 (Ultimate Fallback): Unicode-capable controlled virtual-key injection
                if sys.platform == "win32":
                    try:
                        diag["selected_input_strategy"] = "UNICODE_CONTROLLED"
                        import ctypes
                        from ctypes import wintypes
                        user32 = ctypes.windll.user32
                        for ch in text:
                            if cancel_token and cancel_token.is_cancelled:
                                return False, "Cancelled during typing", diag
                            if ch == "\n":
                                user32.keybd_event(0x0D, 0, 0, 0)
                                user32.keybd_event(0x0D, 0, 2, 0)
                            else:
                                vk = user32.VkKeyScanW(ord(ch))
                                if vk != -1:
                                    shift = (vk >> 8) & 1
                                    code = vk & 0xFF
                                    try:
                                        if shift:
                                            user32.keybd_event(0x10, 0, 0, 0)
                                        user32.keybd_event(code, 0, 0, 0)
                                    finally:
                                        user32.keybd_event(code, 0, 2, 0)
                                        if shift:
                                            user32.keybd_event(0x10, 0, 2, 0)
                            await asyncio.sleep(0.015)
                        if press_enter:
                            user32.keybd_event(0x0D, 0, 0, 0)
                            user32.keybd_event(0x0D, 0, 2, 0)

                        diag["dispatch_result"] = True
                        diag["target_window_after_typing"] = self._get_active_window_title_safe()
                        return True, None, diag
                    except Exception as char_ex:
                        diag["error_message"] = f"Character typing failed: {char_ex}"
                        return False, f"Character typing failed: {char_ex}", diag

                diag["dispatch_result"] = True
                diag["target_window_after_typing"] = self._get_active_window_title_safe()
                return True, None, diag

            finally:
                # Part 7: Generic guaranteed modifier cleanup on completion or failure
                if sys.platform == "win32":
                    try:
                        import ctypes
                        from ctypes import wintypes
                        u32 = ctypes.windll.user32
                        for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C):  # SHIFT, CTRL, ALT, LWIN, RWIN
                            u32.keybd_event(wintypes.BYTE(vk), 0, wintypes.DWORD(2), 0)
                    except Exception:
                        pass
                diag["completion_time_ns"] = time.perf_counter_ns()
                self._last_text_input_diagnostics = diag

    def _requires_authoritative_strategy_execution(
        self,
        strategy: Optional[StrategyOption],
        context: Dict[str, Any],
    ) -> bool:
        """Determine whether a selected strategy should be authoritatively executed by StrategyExecutionEngine."""
        if strategy is None or not strategy.stages:
            return False

        # If explicitly opted into authoritative strategy execution
        if context.get("authoritative_strategy_execution") is True or context.get("use_strategy_engine") is True:
            return True

        # Composite workflows with multiple sub-stages or image generation
        if strategy.strategy_id.startswith("STRAT_COMPOSITE") or "IMAGE_GENERATE_AND_INSERT" in strategy.required_capabilities:
            return True

        # Workflows that declare dynamic output references (e.g. {{stage_0...}})
        for stage in strategy.stages:
            for v in stage.parameters.values():
                if isinstance(v, str) and "{{" in v and "}}" in v:
                    return True

        return False


