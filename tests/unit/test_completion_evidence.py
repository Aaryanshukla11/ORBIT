"""Unit tests for CompletionEvidenceCollector (M1.8 Step 5)."""

import pytest
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.models.common import BoundingBox
from orbit.runtime.perception.models import OCRBoundingBox, OCRResult, OCRStatus, OCRTextRegion
from orbit.runtime.plan_execution.models import (
    PlanExecutionResult,
    PlanExecutionStatus,
    PlanStepExecutionResult,
    PlanStepExecutionStatus,
)
from orbit.runtime.planning.models import PlanActionType
from orbit.runtime.task_completion.evidence import CompletionEvidenceCollector
from orbit.runtime.task_completion.models import TaskCompletionEvidence


def _make_snapshot(generation_id: int = 1, hwnd: int = 12345, title: str = "Notepad", elements=None) -> ObservationSnapshot:
    win = ObservedWindow(
        hwnd=hwnd,
        window_title=title,
        process_name="notepad.exe",
        process_id=9999,
        extended_bounds=BoundingBox(left=100, top=100, width=800, height=600),
        is_visible=True,
        is_foreground=True,
        dpi_scaling=1.0,
    )
    return ObservationSnapshot(
        snapshot_id="snap_unit_test",
        generation_id=generation_id,
        timestamp_ns=100000,
        ttl_ms=500.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        foreground_window=win,
        windows=[win],
        detected_elements=elements or [],
    )


def test_completion_evidence_builder_with_full_evidence():
    collector = CompletionEvidenceCollector()
    el = ObservedElement(
        element_id="el_1",
        source="accessibility",
        name="Document text: Hello ORBIT",
        control_type="Edit",
        role="edit",
        bounds=BoundingBox(left=110, top=110, width=780, height=580),
    )
    snap = _make_snapshot(generation_id=2, hwnd=12345, title="Untitled - Notepad", elements=[el])

    step_res = PlanStepExecutionResult(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ENTER_TEXT,
        status=PlanStepExecutionStatus.SUCCEEDED,
    )
    plan_res = PlanExecutionResult(
        plan_id="plan_1",
        task_id="task_1",
        final_status=PlanExecutionStatus.SUCCEEDED,
        is_success=True,
        total_steps=1,
        completed_steps=1,
        step_results=[step_res],
        diagnostics={"total_replans": 1},
    )

    ocr_reg = OCRTextRegion(
        text="Hello ORBIT",
        normalized_text="hello orbit",
        bounding_box=OCRBoundingBox(left=120, top=120, right=320, bottom=150),
        confidence=0.98,
        source_provider="windows_native_ocr",
    )

    evidence: TaskCompletionEvidence = collector.build_evidence(
        snapshot=snap,
        plan_result=plan_res,
        target_app="Notepad",
        target_hwnd=12345,
        verified_text="Hello ORBIT",
        matching_ocr_regions=[ocr_reg],
        accessibility_elements=["Edit:Document text: Hello ORBIT"],
        canvas_pixel_diff_ratio=None,
        clipboard_content=None,
    )

    assert evidence.final_generation_id == 2
    assert evidence.application_name == "Notepad"
    assert evidence.application_hwnd == 12345
    assert evidence.application_is_open is True
    assert evidence.application_in_foreground is True
    assert evidence.verified_text == "Hello ORBIT"
    assert evidence.ocr_matched_text == "Hello ORBIT"
    assert evidence.ocr_confidence == 0.98
    assert evidence.ocr_regions_count == 1
    assert "Edit:Document text: Hello ORBIT" in evidence.accessibility_matched_elements
    assert "step_1" in evidence.completed_steps
    assert evidence.replan_count == 1


def test_completion_evidence_builder_missing_snapshot():
    collector = CompletionEvidenceCollector()
    evidence: TaskCompletionEvidence = collector.build_evidence(
        snapshot=None,
        target_app="Notepad",
    )

    assert evidence.final_generation_id == 0
    assert evidence.observation_id is None
    assert evidence.application_is_open is False
    assert evidence.application_in_foreground is False
