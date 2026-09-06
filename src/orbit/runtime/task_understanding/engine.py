"""Engine facade for deterministic task understanding and structured intent extraction."""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

from orbit.runtime.task_understanding.models import (
    RawTaskRequest,
    TaskUnderstandingResult,
)
from orbit.runtime.task_understanding.normalizer import TaskNormalizer
from orbit.runtime.task_understanding.parser import DeterministicTaskParser
from orbit.runtime.task_understanding.validator import TaskUnderstandingValidator


class TaskUnderstandingEngine:
    """Core facade for ORBIT Task Understanding (M1.8 Step 1).

    Converts raw natural language prompts into validated, strongly-typed structured task intents.
    Operates 100% locally and deterministically with zero external LLM dependencies and zero OS side-effects.
    """

    def __init__(
        self,
        normalizer: Optional[TaskNormalizer] = None,
        parser: Optional[DeterministicTaskParser] = None,
        validator: Optional[TaskUnderstandingValidator] = None,
    ):
        self._normalizer = normalizer or TaskNormalizer()
        self._parser = parser or DeterministicTaskParser(normalizer=self._normalizer)
        self._validator = validator or TaskUnderstandingValidator()

    def understand(
        self,
        request: Union[RawTaskRequest, str],
        source: str = "user",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskUnderstandingResult:
        """Parse, extract, and validate structured intents from a task request."""
        if isinstance(request, str):
            raw_req = RawTaskRequest(
                raw_text=request,
                source=source,
                metadata=metadata or {},
            )
        else:
            raw_req = request

        # Extract structured intents
        intents = self._parser.parse_request(raw_req)

        # Validate and produce final result
        result = self._validator.validate(raw_req, intents)
        return result
