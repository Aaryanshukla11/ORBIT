"""Compatibility shim for CognitiveExecutionLoop delegating to canonical AgentExecutionLoop."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from orbit.contracts.capabilities import (
    KeyboardCapability,
    ObservationCapability,
    PointerCapability,
    WorkspaceCapability,
)
from orbit.runtime.cancellation import CancellationToken
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.engine import CognitiveDecisionEngine
from orbit.runtime.cognitive.interpreter import LLMIntentInterpreter
from orbit.runtime.cognitive.models import (
    CognitiveExecutionResult,
    ExecutionBudget,
    StructuredObjective,
)
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.targeting import TargetLocator
from orbit.runtime.task_completion.goal_verifier import GoalVerifier

logger = logging.getLogger(__name__)


class CognitiveExecutionLoop(AgentExecutionLoop):
    """Compatibility wrapper around canonical AgentExecutionLoop enforcing the single execution path."""

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
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model_session_manager=model_session_manager,
            interpreter=interpreter,
            observer=observer,
            decision_engine=decision_engine,
            target_locator=target_locator,
            workspace=workspace,
            pointer=pointer,
            keyboard=keyboard,
            observation=observation,
            goal_verifier=goal_verifier,
            budget=budget,
            **kwargs,
        )

    def set_model_session_manager(self, msm: Any) -> None:
        self._session_manager = msm
        if self._interpreter is not None and hasattr(self._interpreter, "set_model_session_manager"):
            self._interpreter.set_model_session_manager(msm)
        if self._decision_engine is not None and hasattr(self._decision_engine, "set_model_session_manager"):
            self._decision_engine.set_model_session_manager(msm)
