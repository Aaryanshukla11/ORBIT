"""Post-action verification engine for ORBIT."""

from __future__ import annotations

import logging
from typing import Optional

from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.runtime.verification.evidence import summarize_observation_evidence
from orbit.runtime.verification.models import (
    ActionVerificationResult,
    ExpectedOutcome,
    ExpectedOutcomeType,
    ObservationEvidenceSummary,
    VerificationOutcome,
    VerificationStrategy,
)
from orbit.runtime.verification.strategies import (
    evaluate_accessibility_state_change,
    evaluate_observation_state_delta,
    evaluate_window_state_change,
)

logger = logging.getLogger(__name__)


class ActionVerifier:
    """Deterministic post-action verification engine.

    Evaluates whether an executed action achieved its intended outcome
    by comparing pre-action observation evidence against a freshly acquired
    post-action observation.

    Key safety invariants:
    1. NEVER equate successful pointer event dispatch with successful verification.
    2. Reject stale post-action observations fail-closed (STALE_EVIDENCE).
    3. Reject generation changes between pre and post action fail-closed (STALE_EVIDENCE).
    4. Reject using the exact same snapshot for pre and post action (STALE_EVIDENCE).
    5. Return UNSUPPORTED for strategies not genuinely backed by active production capabilities.
    6. Confidence reflects actual evidence strength; never fabricate 1.0 confidence.
    """

    def verify(
        self,
        pre_snapshot: Optional[ObservationSnapshot],
        post_snapshot: Optional[ObservationSnapshot],
        expected_outcome: Optional[ExpectedOutcome] = None,
    ) -> ActionVerificationResult:
        """Verify the outcome of an action by comparing pre- and post-action observations."""
        # 1. Validate pre-action evidence
        if pre_snapshot is None:
            summary = summarize_observation_evidence(None)
            return ActionVerificationResult(
                outcome=VerificationOutcome.INCONCLUSIVE,
                strategy_used=(
                    expected_outcome.strategy
                    if expected_outcome
                    else VerificationStrategy.OBSERVATION_STATE_DELTA
                ),
                confidence=0.0,
                pre_generation_id=-1,
                post_generation_id=-1,
                pre_evidence=summary or self._empty_summary(-1),
                post_evidence=None,
                detected_changes=[],
                failure_reason="Missing pre-action observation snapshot",
            )

        pre_summary = summarize_observation_evidence(pre_snapshot)
        assert pre_summary is not None

        # 2. Validate post-action evidence presence
        if post_snapshot is None:
            return ActionVerificationResult(
                outcome=VerificationOutcome.INCONCLUSIVE,
                strategy_used=(
                    expected_outcome.strategy
                    if expected_outcome
                    else VerificationStrategy.OBSERVATION_STATE_DELTA
                ),
                confidence=0.0,
                pre_generation_id=pre_snapshot.generation_id,
                post_generation_id=-1,
                pre_evidence=pre_summary,
                post_evidence=None,
                detected_changes=[],
                failure_reason="Missing post-action observation snapshot",
            )

        post_summary = summarize_observation_evidence(post_snapshot)
        assert post_summary is not None

        # 3. Detect invalid reuse of identical snapshot
        if post_snapshot.snapshot_id == pre_snapshot.snapshot_id:
            return ActionVerificationResult(
                outcome=VerificationOutcome.STALE_EVIDENCE,
                strategy_used=(
                    expected_outcome.strategy
                    if expected_outcome
                    else VerificationStrategy.OBSERVATION_STATE_DELTA
                ),
                confidence=0.0,
                pre_generation_id=pre_snapshot.generation_id,
                post_generation_id=post_snapshot.generation_id,
                pre_evidence=pre_summary,
                post_evidence=post_summary,
                detected_changes=[],
                failure_reason=(
                    f"Post-action snapshot is identical to pre-action snapshot "
                    f"(snapshot_id: {post_snapshot.snapshot_id}). A fresh observation is mandatory."
                ),
            )

        # 4. Check snapshot freshness
        if post_snapshot.is_stale:
            return ActionVerificationResult(
                outcome=VerificationOutcome.STALE_EVIDENCE,
                strategy_used=(
                    expected_outcome.strategy
                    if expected_outcome
                    else VerificationStrategy.OBSERVATION_STATE_DELTA
                ),
                confidence=0.0,
                pre_generation_id=pre_snapshot.generation_id,
                post_generation_id=post_snapshot.generation_id,
                pre_evidence=pre_summary,
                post_evidence=post_summary,
                detected_changes=[],
                failure_reason=(
                    f"Post-action snapshot is marked stale "
                    f"(reason: {post_snapshot.invalidation_reason or 'unknown'})."
                ),
            )

        # 5. Check desktop generation parity
        if post_snapshot.generation_id != pre_snapshot.generation_id:
            return ActionVerificationResult(
                outcome=VerificationOutcome.STALE_EVIDENCE,
                strategy_used=(
                    expected_outcome.strategy
                    if expected_outcome
                    else VerificationStrategy.OBSERVATION_STATE_DELTA
                ),
                confidence=0.0,
                pre_generation_id=pre_snapshot.generation_id,
                post_generation_id=post_snapshot.generation_id,
                pre_evidence=pre_summary,
                post_evidence=post_summary,
                detected_changes=[],
                failure_reason=(
                    f"Desktop generation changed across action dispatch: "
                    f"pre={pre_snapshot.generation_id}, post={post_snapshot.generation_id}. "
                    f"Comparison unsafe due to display geometry shift."
                ),
            )

        # 6. Resolve strategy
        strategy = (
            expected_outcome.strategy
            if expected_outcome
            else VerificationStrategy.OBSERVATION_STATE_DELTA
        )

        # 7. Check for unsupported strategies
        if strategy == VerificationStrategy.VISUAL_SEMANTIC:
            return ActionVerificationResult(
                outcome=VerificationOutcome.UNSUPPORTED,
                strategy_used=strategy,
                confidence=0.0,
                pre_generation_id=pre_snapshot.generation_id,
                post_generation_id=post_snapshot.generation_id,
                pre_evidence=pre_summary,
                post_evidence=post_summary,
                detected_changes=[],
                failure_reason=(
                    "VISUAL_SEMANTIC strategy is unsupported: ORBIT does not fabricate "
                    "mock computer vision or unverified pixel OCR."
                ),
            )

        # 8. Dispatch to strategy evaluator
        outcome: VerificationOutcome
        confidence: float
        changes: list[str]
        failure_reason: Optional[str]

        if strategy == VerificationStrategy.WINDOW_STATE_CHANGE:
            if expected_outcome is None:
                expected_outcome = ExpectedOutcome(
                    outcome_type=ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE,
                    strategy=strategy,
                )
            outcome, confidence, changes, failure_reason = evaluate_window_state_change(
                pre_snapshot, post_snapshot, expected_outcome
            )

        elif strategy in (
            VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
            VerificationStrategy.TARGET_PRESENCE_CHANGE,
        ):
            if expected_outcome is None:
                expected_outcome = ExpectedOutcome(
                    outcome_type=ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE,
                    strategy=strategy,
                )
            outcome, confidence, changes, failure_reason = evaluate_accessibility_state_change(
                pre_snapshot, post_snapshot, expected_outcome
            )

        elif strategy == VerificationStrategy.OBSERVATION_STATE_DELTA:
            outcome, confidence, changes, failure_reason = evaluate_observation_state_delta(
                pre_snapshot, post_snapshot, expected_outcome
            )

        else:
            outcome = VerificationOutcome.UNSUPPORTED
            confidence = 0.0
            changes = []
            failure_reason = f"Verification strategy '{strategy}' is not implemented."

        return ActionVerificationResult(
            outcome=outcome,
            strategy_used=strategy,
            confidence=confidence,
            pre_generation_id=pre_snapshot.generation_id,
            post_generation_id=post_snapshot.generation_id,
            pre_evidence=pre_summary,
            post_evidence=post_summary,
            detected_changes=changes,
            failure_reason=failure_reason,
        )

    def _empty_summary(self, gen_id: int) -> ObservationEvidenceSummary:
        return ObservationEvidenceSummary(
            snapshot_id="none",
            desktop_generation_id=gen_id,
            timestamp_ns=0,
            is_stale=True,
            foreground_hwnd=None,
            foreground_title=None,
            visible_window_count=0,
            element_count=0,
            element_ids=[],
            window_hwnds=[],
            metadata={},
        )
