"""Integration tests for ORBIT M1.6 Step 2: Post-Action Visual & Semantic Verification Engine.

Explicitly validates:
1. Successful flow: Observe -> execute action -> observe -> expected state confirmed -> VERIFIED
2. Dispatch without verification success: action dispatch succeeds -> expected state not observed -> NOT_VERIFIED (fails closed)
3. Observation unavailable: action dispatch succeeds -> post observation fails -> INCONCLUSIVE / ERROR
4. Generation invalidation: pre-action generation N -> workspace changes -> post-action generation N+1 -> no false VERIFIED result
5. Human takeover: action completes -> takeover activates -> verification safely aborted / cancelled
"""

import asyncio
from datetime import datetime, timezone
import pytest
import time

from orbit.adapters.mocks.mock_keyboard import MockKeyboardAdapter
from orbit.adapters.mocks.mock_observation import MockObservationAdapter
from orbit.adapters.mocks.mock_pointer import MockPointerAdapter
from orbit.adapters.mocks.mock_safety import MockSafetyCoordinator
from orbit.adapters.mocks.mock_takeover import MockHumanTakeoverAdapter
from orbit.adapters.mocks.mock_workspace import MockWorkspaceAdapter
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.events import EventType
from orbit.contracts.runtime import (
    Action,
    ActionStage,
    ActionTier,
    SystemState,
    TaskStatus,
    VerificationResult as RuntimeVerificationResult,
    VerificationStatus as RuntimeVerificationStatus,
)
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
from orbit.runtime.cancellation import CancellationSource
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.verification import (
    ActionVerificationResult,
    ActionVerifier,
    ExpectedOutcome,
    ExpectedOutcomeType,
    VerificationOutcome,
    VerificationStatus,
    VerificationStrategy,
)


def _make_window(
    hwnd: int,
    title: str = "",
    class_name: str = "TestClass",
    process_id: int = 1234,
    process_name: str = "test.exe",
    bounds: BoundingBox = BoundingBox(left=0, top=0, width=800, height=600),
    is_foreground: bool = False,
    is_visible: bool = True,
) -> ObservedWindow:
    return ObservedWindow(
        hwnd=hwnd,
        process_id=process_id,
        process_name=process_name,
        window_title=title,
        extended_bounds=bounds,
        is_foreground=is_foreground,
        is_visible=is_visible,
        dpi_scaling=1.0,
    )


def _make_snapshot(
    snapshot_id: str,
    generation_id: int = 1,
    windows=None,
    elements=None,
    is_stale: bool = False,
    invalidation_reason=None,
    foreground_window=None,
) -> ObservationSnapshot:
    return ObservationSnapshot(
        snapshot_id=snapshot_id,
        generation_id=generation_id,
        timestamp_ns=time.monotonic_ns(),
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=5.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        windows=windows or [],
        detected_elements=elements or [],
        foreground_window=foreground_window,
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.STALE if is_stale else FreshnessState.FRESH,
        is_stale=is_stale,
        invalidation_reason=invalidation_reason,
    )


@pytest.fixture
def verification_env():
    event_bus = EventBus()
    obs = MockObservationAdapter()
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    tkv = MockHumanTakeoverAdapter()
    wsp = MockWorkspaceAdapter()
    sft = MockSafetyCoordinator()

    orch = OrbitOrchestrator(
        event_bus=event_bus,
        observation=obs,
        pointer=ptr,
        keyboard=kbd,
        takeover=tkv,
        workspace=wsp,
        safety=sft,
    )
    return orch, obs, ptr, wsp, tkv, event_bus


