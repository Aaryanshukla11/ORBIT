"""Evidence collection and aggregation for Task Completion Verification (M1.8 Step 5)."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from PIL import Image

from orbit.adapters.observation.snapshot import ObservationSnapshot, ObservedWindow
from orbit.runtime.perception.models import OCRResult, OCRTextRegion
from orbit.runtime.plan_execution.models import PlanExecutionResult
from orbit.runtime.task_completion.models import TaskCompletionEvidence

logger = logging.getLogger(__name__)


class CompletionEvidenceCollector:
    """Collects and organizes multi-modal evidence for final goal verification."""

    def build_evidence(
        self,
        snapshot: Optional[ObservationSnapshot] = None,
        plan_result: Optional[PlanExecutionResult] = None,
        target_app: Optional[str] = None,
        target_hwnd: Optional[int] = None,
        verified_text: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None,
        matching_ocr_regions: Optional[List[OCRTextRegion]] = None,
        accessibility_elements: Optional[List[str]] = None,
        canvas_pixel_diff_ratio: Optional[float] = None,
        visual_changes: Optional[List[str]] = None,
        clipboard_content: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> TaskCompletionEvidence:
        """Assemble a complete TaskCompletionEvidence instance."""
        gen_id = snapshot.generation_id if snapshot else 0
        obs_id = snapshot.snapshot_id if snapshot else None

        app_is_open = False
        app_in_fg = False
        resolved_hwnd = target_hwnd

        if snapshot is not None:
            # Check window list
            for w in snapshot.windows:
                if target_hwnd is not None and w.hwnd == target_hwnd:
                    app_is_open = True
                    resolved_hwnd = w.hwnd
                    break
                elif target_app is not None:
                    title = (w.window_title or "").lower()
                    pname = (w.process_name or "").lower()
                    q = target_app.lower()
                    if q in title or q in pname:
                        app_is_open = True
                        resolved_hwnd = w.hwnd
                        break

            # Check foreground window
            if snapshot.foreground_window is not None:
                fg = snapshot.foreground_window
                if resolved_hwnd is not None and fg.hwnd == resolved_hwnd:
                    app_in_fg = True
                elif target_app is not None:
                    fg_title = (fg.window_title or "").lower()
                    fg_proc = (fg.process_name or "").lower()
                    q = target_app.lower()
                    if q in fg_title or q in fg_proc:
                        app_in_fg = True

        completed_steps: List[str] = []
        total_steps = 0
        replan_count = 0

        if plan_result is not None:
            completed_steps = [
                s.step_id for s in plan_result.step_results
                if s.status.value == "SUCCEEDED"
            ]
            total_steps = plan_result.total_steps
            replan_count = plan_result.diagnostics.get("total_replans", 0)

        ocr_text = None
        ocr_conf = None
        ocr_count = 0

        if matching_ocr_regions:
            ocr_text = " ".join([r.text for r in matching_ocr_regions])
            confidences = [r.confidence for r in matching_ocr_regions if r.confidence is not None]
            ocr_conf = sum(confidences) / len(confidences) if confidences else 1.0
            ocr_count = len(matching_ocr_regions)
        elif ocr_result is not None and ocr_result.is_success:
            ocr_text = ocr_result.full_text

        return TaskCompletionEvidence(
            final_generation_id=gen_id,
            observation_id=obs_id,
            application_name=target_app,
            application_hwnd=resolved_hwnd,
            application_is_open=app_is_open,
            application_in_foreground=app_in_fg,
            verified_text=verified_text,
            ocr_matched_text=ocr_text,
            ocr_confidence=ocr_conf,
            ocr_regions_count=ocr_count,
            visual_changes_detected=visual_changes or [],
            accessibility_matched_elements=accessibility_elements or [],
            canvas_pixel_difference_ratio=canvas_pixel_diff_ratio,
            clipboard_verified_content=clipboard_content,
            completed_step_ids=completed_steps,
            total_steps=total_steps,
            replan_count=replan_count,
            verification_timestamp_utc=datetime.now(timezone.utc),
            diagnostics=diagnostics or {},
        )
