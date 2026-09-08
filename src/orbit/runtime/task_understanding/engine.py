"""Engine facade for hybrid deterministic and cognitive LLM task understanding."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, Union

from orbit.runtime.task_understanding.llm_decomposer import LLMTaskDecomposer
from orbit.runtime.task_understanding.models import (
    RawTaskRequest,
    TaskUnderstandingResult,
    TaskUnderstandingStatus,
)
from orbit.runtime.task_understanding.normalizer import TaskNormalizer
from orbit.runtime.task_understanding.parser import DeterministicTaskParser
from orbit.runtime.task_understanding.validator import TaskUnderstandingValidator


class TaskUnderstandingEngine:
    """Core facade for ORBIT Hybrid Task Understanding.

    .. deprecated::
        Superseded in production by the unified AI-native `AgentExecutionLoop` and `ModelRouter`.
        Retained for backward compatibility, testing, and legacy intent parsing.
    """

    def __init__(
        self,
        normalizer: Optional[TaskNormalizer] = None,
        parser: Optional[DeterministicTaskParser] = None,
        validator: Optional[TaskUnderstandingValidator] = None,
        llm_decomposer: Optional[LLMTaskDecomposer] = None,
    ):
        self._normalizer = normalizer or TaskNormalizer()
        self._parser = parser or DeterministicTaskParser(normalizer=self._normalizer)
        self._validator = validator or TaskUnderstandingValidator()
        self._llm_decomposer = llm_decomposer or LLMTaskDecomposer()

    @property
    def llm_decomposer(self) -> LLMTaskDecomposer:
        return self._llm_decomposer

    def set_model_session_manager(self, msm: Any) -> None:
        """Bind active model session manager to underlying LLM task decomposer."""
        if self._llm_decomposer is not None:
            self._llm_decomposer.set_model_session_manager(msm)

    def understand(
        self,
        request: Union[RawTaskRequest, str],
        source: str = "user",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskUnderstandingResult:
        """Parse, extract, and validate structured intents from a task request synchronously."""
        if isinstance(request, str):
            raw_req = RawTaskRequest(
                raw_text=request,
                source=source,
                metadata=metadata or {},
            )
        else:
            raw_req = request

        # 1. Fast deterministic parse
        intents = self._parser.parse_request(raw_req)
        result = self._validator.validate(raw_req, intents)
        return result

    async def understand_async(
        self,
        request: Union[RawTaskRequest, str],
        source: str = "user",
        metadata: Optional[Dict[str, Any]] = None,
        snapshot: Optional[Any] = None,
    ) -> TaskUnderstandingResult:
        """Parse and extract structured intents with asynchronous Cognitive LLM fallback."""

        if isinstance(request, str):
            raw_req = RawTaskRequest(
                raw_text=request,
                source=source,
                metadata=metadata or {},
            )
        else:
            raw_req = request

        # 1. Fast deterministic parse
        intents = self._parser.parse_request(raw_req)
        result = self._validator.validate(raw_req, intents)

        # 2. If deterministic parse succeeded cleanly or is explicitly AMBIGUOUS, return immediately
        if result.status == TaskUnderstandingStatus.AMBIGUOUS:
            return result

        is_clean = (
            result.status == TaskUnderstandingStatus.UNDERSTOOD
            and not any(i.goal.value == "UNKNOWN" for i in intents)
        )
        if is_clean:
            return result


        # 3. Cognitive LLM Decomposition fallback for complex / unparsed goals
        if self._llm_decomposer is not None:
            llm_intents = await self._llm_decomposer.decompose_request(raw_req)
            if llm_intents:
                llm_result = self._validator.validate(raw_req, llm_intents)
                if llm_result.status in (TaskUnderstandingStatus.UNDERSTOOD, TaskUnderstandingStatus.PARTIALLY_UNDERSTOOD):
                    return llm_result

        return result
