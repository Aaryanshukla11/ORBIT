"""Integration tests for Task Completion with Dynamic Replanning Recovery (M1.8 Step 5)."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from PIL import Image

from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.adapters.registry import CapabilityRegistry
from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.runtime import SystemState
from orbit.models.common import BoundingBox
from orbit.runtime.execution import ClosedLoopExecutionEngine
from orbit.runtime.plan_execution import PlanExecutor
from orbit.runtime.replanning import DynamicReplanner
from orbit.runtime.task_completion import (
    TaskCompletionEngine,
    TaskCompletionStatus,
    TaskExecutionResult,
)
from orbit.runtime.targeting import (
    ResolvedTarget,
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
    TargetStrategy,
)
from orbit.runtime.targeting.models import TargetResolutionResult, TargetResolutionStatus
from orbit.runtime.verification import (
    ActionVerificationResult,
    ObservationEvidenceSummary,
    VerificationOutcome,
    VerificationStrategy,
)
from orbit.runtime.verification.evidence import summarize_observation_evidence
from orbit.infrastructure.event_bus import EventBus


def _make_snapshot(generation_id: int = 1, text: str = "Test", hwnd: int = 12345, is_fg: bool = True) -> ObservationSnapshot:
    win = ObservedWindow(
        hwnd=hwnd,
        window_title="Untitled - Notepad",
        process_name="notepad.exe",
        process_id=9999,
        extended_bounds=BoundingBox(left=100, top=100, width=800, height=600),
        is_visible=True,
        is_foreground=is_fg,
        dpi_scaling=1.0,
    )
    el = ObservedElement(
        element_id="el_doc",
        source="accessibility",
        name=f"Document Text: {text}",
        control_type="Edit",
        role="edit",
        bounds=BoundingBox(left=110, top=110, width=780, height=580),
    )
    return ObservationSnapshot(
        snapshot_id=f"snap_rec_{generation_id}",
        generation_id=generation_id,
        timestamp_ns=100000 + generation_id * 1000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        foreground_window=win if is_fg else None,
        windows=[win],
        detected_elements=[el],
    )


@pytest.mark.asyncio
async def test_task_completion_with_focus_loss_recovery():
    """Test end-to-end task recovering from focus loss mid-flight and successfully verifying final text."""
    bus = EventBus()
    state = {"text": "", "generation": 1, "is_fg": True, "focus_drops_left": 1}

    def _get_snap(*args, **kwargs):
        # Simulate a transient focus drop on call 3, then recovery
        if state["focus_drops_left"] > 0 and state["generation"] >= 2:
            state["focus_drops_left"] -= 1
            is_fg = False
        else:
            is_fg = True
        state["generation"] += 1
        return _make_snapshot(generation_id=state["generation"], text=state["text"], is_fg=is_fg)

    async def _mock_type(text, *args, **kwargs):
        state["text"] = text
        state["generation"] += 1
        return True

    mock_obs = MagicMock()
    mock_obs.capture_snapshot = AsyncMock(side_effect=_get_snap)
    mock_obs.capture_screen = AsyncMock(return_value=None)
    mock_obs.is_ready = True

    mock_ptr = MagicMock()
    mock_ptr.click = AsyncMock(return_value=True)
    mock_ptr.move_to = AsyncMock(return_value=True)
    mock_ptr.is_ready = True

    mock_kbd = MagicMock()
    mock_kbd.type_text = AsyncMock(side_effect=_mock_type)
    mock_kbd.is_ready = True

    locator = MagicMock()
    tb = TargetBoundingBox.from_bounding_box(BoundingBox(left=110, top=110, width=780, height=580))
    safe_pt = SafeActionPoint(
        x=200, y=200,
        bounding_box=tb,
        desktop_generation_id=1,
    )
    ev = TargetEvidence(
        source="ACCESSIBILITY",
        identifier="el_doc",
        name="Document Text",
        confidence=0.95,
    )
    resolved_tgt = ResolvedTarget(
        target_id="tgt_edit",
        target_hwnd=12345,
        desktop_generation_id=1,
        safe_point=safe_pt,
        bounding_box=tb,
        confidence=0.95,
        evidence=ev,
        observation_id="snap_rec_1",
    )
    res_tgt_result = TargetResolutionResult(
        status=TargetResolutionStatus.RESOLVED,
        target=resolved_tgt,
        candidates_count=1,
    )
    locator.locate_target = MagicMock(return_value=res_tgt_result)

    verifier = MagicMock()
    verif_ok = ActionVerificationResult(
        outcome=VerificationOutcome.VERIFIED_SUCCESS,
        strategy_used=VerificationStrategy.WINDOW_STATE_CHANGE,
        confidence=0.95,
        pre_generation_id=1,
        post_generation_id=2,
        pre_evidence=summarize_observation_evidence(_make_snapshot(1, "")),
    )
    verifier.verify = MagicMock(return_value=verif_ok)

    exec_engine = ClosedLoopExecutionEngine(
        observation=mock_obs,
        pointer=mock_ptr,
        keyboard=mock_kbd,
        target_locator=locator,
        action_verifier=verifier,
        event_bus=bus,
        system_state_getter=lambda: SystemState.IDLE,
    )

    replanner = DynamicReplanner(observation=mock_obs)
    plan_executor = PlanExecutor(execution_engine=exec_engine, replanner=replanner, event_bus=bus)
    engine = TaskCompletionEngine(
        plan_executor=plan_executor,
        observation=mock_obs,
    )

    task_result: TaskExecutionResult = await engine.execute_task(
        goal="Open Notepad and write: Recovered Text",
        session_id="recovery_session",
    )

    assert task_result.completion_status == TaskCompletionStatus.COMPLETED
    assert task_result.is_success is True
    assert task_result.evidence.verified_text == "Recovered Text"