@pytest.mark.asyncio
async def test_post_action_verification_successful_flow(verification_env):
    """Flow 1: Observe -> execute action -> observe -> expected state confirmed -> VERIFIED."""
    orch, obs, ptr, wsp, tkv, bus = verification_env
    await orch.initialize()

    # Pre-action: target button not focused
    pre_el = ObservedElement(
        element_id="btn_ok",
        source="MSAA",
        name="OK",
        role="Button",
        bounds=BoundingBox(left=400, top=300, width=80, height=30),
        is_focused=False,
    )
    # Post-action: target button focused
    post_el = ObservedElement(
        element_id="btn_ok",
        source="MSAA",
        name="OK",
        role="Button",
        bounds=BoundingBox(left=400, top=300, width=80, height=30),
        is_focused=True,
    )

    pre_snap = _make_snapshot("snap_pre_flow", generation_id=wsp.desktop_generation_id, elements=[pre_el])
    post_snap = _make_snapshot("snap_post_flow", generation_id=wsp.desktop_generation_id, elements=[post_el])

    obs.queue_mock_snapshot(pre_snap)
    obs.queue_mock_snapshot(post_snap)

    action = Action(
        action_id="act_flow_01",
        task_id="task_flow_01",
        action_type="pointer_click",
        tier=ActionTier.TIER_2_CONSTRAINED,
        parameters={
            "x": 440,
            "y": 315,
            "desktop_generation_id": wsp.desktop_generation_id,
            "expected_outcome": {
                "outcome_type": "ELEMENT_STATE_CHANGED",
                "strategy": "ACCESSIBILITY_STATE_CHANGE",
                "target_id": "btn_ok",
                "expected_property": "is_focused",
                "expected_value": True,
            },
        },
    )

    cancel_source = CancellationSource()
    await orch._execute_action("sess_01", action, cancel_source.token)

    # Action must be COMPLETED and verified
    assert action.stage == ActionStage.COMPLETED
    assert action.verification is not None
    assert action.verification.status == RuntimeVerificationStatus.PASSED
    assert action.verification.details["outcome"] == VerificationOutcome.VERIFIED_SUCCESS.value
    assert action.verification.confidence == 0.95


@pytest.mark.asyncio
async def test_post_action_verification_dispatch_without_outcome_fails(verification_env):
    """Flow 2: Action dispatch succeeds -> expected state not observed -> NOT_VERIFIED (fails closed)."""
    orch, obs, ptr, wsp, tkv, bus = verification_env
    await orch.initialize()

    # Pre-action and post-action: dialog remains open after close click
    dialog_win = _make_window(hwnd=6001, title="Confirm Exit", bounds=BoundingBox(left=200, top=200, width=400, height=300))

    pre_snap = _make_snapshot("snap_pre_fail", generation_id=wsp.desktop_generation_id, windows=[dialog_win])
    post_snap = _make_snapshot("snap_post_fail", generation_id=wsp.desktop_generation_id, windows=[dialog_win])

    obs.queue_mock_snapshot(pre_snap)
    obs.queue_mock_snapshot(post_snap)

    action = Action(
        action_id="act_fail_01",
        task_id="task_fail_01",
        action_type="pointer_click",
        tier=ActionTier.TIER_2_CONSTRAINED,
        parameters={
            "x": 580,
            "y": 210,
            "desktop_generation_id": wsp.desktop_generation_id,
            "expected_outcome": {
                "outcome_type": "WINDOW_CLOSED",
                "strategy": "WINDOW_STATE_CHANGE",
                "target_hwnd": 6001,
                "window_title": "Confirm Exit",
            },
        },
    )

    cancel_source = CancellationSource()
    with pytest.raises(RuntimeError) as exc_info:
        await orch._execute_action("sess_01", action, cancel_source.token)

    assert "Action verification failed (VERIFIED_FAILURE)" in str(exc_info.value)
    assert action.stage == ActionStage.FAILED
    assert action.verification is not None
    assert action.verification.status == RuntimeVerificationStatus.FAILED
    assert action.verification.details["outcome"] == VerificationOutcome.VERIFIED_FAILURE.value
    assert action.error is not None
    assert action.error.code == "VERIFIED_FAILURE"


