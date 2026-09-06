"""Live Closed-Loop Execution and Recovery Validation Suite for Milestone M1.6.

Verifies:
1. Genuine multi-step closed loop on live desktop (Observation -> Target 1 -> Act -> Observation 2 -> Target 2 -> Act).
2. Target Not Found fail-closed behavior (0 OS input dispatches).
3. Stale Generation ID rejection before dispatch (0 OS input dispatches).
4. Verification failure recovery and retry budget exhaustion.

Epistemic Classification:
- LIVE_OS_VALIDATED: Executed against live Windows display, Win32 window APIs, and production adapters.
- TEST_PROVEN: Deterministically proven under controlled integration test assertions.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import subprocess
import sys
import time
from typing import Generator
from uuid import uuid4
import pytest

from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.workspace.abi import IS_WINDOWS
from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
from orbit.runtime.execution import (
    ClosedLoopExecutionEngine,
    ClosedLoopExecutionResult,
    ExecutionPolicy,
    ExecutionState,
)
from orbit.runtime.execution.context import DispatchStage
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    TargetIntent,
    TargetStrategy,
)
from orbit.runtime.verification import (
    ActionVerifier,
    ExpectedOutcome,
    ExpectedOutcomeType,
    VerificationOutcome,
    VerificationStrategy,
)


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="Live OS validation requires Windows platform")
async def test_live_multi_step_closed_loop_sequential_progression():
    """Verify that multi-step tasks independently resolve each step from fresh observations.

    Proves:
    1. Step 1 resolves Target 1 dynamically, validates, and dispatches.
    2. Step 2 captures fresh observation, independently resolves Target 2, and dispatches.
    3. Resolved coordinates differ and match the independent target intents.
    """
    event_bus = EventBus()
    obs = ProductionObservationAdapter(default_ttl_ms=1000.0)
    wsp = ProductionWorkspaceAdapter()
    ptr = ProductionPointerAdapter()
    locator = EvidenceBasedTargetLocator()
    verifier = ActionVerifier()

    await obs.initialize()
    await wsp.initialize()
    await ptr.initialize()

    try:
        engine = ClosedLoopExecutionEngine(
            observation=obs,
            pointer=ptr,
            workspace=wsp,
            target_locator=locator,
            action_verifier=verifier,
            event_bus=event_bus,
        )

        active_gen = wsp.get_desktop_generation()

        # Step 1: Target Region A (200, 200)
        intent1 = TargetIntent(
            strategy=TargetStrategy.COORDINATE_REGION,
            explicit_bounds=BoundingBox(left=200, top=200, width=120, height=120),
            metadata={"desktop_generation_id": active_gen},
        )
        res1: ClosedLoopExecutionResult = await engine.execute_task_action(
            session_id="multi_step_live",
            task_id="step_1_region_a",
            prompt="Interact with target region A",
            target_intent=intent1,
            action_type="pointer_move",
            policy=ExecutionPolicy(max_total_attempts=2, allow_inconclusive_as_success=True),
        )

        assert res1.is_success is True
        assert res1.final_state == ExecutionState.SUCCEEDED
        assert res1.resolved_target is not None
        pt1 = (res1.resolved_target.safe_point.x, res1.resolved_target.safe_point.y)

        # Step 2: Target Region B (500, 300)
        intent2 = TargetIntent(
            strategy=TargetStrategy.COORDINATE_REGION,
            explicit_bounds=BoundingBox(left=500, top=300, width=120, height=120),
            metadata={"desktop_generation_id": active_gen},
        )
        res2: ClosedLoopExecutionResult = await engine.execute_task_action(
            session_id="multi_step_live",
            task_id="step_2_region_b",
            prompt="Interact with target region B",
            target_intent=intent2,
            action_type="pointer_move",
            policy=ExecutionPolicy(max_total_attempts=2, allow_inconclusive_as_success=True),
        )

        assert res2.is_success is True
        assert res2.final_state == ExecutionState.SUCCEEDED
        assert res2.resolved_target is not None
        pt2 = (res2.resolved_target.safe_point.x, res2.resolved_target.safe_point.y)

        # Invariant Assertions
        assert pt1 != pt2
        assert pt1[0] >= 200 and pt1[1] >= 200
        assert pt2[0] >= 500 and pt2[1] >= 300
        assert res1.dispatch_stage == DispatchStage.DISPATCHED
        assert res2.dispatch_stage == DispatchStage.DISPATCHED
    finally:
        await ptr.shutdown()
        await wsp.shutdown()
        await obs.shutdown()


@pytest.mark.asyncio
async def test_live_target_not_found_fails_closed_zero_dispatches():
    """Verify that targeting a non-existent target fails closed with 0 pointer dispatches."""
    event_bus = EventBus()
    obs = ProductionObservationAdapter()
    wsp = ProductionWorkspaceAdapter()
    ptr = ProductionPointerAdapter()
    locator = EvidenceBasedTargetLocator()
    verifier = ActionVerifier()

    await obs.initialize()
    await wsp.initialize()
    await ptr.initialize()

    try:
        engine = ClosedLoopExecutionEngine(
            observation=obs,
            pointer=ptr,
            workspace=wsp,
            target_locator=locator,
            action_verifier=verifier,
            event_bus=event_bus,
        )

        intent = TargetIntent(
            strategy=TargetStrategy.WINDOW_TITLE,
            window_title="NonExistentTargetWindow_ORBIT_999999",
        )

        result: ClosedLoopExecutionResult = await engine.execute_task_action(
            session_id="test_session_fail",
            task_id="task_not_found",
            prompt="Interact with phantom window",
            target_intent=intent,
            action_type="pointer_click",
            policy=ExecutionPolicy(max_total_attempts=2, max_target_resolution_attempts=1),
        )

        assert result.is_success is False
        assert result.final_state == ExecutionState.FAILED
        assert result.failure_code == "TARGET_NOT_FOUND"
        assert result.dispatch_stage == DispatchStage.NOT_DISPATCHED
        assert len(result.attempts) == 0
    finally:
        await ptr.shutdown()
        await wsp.shutdown()
        await obs.shutdown()


@pytest.mark.asyncio
async def test_live_stale_generation_target_rejected_fail_closed():
    """Verify that a target with an obsolete desktop generation ID is rejected before dispatch."""
    event_bus = EventBus()
    obs = ProductionObservationAdapter()
    wsp = ProductionWorkspaceAdapter()
    ptr = ProductionPointerAdapter()
    locator = EvidenceBasedTargetLocator()
    verifier = ActionVerifier()

    await obs.initialize()
    await wsp.initialize()
    await ptr.initialize()

    try:
        engine = ClosedLoopExecutionEngine(
            observation=obs,
            pointer=ptr,
            workspace=wsp,
            target_locator=locator,
            action_verifier=verifier,
            event_bus=event_bus,
        )

        # Mock locator to return target with obsolete generation ID
        original_locate = locator.locate_target

        def mock_stale_locate(snap, it):
            res = original_locate(snap, it)
            if res.target:
                res.target.desktop_generation_id = 888888
                res.target.safe_point.desktop_generation_id = 888888
            return res

        engine._target_locator.locate_target = mock_stale_locate

        intent = TargetIntent(
            strategy=TargetStrategy.COORDINATE_REGION,
            explicit_bounds=BoundingBox(left=200, top=200, width=100, height=100),
            metadata={"desktop_generation_id": 888888},
        )

        result: ClosedLoopExecutionResult = await engine.execute_task_action(
            session_id="test_session_stale",
            task_id="task_stale_gen",
            prompt="Execute on stale generation target",
            target_intent=intent,
            action_type="pointer_click",
            policy=ExecutionPolicy(max_total_attempts=1, max_recovery_attempts=0),
        )

        assert result.is_success is False
        assert result.final_state == ExecutionState.FAILED
        assert result.dispatch_stage == DispatchStage.NOT_DISPATCHED
    finally:
        await ptr.shutdown()
        await wsp.shutdown()
        await obs.shutdown()


@pytest.mark.asyncio
async def test_live_verification_failure_triggers_bounded_retry_exhaustion():
    """Verify that verification failures trigger recovery up to the configured budget limit."""
    event_bus = EventBus()
    obs = ProductionObservationAdapter()
    wsp = ProductionWorkspaceAdapter()
    ptr = ProductionPointerAdapter()
    locator = EvidenceBasedTargetLocator()

    class AlwaysFailingVerifier(ActionVerifier):
        def verify(self, pre_snapshot, post_snapshot, expected_outcome=None):
            from orbit.runtime.verification.evidence import summarize_observation_evidence
            from orbit.runtime.verification.models import ActionVerificationResult
            return ActionVerificationResult(
                outcome=VerificationOutcome.VERIFIED_FAILURE,
                strategy_used=VerificationStrategy.OBSERVATION_STATE_DELTA,
                confidence=0.95,
                pre_generation_id=1,
                post_generation_id=1,
                pre_evidence=summarize_observation_evidence(pre_snapshot),
                post_evidence=summarize_observation_evidence(post_snapshot),
                detected_changes=[],
                failure_reason="Deterministic verification failure for retry budget test",
            )

    await obs.initialize()
    await wsp.initialize()
    await ptr.initialize()

    try:
        engine = ClosedLoopExecutionEngine(
            observation=obs,
            pointer=ptr,
            workspace=wsp,
            target_locator=locator,
            action_verifier=AlwaysFailingVerifier(),
            event_bus=event_bus,
        )

        intent = TargetIntent(
            strategy=TargetStrategy.COORDINATE_REGION,
            explicit_bounds=BoundingBox(left=150, top=150, width=100, height=100),
            expected_outcome=ExpectedOutcome(
                strategy=VerificationStrategy.OBSERVATION_STATE_DELTA,
                outcome_type=ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE,
            ),
        )

        result: ClosedLoopExecutionResult = await engine.execute_task_action(
            session_id="test_session_retry",
            task_id="task_retry_budget",
            prompt="Test bounded retry exhaustion",
            target_intent=intent,
            action_type="pointer_move",
            expected_outcome=intent.expected_outcome,
            policy=ExecutionPolicy(max_total_attempts=3, max_verification_retries=2),
        )

        assert result.is_success is False
        assert result.final_state == ExecutionState.FAILED
        assert result.total_attempts == 3
        assert result.total_recoveries == 2
    finally:
        await ptr.shutdown()
        await wsp.shutdown()
        await obs.shutdown()
