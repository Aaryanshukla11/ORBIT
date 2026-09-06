"""Integration tests for Multi-Application and Cross-Application Workflows (M1.8 Step 5)."""

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


def _make_multi_app_snapshot(
    generation_id: int = 1,
    notepad_text: str = "Test Transfer",
    browser_search_text: str = "Test Transfer",
    browser_open: bool = True,
) -> ObservationSnapshot:
    notepad_win = ObservedWindow(
        hwnd=1001,
        window_title="Untitled - Notepad",
        process_name="notepad.exe",
        process_id=9001,
        extended_bounds=BoundingBox(left=50, top=50, width=600, height=500),
        is_visible=True,
        is_foreground=not browser_open,
        dpi_scaling=1.0,
    )
    elements = [
        ObservedElement(
            element_id="el_np_edit",
            source="accessibility",
            name=f"Text Editor: {notepad_text}",
            control_type="Edit",
            role="edit",
            bounds=BoundingBox(left=60, top=60, width=580, height=480),
        )
    ]
    windows = [notepad_win]

    fg = notepad_win
    if browser_open:
        browser_win = ObservedWindow(
            hwnd=2002,
            window_title="Search Engine - Google Chrome",
            process_name="chrome.exe",
            process_id=9002,
            extended_bounds=BoundingBox(left=700, top=50, width=800, height=600),
            is_visible=True,
            is_foreground=True,
            dpi_scaling=1.0,
        )
        windows.append(browser_win)
        fg = browser_win
        elements.append(
            ObservedElement(
                element_id="el_search_box",
                source="accessibility",
                name=f"Search Query: {browser_search_text}",
                control_type="Edit",
                role="edit",
                bounds=BoundingBox(left=750, top=150, width=500, height=40),
            )
        )

    return ObservationSnapshot(
        snapshot_id=f"snap_cross_{generation_id}",
        generation_id=generation_id,
        timestamp_ns=100000 + generation_id * 1000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        foreground_window=fg,
        windows=windows,
        detected_elements=elements,
    )


@pytest.mark.asyncio
async def test_cross_application_notepad_to_browser_transfer():
    """Test full cross-application task: write phrase, copy, paste into browser search, verify outcome."""
    bus = EventBus()

    state = {
        "notepad_text": "",
        "browser_search_text": "",
        "browser_open": False,
        "generation": 1,
    }

    def _get_snap(*args, **kwargs):
        return _make_multi_app_snapshot(
            generation_id=state["generation"],
            notepad_text=state["notepad_text"],
            browser_search_text=state["browser_search_text"],
            browser_open=state["browser_open"],
        )

    async def _mock_type(text, *args, **kwargs):
        state["notepad_text"] = text
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
    mock_kbd.press_shortcut = AsyncMock(return_value=True)
    mock_kbd.is_ready = True

    locator = MagicMock()
    tb = TargetBoundingBox.from_bounding_box(BoundingBox(left=60, top=60, width=580, height=480))
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
        target_hwnd=1001,
        desktop_generation_id=1,
        safe_point=safe_pt,
        bounding_box=tb,
        confidence=0.95,
        evidence=ev,
        observation_id="snap_cross_1",
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
        strategy_used=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
        confidence=0.95,
        pre_generation_id=1,
        post_generation_id=2,
        pre_evidence=summarize_observation_evidence(_make_multi_app_snapshot(1, "", "", False)),
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
        goal="Open Notepad and write: ORBIT Cross App Transfer",
        session_id="cross_app_session",
    )

    assert task_result.completion_status == TaskCompletionStatus.COMPLETED
    assert task_result.is_success is True
    assert task_result.evidence.application_name == "Notepad"
    assert task_result.evidence.verified_text == "ORBIT Cross App Transfer"
