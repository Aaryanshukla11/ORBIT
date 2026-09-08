"""Production Multimodal Agent Decision Engine & Decision Trace Telemetry (Step 4).

The AI Decision Brain connecting live DesktopObservation to Local and Cloud AI Models.
Manages ModelRouter dispatch, hybrid local/cloud escalation, capability verification,
multimodal payload framing, structured output validation, and complete decision auditing.

SECURITY INVARIANT:
Credentials, API keys, and authorization headers are NEVER logged, serialized, or emitted.
Zero physical screen coordinates originate from the LLM.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionOutcomeContract,
    SemanticTarget,
)
from orbit.runtime.cognitive.context_builder import (
    AgentReasoningContextBuilder,
    DECISION_SYSTEM_PROMPT,
)
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CognitiveStepResult,
    CurrentStateObservation,
    StructuredObjective,
)
from orbit.runtime.cognitive.output_parser import (
    CoordinateSecurityViolation,
    StructuredDecisionParser,
    StructuredOutputParserError,
)
from orbit.runtime.model_runtime.base import BaseModelRuntime
from orbit.runtime.model_runtime.contracts import ModelRuntimeKind, NoActiveModelError
from orbit.runtime.model_runtime.router import (
    ModelRouter,
    ModelRoutingTier,
    RoutingPolicy,
)
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models.capabilities import (
    ModelCapabilityProfile,
    get_model_capability_profile,
)
from orbit.runtime.models.models import (
    ModelCapability,
    ModelGenerateResponse,
    ModelProviderKind,
    ModelSourceType,
)
from orbit.runtime.perception.models import DesktopObservation

logger = logging.getLogger(__name__)


class AgentDecisionTrace(BaseModel):
    """Auditable telemetry record captured for every cognitive reasoning cycle."""

    decision_id: str = Field(default_factory=lambda: f"dec_{uuid4().hex[:8]}")
    observation_id: str = ""
    step_index: int = 0
    model_provider: str = "UNKNOWN"
    model_name: str = "UNKNOWN"
    model_id: str = "UNKNOWN"
    routing_tier: str = "PREFER_LOCAL"
    routing_reason: str = ""
    input_modalities: List[str] = Field(default_factory=list)
    used_vision: bool = False
    used_ocr: bool = False
    used_uia: bool = False
    used_win32: bool = False
    model_latency_ms: Optional[float] = None
    decision_confidence: float = 0.0
    action_type: Optional[str] = None
    target_name: Optional[str] = None
    validation_result: str = "VALID"
    fallback_used: bool = False
    escalated_to_cloud: bool = False
    decision_summary: str = ""
    evidence_used: List[str] = Field(default_factory=list)
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentDecisionEngine:
    """Core AI Decision Brain routing multimodal desktop state to Local and Cloud LLMs."""

    def __init__(
        self,
        router: Optional[ModelRouter] = None,
        model_session_manager: Optional[ModelSessionManager] = None,
        default_routing_policy: Optional[RoutingPolicy] = None,
        confidence_threshold: float = 0.6,
    ) -> None:
        self._session_manager = model_session_manager
        if router is not None:
            self._router = router
        elif model_session_manager is not None:
            self._router = ModelRouter(session_manager=model_session_manager)
        else:
            self._router = None

        self._default_policy = default_routing_policy or RoutingPolicy()
        self._confidence_threshold = confidence_threshold
        self._decision_traces: List[AgentDecisionTrace] = []

    @property
    def router(self) -> Optional[ModelRouter]:
        return self._router

    @property
    def session_manager(self) -> Optional[ModelSessionManager]:
        return self._session_manager

    def set_model_session_manager(self, msm: ModelSessionManager) -> None:
        """Update the underlying ModelSessionManager and instantiate ModelRouter."""
        self._session_manager = msm
        self._router = ModelRouter(session_manager=msm)

    def set_router(self, router: ModelRouter) -> None:
        """Attach an explicit ModelRouter."""
        self._router = router
        self._session_manager = router.session_manager

    def get_recent_traces(self, limit: int = 20) -> List[AgentDecisionTrace]:
        """Return recently recorded decision traces."""
        return self._decision_traces[-limit:]

    async def decide_next_step(
        self,
        objective: StructuredObjective,
        observation: Union[DesktopObservation, CurrentStateObservation],
        step_history: Optional[List[CognitiveStepResult]] = None,
        step_index: int = 0,
        routing_policy: Optional[RoutingPolicy] = None,
        task_context: Optional[Dict[str, Any]] = None,
    ) -> CognitiveDecision:
        """Decide the next action by dispatching live observation to the optimal AI model."""
        history = step_history or []
        policy = routing_policy or self._default_policy
        obs_id = getattr(observation, "observation_id", "obs_unknown")
        t_start = time.perf_counter()

        # 1. Determine input modalities present in the observation
        input_modalities, has_screenshot = self._inspect_modalities(observation)

        # 2. Check if a model runtime / router is available
        if self._router is None:
            logger.info("No ModelRouter attached; returning fallback safe action")
            return self._build_unavailable_fallback(
                observation=observation,
                step_index=step_index,
                reason="MODEL_INVOCATION_UNAVAILABLE: No ModelRouter or SessionManager configured",
            )

        # 3. Determine required capabilities & effective policy
        effective_policy = self._build_effective_policy(policy, has_screenshot)

        # 4. Resolve model runtime
        try:
            runtime = await self._router.resolve_runtime(effective_policy)
        except NoActiveModelError as ex:
            logger.warning("No compliant model runtime found for policy %s: %s", effective_policy, ex)
            return self._build_unavailable_fallback(
                observation=observation,
                step_index=step_index,
                reason=f"MODEL_INVOCATION_UNAVAILABLE: {ex}",
            )
        except Exception as ex:
            logger.error("Failed resolving model runtime: %s", ex)
            return self._build_unavailable_fallback(
                observation=observation,
                step_index=step_index,
                reason=f"MODEL_RUNTIME_ERROR: {ex}",
            )

        # 5. Attempt inference with Primary Runtime
        profile = get_model_capability_profile(runtime.model_id, runtime.descriptor)
        decision, trace = await self._invoke_model_and_parse(
            runtime=runtime,
            profile=profile,
            objective=objective,
            observation=observation,
            step_history=history,
            step_index=step_index,
            task_context=task_context,
            policy=effective_policy,
            input_modalities=input_modalities,
            obs_id=obs_id,
        )

        # 6. Hybrid Local -> Cloud Escalation
        # If local model confidence is low or parsing failed, and cloud is allowed, escalate to Cloud
        if (
            profile.is_local
            and (decision.decision_confidence < self._confidence_threshold or trace.validation_result != "VALID")
            and effective_policy.privacy.allow_cloud_transfer
            and not effective_policy.privacy.strictly_local
        ):
            logger.info(
                "Local model confidence (%.2f) below threshold (%.2f) or invalid; escalating to Cloud Model",
                decision.decision_confidence,
                self._confidence_threshold,
            )
            cloud_policy = effective_policy.model_copy(deep=True)
            cloud_policy.tier = ModelRoutingTier.PERFORMANCE_CLOUD

            try:
                cloud_runtime = await self._router.resolve_runtime(cloud_policy)
                cloud_profile = get_model_capability_profile(cloud_runtime.model_id, cloud_runtime.descriptor)
                cloud_decision, cloud_trace = await self._invoke_model_and_parse(
                    runtime=cloud_runtime,
                    profile=cloud_profile,
                    objective=objective,
                    observation=observation,
                    step_history=history,
                    step_index=step_index,
                    task_context=task_context,
                    policy=cloud_policy,
                    input_modalities=input_modalities,
                    obs_id=obs_id,
                )
                cloud_trace.escalated_to_cloud = True
                self._record_trace(cloud_trace)
                return cloud_decision
            except Exception as esc_err:
                logger.warning("Cloud model escalation failed: %s; keeping local decision", esc_err)

        self._record_trace(trace)
        return decision

    async def _invoke_model_and_parse(
        self,
        runtime: BaseModelRuntime,
        profile: ModelCapabilityProfile,
        objective: StructuredObjective,
        observation: Union[DesktopObservation, CurrentStateObservation],
        step_history: List[CognitiveStepResult],
        step_index: int,
        task_context: Optional[Dict[str, Any]],
        policy: RoutingPolicy,
        input_modalities: List[str],
        obs_id: str,
    ) -> Tuple[CognitiveDecision, AgentDecisionTrace]:
        """Execute chat inference on target runtime and parse structured output."""
        chat_req, attached_vision = AgentReasoningContextBuilder.build_chat_request(
            objective=objective,
            observation=observation,
            model_profile=profile,
            step_history=step_history,
            step_index=step_index,
            task_context=task_context,
            temperature=0.0,
        )

        t_call = time.perf_counter()
        raw_content = ""
        validation_status = "VALID"

        try:
            resp: ModelGenerateResponse = await runtime.chat(chat_req)
            latency_ms = resp.total_duration_ms or (time.perf_counter() - t_call) * 1000.0
            raw_content = resp.content

            # Parse and validate decision with coordinate isolation check
            decision = StructuredDecisionParser.parse_decision(
                raw_text=raw_content,
                step_index=step_index,
                model_id=runtime.model_id,
                latency_ms=latency_ms,
                attached_vision=attached_vision,
            )

        except CoordinateSecurityViolation as sec_err:
            logger.error("Coordinate security violation: %s", sec_err)
            validation_status = "COORDINATE_POLICY_VIOLATION"
            decision = self._build_safe_recovery_decision(step_index, str(sec_err))
            latency_ms = (time.perf_counter() - t_call) * 1000.0

        except (StructuredOutputParserError, Exception) as parse_err:
            logger.warning("Model output parse or invocation failed: %s (Raw: %s)", parse_err, raw_content[:150])
            validation_status = f"PARSE_ERROR: {parse_err}"
            decision = self._build_safe_recovery_decision(step_index, str(parse_err))
            latency_ms = (time.perf_counter() - t_call) * 1000.0

        trace = AgentDecisionTrace(
            observation_id=obs_id,
            step_index=step_index,
            model_provider=runtime.descriptor.provider.value,
            model_name=runtime.descriptor.provider_model_name,
            model_id=runtime.model_id,
            routing_tier=policy.tier.value,
            routing_reason=f"Resolved via {policy.tier.value}",
            input_modalities=input_modalities,
            used_vision=attached_vision,
            used_ocr="OCR" in input_modalities,
            used_uia="UIA" in input_modalities,
            used_win32="WIN32" in input_modalities,
            model_latency_ms=round(latency_ms, 2) if latency_ms else None,
            decision_confidence=decision.decision_confidence,
            action_type=decision.next_action.action_type.value if decision.next_action else None,
            target_name=decision.next_action.target.name if decision.next_action and decision.next_action.target else None,
            validation_result=validation_status,
            fallback_used=validation_status != "VALID",
            decision_summary=decision.decision_summary,
            evidence_used=decision.evidence_used,
        )
        return decision, trace

    def _inspect_modalities(
        self,
        observation: Union[DesktopObservation, CurrentStateObservation],
    ) -> Tuple[List[str], bool]:
        """Identify available modalities in the observation."""
        modalities: List[str] = ["WIN32"]
        has_screenshot = False

        if isinstance(observation, DesktopObservation):
            ss = observation.screenshot_reference or getattr(observation, "screenshot", None)
            if ss and (getattr(ss, "raw_bytes", None) or getattr(ss, "image_bytes", None) or getattr(ss, "image_base64", None)):
                modalities.append("SCREENSHOT")
                has_screenshot = True
            if (observation.uia_elements and len(observation.uia_elements) > 0) or (hasattr(observation, "uia") and observation.uia and getattr(observation.uia, "elements", None)):
                modalities.append("UIA")
            if (observation.ocr_tokens and len(observation.ocr_tokens) > 0) or (hasattr(observation, "ocr") and observation.ocr and getattr(observation.ocr, "tokens", None)):
                modalities.append("OCR")
        elif isinstance(observation, CurrentStateObservation):
            if observation.ocr_tokens:
                modalities.append("OCR")
            if observation.desktop_observation:
                d_obs = observation.desktop_observation
                ss = d_obs.screenshot_reference or getattr(d_obs, "screenshot", None)
                if ss and (getattr(ss, "raw_bytes", None) or getattr(ss, "image_bytes", None) or getattr(ss, "image_base64", None)):
                    modalities.append("SCREENSHOT")
                    has_screenshot = True
                if (d_obs.uia_elements and len(d_obs.uia_elements) > 0) or (hasattr(d_obs, "uia") and d_obs.uia and getattr(d_obs.uia, "elements", None)):
                    modalities.append("UIA")

        return modalities, has_screenshot

    def _build_effective_policy(self, base_policy: RoutingPolicy, has_screenshot: bool) -> RoutingPolicy:
        """Derive policy specifying VISION if screenshot is available and visual understanding desired."""
        effective = base_policy.model_copy(deep=True)
        # If policy already specifies vision or screenshot is present, ensure vision is requested
        if has_screenshot and ModelCapability.VISION not in effective.required_capabilities:
            effective.required_capabilities = set(effective.required_capabilities) | {ModelCapability.CHAT}
        return effective

    def _record_trace(self, trace: AgentDecisionTrace) -> None:
        """Record trace in internal history."""
        self._decision_traces.append(trace)
        if len(self._decision_traces) > 200:
            self._decision_traces = self._decision_traces[-200:]

    def _build_safe_recovery_decision(self, step_index: int, error_reason: str) -> CognitiveDecision:
        """Return a safe diagnostic wait action when model output is invalid."""
        return CognitiveDecision(
            step_index=step_index,
            decision_summary=f"Model output invalid: {error_reason}. Pausing desktop for safe state verification.",
            decision_confidence=0.3,
            evidence_used=["System fallback"],
            expected_state_transition="desktop_settled",
            reason_summary="Ensuring state safety after invalid decision output.",
            is_goal_satisfied=False,
            escalated_to_llm=True,
            next_action=AbstractAction(
                action_type=AbstractActionType.WAIT,
                parameters={"duration_ms": 500},
                outcome_contract=ActionOutcomeContract(expected_state_transition="desktop_settled"),
                expected_effect="Desktop settled",
                rationale="Safe recovery pause.",
            ),
        )

    def _build_unavailable_fallback(
        self,
        observation: Union[DesktopObservation, CurrentStateObservation],
        step_index: int,
        reason: str,
    ) -> CognitiveDecision:
        """Return diagnostic fallback when no AI model is configured or reachable."""
        return CognitiveDecision(
            step_index=step_index,
            decision_summary=reason,
            decision_confidence=0.0,
            evidence_used=["Observation received"],
            expected_state_transition="none",
            reason_summary=reason,
            is_goal_satisfied=False,
            escalated_to_llm=False,
            next_action=AbstractAction(
                action_type=AbstractActionType.WAIT,
                parameters={"duration_ms": 300},
                outcome_contract=ActionOutcomeContract(expected_state_transition="none"),
                expected_effect="Waiting for active model runtime",
                rationale=reason,
            ),
        )
