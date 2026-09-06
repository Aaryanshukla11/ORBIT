"""Integration tests for ORBIT M1.6 Step 2: Post-Action Verification Engine lifecycle flow."""

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
    VerificationResult,
    VerificationStatus,
)
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
from orbit.runtime.cancellation import CancellationSource
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.verification import (
    ExpectedOutcome,
    ExpectedOutcomeType,
    VerificationOutcome,
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
async def test_action_verification_success_flow(verification_env):
    """Verify an action succeeds and transitions to COMPLETED when evidence confirms expectation."""
    orch, obs, ptr, wsp, tkv, bus = verification_env
    await orch.initialize()

    # Pre-action snapshot: button exists and is not focused
    pre_el = ObservedElement(
        element_id="btn_submit",
        source="MSAA",
        name="Submit",
        role="Button",
        bounds=BoundingBox(left=500, top=300, width=100, height=35),
        is_focused=False,
    )
    post_el = ObservedElement(
        element_id="btn_submit",
        source="MSAA",
        name="Submit",
        role="Button",
        bounds=BoundingBox(left=500, top=300, width=100, height=35),
        is_focused=True,
    )

    pre_snap = _make_snapshot("snap_pre_01", generation_id=wsp.desktop_generation_id, elements=[pre_el])
    post_snap = _make_snapshot("snap_post_01", generation_id=wsp.desktop_generation_id, elements=[post_el])

    obs.queue_mock_snapshot(pre_snap)
    obs.queue_mock_snapshot(post_snap)

    action = Action(
        action_id="act_click_verify_01",
        task_id="task_verif_01",
        action_type="pointer_click",
        tier=ActionTier.TIER_2_CONSTRAINED,
        parameters={
            "x": 550,
            "y": 315,
            "desktop_generation_id": wsp.desktop_generation_id,
            "expected_outcome": {
                "outcome_type": "ELEMENT_STATE_CHANGED",
                "strategy": "ACCESSIBILITY_STATE_CHANGE",
                "target_id": "btn_submit",
                "expected_property": "is_focused",
                "expected_value": True,
            },
        },
    )

    cancel_source = CancellationSource()
    await orch._execute_action("sess_01", action, cancel_source.token)

    assert action.stage == ActionStage.COMPLETED
    assert action.verification is not None
    assert action.verification.status == VerificationStatus.PASSED
    assert action.verification.confidence == 0.95
    assert action.verification.details["outcome"] == "VERIFIED_SUCCESS"


@pytest.mark.asyncio
async def test_action_verification_failure_fails_closed(verification_env):
    """Verify an action fails closed when post-action evidence demonstrates expectation was not met."""
    orch, obs, ptr, wsp, tkv, bus = verification_env
    await orch.initialize()

    # Pre-action and post-action snapshots show the window remained open (failed to close)
    open_win = _make_window(hwnd=8888, title="Unsaved Document", bounds=BoundingBox(left=100, top=100, width=500, height=400))

    pre_snap = _make_snapshot("snap_pre_close", generation_id=wsp.desktop_generation_id, windows=[open_win])
    post_snap = _make_snapshot("snap_post_close", generation_id=wsp.desktop_generation_id, windows=[open_win])

    obs.queue_mock_snapshot(pre_snap)
    obs.queue_mock_snapshot(post_snap)

    action = Action(
        action_id="act_close_01",
        task_id="task_close_01",
        action_type="pointer_click",
        tier=ActionTier.TIER_2_CONSTRAINED,
        parameters={
            "x": 580,
            "y": 110,
            "desktop_generation_id": wsp.desktop_generation_id,
            "expected_outcome": {
                "outcome_type": "WINDOW_CLOSED",
                "strategy": "WINDOW_STATE_CHANGE",
                "target_hwnd": 8888,
                "window_title": "Unsaved Document",
            },
        },
    )

    cancel_source = CancellationSource()
    with pytest.raises(RuntimeError) as exc_info:
        await orch._execute_action("sess_01", action, cancel_source.token)

    assert "Action verification failed (VERIFIED_FAILURE)" in str(exc_info.value)
    assert action.stage == ActionStage.FAILED
    assert action.verification is not None
    assert action.verification.status == VerificationStatus.FAILED
    assert action.verification.details["outcome"] == "VERIFIED_FAILURE"
    assert action.error is not None
    assert action.error.code == "VERIFIED_FAILURE"


@pytest.mark.asyncio
async def test_action_verification_stale_evidence_fails_closed(verification_env):
    """Verify stale post-action observation evidence fails closed immediately."""
    orch, obs, ptr, wsp, tkv, bus = verification_env
    await orch.initialize()

    pre_snap = _make_snapshot("snap_pre_fresh", generation_id=wsp.desktop_generation_id)
    post_snap = _make_snapshot(
        "snap_post_stale",
        generation_id=wsp.desktop_generation_id,
        is_stale=True,
        invalidation_reason="Desktop reconfigured during dispatch",
    )

    obs.queue_mock_snapshot(pre_snap)
    obs.queue_mock_snapshot(post_snap)

    action = Action(
        action_id="act_stale_01",
        task_id="task_stale_01",
        action_type="pointer_click",
        tier=ActionTier.TIER_2_CONSTRAINED,
        parameters={
            "x": 400,
            "y": 400,
            "desktop_generation_id": wsp.desktop_generation_id,
            "expected_outcome": {
                "outcome_type": "ANY_OBSERVABLE_CHANGE",
                "strategy": "OBSERVATION_STATE_DELTA",
            },
        },
    )

    cancel_source = CancellationSource()
    with pytest.raises(RuntimeError) as exc_info:
        await orch._execute_action("sess_01", action, cancel_source.token)

    assert "Action verification failed (STALE_EVIDENCE)" in str(exc_info.value)
    assert action.stage == ActionStage.FAILED
    assert action.error.code == "STALE_EVIDENCE"


@pytest.mark.asyncio
async def test_action_verification_unsupported_strategy_fails_closed(verification_env):
    """Verify requesting an unsupported strategy like VISUAL_SEMANTIC fails closed with UNSUPPORTED."""
    orch, obs, ptr, wsp, tkv, bus = verification_env
    await orch.initialize()

    pre_snap = _make_snapshot("snap_pre", generation_id=wsp.desktop_generation_id)
    post_snap = _make_snapshot("snap_post", generation_id=wsp.desktop_generation_id)

    obs.queue_mock_snapshot(pre_snap)
    obs.queue_mock_snapshot(post_snap)

    action = Action(
        action_id="act_unsupported_01",
        task_id="task_unsupported_01",
        action_type="pointer_click",
        tier=ActionTier.TIER_2_CONSTRAINED,
        parameters={
            "x": 300,
            "y": 200,
            "desktop_generation_id": wsp.desktop_generation_id,
            "expected_outcome": {
                "outcome_type": "ANY_OBSERVABLE_CHANGE",
                "strategy": "VISUAL_SEMANTIC",
            },
        },
    )

    cancel_source = CancellationSource()
    with pytest.raises(RuntimeError) as exc_info:
        await orch._execute_action("sess_01", action, cancel_source.token)

    assert "Action verification failed (UNSUPPORTED)" in str(exc_info.value)
    assert action.stage == ActionStage.FAILED
    assert action.error.code == "UNSUPPORTED"


@pytest.mark.asyncio
async def test_human_takeover_blocks_verification(verification_env):
    """Verify human takeover active during verification fails closed and prevents completion."""
    orch, obs, ptr, wsp, tkv, bus = verification_env
    await orch.initialize()

    # Pre-action snapshot
    pre_snap = _make_snapshot("snap_pre", generation_id=wsp.desktop_generation_id)
    obs.queue_mock_snapshot(pre_snap)

    action = Action(
        action_id="act_tkv_01",
        task_id="task_tkv_01",
        action_type="pointer_click",
        tier=ActionTier.TIER_2_CONSTRAINED,
        parameters={
            "x": 350,
            "y": 250,
            "desktop_generation_id": wsp.desktop_generation_id,
            "expected_outcome": {
                "outcome_type": "ANY_OBSERVABLE_CHANGE",
                "strategy": "OBSERVATION_STATE_DELTA",
            },
        },
    )

    # Trigger human takeover
    orch._system_sm.transition_to(SystemState.HUMAN_TAKEOVER_ACTIVE)

    cancel_source = CancellationSource()
    with pytest.raises(RuntimeError) as exc_info:
        await orch._execute_action("sess_01", action, cancel_source.token)

    assert "Human takeover is currently active" in str(exc_info.value)
    assert action.stage == ActionStage.FAILED
    assert action.error.code == "HUMAN_TAKEOVER_ACTIVE"


@pytest.mark.asyncio
async def test_cancellation_preempts_action_verification(verification_env):
    """Verify cancellation token preempts verification and never produces a verified success."""
    orch, obs, ptr, wsp, tkv, bus = verification_env
    await orch.initialize()

    action = Action(
        action_id="act_cancel_01",
        task_id="task_cancel_01",
        action_type="pointer_click",
        tier=ActionTier.TIER_2_CONSTRAINED,
        parameters={
            "x": 200,
            "y": 200,
            "desktop_generation_id": wsp.desktop_generation_id,
            "expected_outcome": {
                "outcome_type": "ANY_OBSERVABLE_CHANGE",
                "strategy": "OBSERVATION_STATE_DELTA",
            },
        },
    )

    cancel_source = CancellationSource()
    cancel_source.cancel(reason="Operator cancelled before dispatch")

    await orch._execute_action("sess_01", action, cancel_source.token)

    assert action.stage == ActionStage.CANCELLED
    assert action.verification is None
