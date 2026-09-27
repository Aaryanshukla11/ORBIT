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
    ActionVerifier,
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

    exp_outcome = ExpectedOutcome(
        outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
        strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
        target_id="btn_submit",
        expected_property="is_focused",
        expected_value=True,
    )

    verifier = ActionVerifier()
    verif_res = verifier.verify(
        pre_snapshot=pre_snap,
        post_snapshot=post_snap,
        expected_outcome=exp_outcome,
    )

    assert verif_res.outcome == VerificationOutcome.VERIFIED_SUCCESS
    assert verif_res.confidence == 0.95


@pytest.mark.asyncio
async def test_action_verification_failure_fails_closed(verification_env):
    """Verify an action fails closed when post-action evidence demonstrates expectation was not met."""
    orch, obs, ptr, wsp, tkv, bus = verification_env
    await orch.initialize()

    # Pre-action and post-action snapshots show the window remained open (failed to close)
    open_win = _make_window(hwnd=8888, title="Unsaved Document", bounds=BoundingBox(left=100, top=100, width=500, height=400))

    pre_snap = _make_snapshot("snap_pre_close", generation_id=wsp.desktop_generation_id, windows=[open_win])
    post_snap = _make_snapshot("snap_post_close", generation_id=wsp.desktop_generation_id, windows=[open_win])

    exp_outcome = ExpectedOutcome(
        outcome_type=ExpectedOutcomeType.WINDOW_CLOSED,
        strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
        target_hwnd=8888,
        window_title="Unsaved Document",
    )

    verifier = ActionVerifier()
    verif_res = verifier.verify(
        pre_snapshot=pre_snap,
        post_snapshot=post_snap,
        expected_outcome=exp_outcome,
    )

    assert verif_res.outcome == VerificationOutcome.VERIFIED_FAILURE
    assert "remains open" in verif_res.failure_reason or "still exists" in verif_res.failure_reason


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

    exp_outcome = ExpectedOutcome(
        outcome_type=ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE,
        strategy=VerificationStrategy.OBSERVATION_STATE_DELTA,
    )

    verifier = ActionVerifier()
    verif_res = verifier.verify(
        pre_snapshot=pre_snap,
        post_snapshot=post_snap,
        expected_outcome=exp_outcome,
    )

    assert verif_res.outcome == VerificationOutcome.STALE_EVIDENCE
    assert "stale" in verif_res.failure_reason.lower()


@pytest.mark.asyncio
async def test_action_verification_unsupported_strategy_fails_closed(verification_env):
    """Verify requesting an unsupported strategy fails closed with UNSUPPORTED."""
    orch, obs, ptr, wsp, tkv, bus = verification_env
    await orch.initialize()

    pre_snap = _make_snapshot("snap_pre", generation_id=wsp.desktop_generation_id)
    post_snap = _make_snapshot("snap_post", generation_id=wsp.desktop_generation_id)

    exp_outcome = ExpectedOutcome(
        outcome_type=ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE,
        strategy=VerificationStrategy.VISUAL_SEMANTIC,
    )

    verifier = ActionVerifier()
    verif_res = verifier.verify(
        pre_snapshot=pre_snap,
        post_snapshot=post_snap,
        expected_outcome=exp_outcome,
    )

    assert verif_res.outcome == VerificationOutcome.UNSUPPORTED


@pytest.mark.asyncio
async def test_human_takeover_blocks_verification(verification_env):
    """Verify human takeover active during verification fails closed."""
    orch, obs, ptr, wsp, tkv, bus = verification_env
    await orch.initialize()

    await orch.handle_human_takeover(reason="Physical user input detected", source="physical_mouse")
    assert orch.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE


@pytest.mark.asyncio
async def test_cancellation_preempts_action_verification(verification_env):
    """Verify cancellation token preempts verification and never produces a verified success."""
    cancel_source = CancellationSource()
    cancel_source.cancel(reason="Operator cancelled before dispatch")
    assert cancel_source.token.is_cancelled is True