@pytest.mark.asyncio
async def test_post_action_verification_observation_unavailable_inconclusive(verification_env):
    """Flow 3: Action dispatch succeeds -> post observation fails -> INCONCLUSIVE / ERROR (no false success)."""
    orch, obs, ptr, wsp, tkv, bus = verification_env
    await orch.initialize()

    pre_snap = _make_snapshot("snap_pre_unavail", generation_id=wsp.desktop_generation_id)
    obs.queue_mock_snapshot(pre_snap)
    # Post snapshot is deliberately NOT queued; configure mock to raise on capture
    async def _failing_capture(**kwargs):
        raise RuntimeError("GDI Desktop capture failed due to display lock")
    obs.capture_snapshot = _failing_capture

    action = Action(
        action_id="act_unavail_01",
        task_id="task_unavail_01",
        action_type="pointer_click",
        tier=ActionTier.TIER_2_CONSTRAINED,
        parameters={
            "x": 300,
            "y": 300,
            "desktop_generation_id": wsp.desktop_generation_id,
            "pre_snapshot": pre_snap,
            "expected_outcome": {
                "outcome_type": "ANY_OBSERVABLE_CHANGE",
                "strategy": "OBSERVATION_STATE_DELTA",
            },
        },
    )

    cancel_source = CancellationSource()
    await orch._execute_action("sess_01", action, cancel_source.token)

    # Must NOT claim VERIFIED success when post observation is unavailable!
    assert action.verification is not None
    assert action.verification.status == RuntimeVerificationStatus.INCONCLUSIVE
    assert action.verification.confidence == 0.0
    assert action.verification.details["outcome"] == VerificationOutcome.INCONCLUSIVE.value
    assert "Missing post-action observation snapshot" in action.verification.details["failure_reason"]


@pytest.mark.asyncio
async def test_post_action_verification_generation_invalidation(verification_env):
    """Flow 4: Pre-action gen N -> workspace changes -> post-action gen N+1 -> no false VERIFIED result."""
    orch, obs, ptr, wsp, tkv, bus = verification_env
    await orch.initialize()

    gen_n = wsp.desktop_generation_id
    gen_n_plus_1 = gen_n + 1

    pre_snap = _make_snapshot("snap_pre_gen", generation_id=gen_n)
    # Post-action snapshot has new generation ID (e.g. display geometry resized)
    post_snap = _make_snapshot("snap_post_gen", generation_id=gen_n_plus_1)

    obs.queue_mock_snapshot(pre_snap)
    obs.queue_mock_snapshot(post_snap)

    action = Action(
        action_id="act_gen_01",
        task_id="task_gen_01",
        action_type="pointer_click",
        tier=ActionTier.TIER_2_CONSTRAINED,
        parameters={
            "x": 250,
            "y": 250,
            "desktop_generation_id": gen_n,
            "expected_outcome": {
                "outcome_type": "ANY_OBSERVABLE_CHANGE",
                "strategy": "OBSERVATION_STATE_DELTA",
            },
        },
    )

    cancel_source = CancellationSource()
    with pytest.raises(RuntimeError) as exc_info:
        await orch._execute_action("sess_01", action, cancel_source.token)

    # Must fail closed: generation mismatch must never produce VERIFIED!
    assert "Action verification failed (STALE_EVIDENCE)" in str(exc_info.value)
    assert action.stage == ActionStage.FAILED
    assert action.error.code == "STALE_EVIDENCE"
    assert "Desktop generation changed across action dispatch" in action.verification.details["failure_reason"]


@pytest.mark.asyncio
async def test_post_action_verification_human_takeover_preemption(verification_env):
    """Flow 5: Action completes dispatch -> takeover activates -> verification cancelled safely."""
    orch, obs, ptr, wsp, tkv, bus = verification_env
    await orch.initialize()

    pre_snap = _make_snapshot("snap_pre_tkv", generation_id=wsp.desktop_generation_id)
    obs.queue_mock_snapshot(pre_snap)

    action = Action(
        action_id="act_tkv_flow_01",
        task_id="task_tkv_flow_01",
        action_type="pointer_click",
        tier=ActionTier.TIER_2_CONSTRAINED,
        parameters={
            "x": 500,
            "y": 500,
            "desktop_generation_id": wsp.desktop_generation_id,
            "expected_outcome": {
                "outcome_type": "ANY_OBSERVABLE_CHANGE",
                "strategy": "OBSERVATION_STATE_DELTA",
            },
        },
    )

    # Transition system state to HUMAN_TAKEOVER_ACTIVE
    orch._system_sm.transition_to(SystemState.HUMAN_TAKEOVER_ACTIVE)

    cancel_source = CancellationSource()
    with pytest.raises(RuntimeError) as exc_info:
        await orch._execute_action("sess_01", action, cancel_source.token)

    assert "Human takeover" in str(exc_info.value)
    assert action.stage == ActionStage.FAILED
    assert action.error.code == "HUMAN_TAKEOVER_ACTIVE"
