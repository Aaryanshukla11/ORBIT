"""Visual perception engine managing registered templates, trust boundaries, and matching."""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional
from PIL import Image

from orbit.adapters.observation.snapshot import (
    FreshnessState,
    ObservationSnapshot,
)
from orbit.runtime.perception.visual_matcher import (
    TemplateVisualMatcher,
    VisualMatcher,
)
from orbit.runtime.perception.visual_models import (
    VisualMatchPolicy,
    VisualMatchResult,
    VisualMatchStatus,
    VisualTemplate,
    VisualTemplateSource,
)

logger = logging.getLogger(__name__)


class VisualPerceptionEngine:
    """Production visual perception engine managing registered templates and match workflows."""

    def __init__(
        self,
        matcher: Optional[VisualMatcher] = None,
        default_policy: Optional[VisualMatchPolicy] = None,
    ) -> None:
        self._matcher = matcher or TemplateVisualMatcher()
        self._default_policy = default_policy or VisualMatchPolicy()
        self._registered_templates: Dict[str, VisualTemplate] = {}

    @property
    def matcher(self) -> VisualMatcher:
        return self._matcher

    def register_template(self, template: VisualTemplate) -> bool:
        """Register a trusted visual UI template into the registry."""
        if not template.is_valid:
            logger.error("Failed to register template '%s': invalid dimensions", template.template_id)
            return False

        self._registered_templates[template.template_id] = template
        logger.info(
            "Registered visual template '%s' (%dx%d, source=%s)",
            template.template_id,
            template.width,
            template.height,
            template.source.value,
        )
        return True

    def unregister_template(self, template_id: str) -> bool:
        """Remove a template from the registry."""
        if template_id in self._registered_templates:
            del self._registered_templates[template_id]
            return True
        return False

    def get_template(self, template_id: str) -> Optional[VisualTemplate]:
        """Retrieve a registered template by ID."""
        return self._registered_templates.get(template_id)

    def list_templates(self) -> List[VisualTemplate]:
        """List all registered templates."""
        return list(self._registered_templates.values())

    async def find_template(
        self,
        snapshot: ObservationSnapshot,
        template: VisualTemplate,
        image: Optional[Image.Image] = None,
        policy: Optional[VisualMatchPolicy] = None,
    ) -> VisualMatchResult:
        """Match a template against an ObservationSnapshot with generation and freshness gating."""
        t0 = time.perf_counter()
        match_policy = policy or self._default_policy

        # 1. Temporal Freshness Gate
        if snapshot.is_stale or snapshot.freshness_state == FreshnessState.STALE:
            reason = snapshot.invalidation_reason or "Observation snapshot TTL expired"
            logger.warning("Visual matching rejected: snapshot %s is stale (%s)", snapshot.snapshot_id, reason)
            return VisualMatchResult(
                status=VisualMatchStatus.STALE_OBSERVATION,
                matcher_kind=self._matcher.matcher_kind,
                template_id=template.template_id,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                error_message=f"Observation snapshot is stale: {reason}",
            )

        # 2. Extract search image
        search_image = image
        if search_image is None:
            raw_img = snapshot.telemetry.get("screenshot") or snapshot.telemetry.get("image")
            if isinstance(raw_img, Image.Image):
                search_image = raw_img

        if search_image is None:
            return VisualMatchResult(
                status=VisualMatchStatus.ERROR,
                matcher_kind=self._matcher.matcher_kind,
                template_id=template.template_id,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                error_message="No screenshot image available in snapshot or arguments for visual matching",
            )

        # 3. Execute matching
        result = await self._matcher.match(
            template=template,
            image=search_image,
            policy=match_policy,
            desktop_generation_id=snapshot.generation_id,
            observation_id=snapshot.snapshot_id,
        )

        return result
