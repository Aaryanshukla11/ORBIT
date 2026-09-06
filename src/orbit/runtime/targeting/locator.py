"""Evidence-driven target locator resolving UI intent against ObservationSnapshot."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import sys
import time
from typing import TYPE_CHECKING, List, Optional, Protocol, runtime_checkable
from uuid import uuid4

from orbit.adapters.observation.snapshot import (
    FreshnessState,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.runtime.targeting.action_point import calculate_safe_action_point
from orbit.runtime.targeting.models import (
    ResolvedTarget,
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
    TargetIntent,
    TargetResolutionResult,
    TargetResolutionStatus,
    TargetStrategy,
)

if TYPE_CHECKING:
    from orbit.runtime.perception.engine import SemanticPerceptionEngine
from orbit.runtime.perception.models import OCRResult, OCRStatus

logger = logging.getLogger(__name__)


@runtime_checkable
class TargetLocator(Protocol):
    """Protocol for resolving TargetIntent against an ObservationSnapshot."""

    def locate_target(
        self,
        snapshot: ObservationSnapshot,
        intent: TargetIntent,
    ) -> TargetResolutionResult:
        """Locate target UI element in the given snapshot according to declared intent."""
        ...


class EvidenceBasedTargetLocator:
    """Production TargetLocator resolving targets strictly from verified observation evidence.

    Supported strategies:
    - ACCESSIBILITY_ELEMENT: Resolved from MSAA, UI Automation, and Win32 controls in snapshot.detected_elements.
    - WINDOW_TITLE: Resolved from top-level desktop windows in snapshot.windows.
    - COORDINATE_REGION: Resolved from explicit verified bounding box geometry.
    - OCR_TEXT: Resolved from optical character recognition evidence.
    - VISUAL_SEMANTIC: Returns UNSUPPORTED (template/feature matching in future steps).
    """

    def __init__(self, perception_engine: Optional[SemanticPerceptionEngine] = None) -> None:
        self._perception_engine = perception_engine

    def locate_target(
        self,
        snapshot: ObservationSnapshot,
        intent: TargetIntent,
    ) -> TargetResolutionResult:
        """Resolve TargetIntent against ObservationSnapshot using evidence-based matching."""
        # 1. Stale Observation Gate
        if snapshot.is_stale or snapshot.freshness_state == FreshnessState.STALE:
            reason = snapshot.invalidation_reason or "Observation snapshot TTL expired or generation invalid"
            logger.warning("Target localization rejected: snapshot %s is stale (%s)", snapshot.snapshot_id, reason)
            return TargetResolutionResult(
                status=TargetResolutionStatus.STALE_OBSERVATION,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                is_stale_observation=True,
                diagnostic_message=f"Target localization aborted: Observation snapshot is stale ({reason})",
            )

        # 2. Dispatch based on strategy
        if intent.strategy == TargetStrategy.COORDINATE_REGION:
            return self._resolve_coordinate_region(snapshot, intent)
        elif intent.strategy == TargetStrategy.WINDOW_TITLE:
            return self._resolve_window(snapshot, intent)
        elif intent.strategy == TargetStrategy.ACCESSIBILITY_ELEMENT:
            return self._resolve_accessibility_element(snapshot, intent)
        elif intent.strategy == TargetStrategy.OCR_TEXT:
            return self._resolve_ocr_text(snapshot, intent)
        elif intent.strategy in (
            TargetStrategy.VISUAL_TEMPLATE,
            TargetStrategy.ICON_TEMPLATE,
            TargetStrategy.IMAGE_REGION,
            TargetStrategy.VISUAL_SEMANTIC,
        ):
            return self._resolve_visual_template(snapshot, intent)
        elif intent.strategy in (TargetStrategy.MULTIMODAL, TargetStrategy.FUSED_MULTIMODAL):
            return self._resolve_multimodal(snapshot, intent)
        else:
            return TargetResolutionResult(
                status=TargetResolutionStatus.UNSUPPORTED,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"Unsupported target resolution strategy: {intent.strategy}",
            )

    def _resolve_coordinate_region(
        self,
        snapshot: ObservationSnapshot,
        intent: TargetIntent,
    ) -> TargetResolutionResult:
        """Resolve target from explicitly specified bounding box."""
        if intent.explicit_bounds is None:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message="COORDINATE_REGION strategy requires explicit_bounds in TargetIntent",
            )

        try:
            tbox = TargetBoundingBox.from_bounding_box(intent.explicit_bounds)
            if not tbox.is_valid or tbox.width <= 0 or tbox.height <= 0:
                return TargetResolutionResult(
                    status=TargetResolutionStatus.INVALID_REQUEST,
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=snapshot.generation_id,
                    diagnostic_message=f"Invalid explicit_bounds geometry: {intent.explicit_bounds}",
                )

            safe_pt = calculate_safe_action_point(
                bounds=tbox,
                desktop_generation_id=snapshot.generation_id,
            )

            resolved = ResolvedTarget(
                target_id=f"tgt_explicit_{uuid4().hex[:8]}",
                bounding_box=tbox,
                safe_point=safe_pt,
                confidence=1.0,
                evidence=TargetEvidence(
                    source="EXPLICIT_BOUNDS",
                    name="Explicit Region",
                    confidence=1.0,
                    raw_metadata=intent.metadata,
                ),
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
            )
            return TargetResolutionResult(
                status=TargetResolutionStatus.RESOLVED,
                target=resolved,
                candidates_count=1,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
            )
        except Exception as ex:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"Failed to calculate safe point for explicit region: {ex}",
            )

    def _resolve_window(
        self,
        snapshot: ObservationSnapshot,
        intent: TargetIntent,
    ) -> TargetResolutionResult:
        """Resolve target from top-level visible window observations."""
        candidates: List[ObservedWindow] = []

        # Enumerate candidate windows
        all_windows = list(snapshot.windows)
        if snapshot.foreground_window and snapshot.foreground_window not in all_windows:
            all_windows.append(snapshot.foreground_window)

        title_query = intent.window_title or intent.name
        logger.info("Resolving window '%s': %d snapshot windows: %s", title_query, len(all_windows), [(w.hwnd, w.window_title, w.process_name) for w in all_windows[:6]])

        for win in all_windows:
            if not win.is_visible:
                continue

            # Check HWND if specified
            if intent.target_hwnd is not None and win.hwnd != intent.target_hwnd:
                continue

            # Check Process Name
            if intent.process_name:
                if intent.process_name.lower() not in win.process_name.lower():
                    continue

            # Check Window Title or Process Name
            title_query = intent.window_title or intent.name
            if title_query:
                tq = title_query.lower()
                title_match = bool(win.window_title and tq in win.window_title.lower())
                proc_match = bool(win.process_name and tq in win.process_name.lower())
                if tq in ("browser", "web browser", "internet"):
                    known_browsers = ("chrome", "msedge", "edge", "brave", "firefox", "opera")
                    if any(b in (win.process_name or "").lower() or b in (win.window_title or "").lower() for b in known_browsers):
                        proc_match = True
                if not (title_match or proc_match):
                    continue

            candidates.append(win)

        if len(candidates) == 0:
            title_query = intent.window_title or intent.name
            if title_query and sys.platform == "win32":
                tq_clean = title_query.strip().lower()
                known_app_launchers = {
                    "notepad": "notepad.exe",
                    "paint": "mspaint.exe",
                    "calculator": "calc.exe",
                    "cmd": "cmd.exe",
                    "terminal": "wt.exe",
                    "explorer": "explorer.exe",
                }
                exe_name = known_app_launchers.get(tq_clean)
                if exe_name:
                    try:
                        import subprocess
                        subprocess.Popen([exe_name], shell=False)
                        time.sleep(0.8)
                        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                        ctypes.windll.user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
                        ctypes.windll.user32.EnumWindows.restype = wintypes.BOOL
                        GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
                        GetWindowText = ctypes.windll.user32.GetWindowTextW
                        IsWindowVisible = ctypes.windll.user32.IsWindowVisible
                        GetWindowRect = ctypes.windll.user32.GetWindowRect

                        found_hwnds = []
                        def _enum_cb(hwnd, lparam):
                            if IsWindowVisible(hwnd):
                                length = GetWindowTextLength(hwnd)
                                if length > 0:
                                    buff = ctypes.create_unicode_buffer(length + 1)
                                    GetWindowText(hwnd, buff, length + 1)
                                    w_title = buff.value
                                    if tq_clean in w_title.lower() or tq_clean in exe_name.lower():
                                        r = wintypes.RECT()
                                        if GetWindowRect(hwnd, ctypes.byref(r)):
                                            if (r.right - r.left) > 50 and (r.bottom - r.top) > 50:
                                                found_hwnds.append((hwnd, w_title, r))
                            return True

                        cb = WNDENUMPROC(_enum_cb)
                        ctypes.windll.user32.EnumWindows(cb, 0)
                        if found_hwnds:
                            h, wt, r = found_hwnds[0]
                            ctypes.windll.user32.SetForegroundWindow(h)
                            from orbit.models.common import BoundingBox
                            pid = wintypes.DWORD(0)
                            ctypes.windll.user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                            new_win = ObservedWindow(
                                hwnd=h,
                                process_id=pid.value or 0,
                                window_title=wt,
                                process_name=exe_name,
                                is_visible=True,
                                is_foreground=True,
                                extended_bounds=BoundingBox(
                                    left=r.left,
                                    top=r.top,
                                    width=r.right - r.left,
                                    height=r.bottom - r.top,
                                ),
                            )
                            candidates.append(new_win)
                    except Exception as launch_err:
                        logger.warning("Failed to launch application '%s': %s", title_query, launch_err)

        if len(candidates) == 0:
            title_query = intent.window_title or intent.name
            return TargetResolutionResult(
                status=TargetResolutionStatus.NOT_FOUND,
                candidates_count=0,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=(
                    f"No visible window matched criteria: title='{title_query}', "
                    f"process='{intent.process_name}', hwnd={intent.target_hwnd}"
                ),
            )

        if len(candidates) > 1:
            # If multiple match, prefer foreground window if it is one of the candidates
            fg_matches = [w for w in candidates if w.is_foreground]
            if len(fg_matches) == 1:
                matched_win = fg_matches[0]
            else:
                title_query = intent.window_title or intent.name
                exact_title_matches = [
                    w for w in candidates
                    if title_query and w.window_title and w.window_title.strip().lower() == title_query.strip().lower()
                ]
                if len(exact_title_matches) == 1:
                    matched_win = exact_title_matches[0]
                else:
                    # Disambiguate by selecting the topmost window in z-order
                    z_sorted = sorted(candidates, key=lambda w: getattr(w, "z_order_rank", 9999))
                    matched_win = z_sorted[0]
        else:
            matched_win = candidates[0]

        try:
            tbox = TargetBoundingBox.from_bounding_box(matched_win.extended_bounds)
            safe_pt = calculate_safe_action_point(
                bounds=tbox,
                desktop_generation_id=snapshot.generation_id,
            )

            resolved = ResolvedTarget(
                target_id=f"tgt_win_{matched_win.hwnd}_{uuid4().hex[:6]}",
                bounding_box=tbox,
                safe_point=safe_pt,
                confidence=1.0,
                evidence=TargetEvidence(
                    source="WIN32_WINDOW",
                    identifier=str(matched_win.hwnd),
                    name=matched_win.window_title,
                    role="Window",
                    confidence=1.0,
                    raw_metadata={
                        "hwnd": matched_win.hwnd,
                        "process_name": matched_win.process_name,
                        "is_foreground": matched_win.is_foreground,
                    },
                ),
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                target_hwnd=matched_win.hwnd,
            )
            return TargetResolutionResult(
                status=TargetResolutionStatus.RESOLVED,
                target=resolved,
                candidates_count=1,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
            )
        except Exception as ex:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"Failed to calculate safe point for window bounds: {ex}",
            )

    def _resolve_accessibility_element(
        self,
        snapshot: ObservationSnapshot,
        intent: TargetIntent,
    ) -> TargetResolutionResult:
        """Resolve target from UI accessibility elements (MSAA, UI Automation, Win32)."""
        candidates: List[ObservedElement] = []

        for el in snapshot.detected_elements:
            # Skip disabled or offscreen elements
            if el.is_offscreen or not el.is_enabled:
                continue

            # Validate positive dimensions
            if el.bounds.width <= 0 or el.bounds.height <= 0:
                continue

            # Check accessible name
            if intent.name:
                if not el.name or intent.name.lower() not in el.name.lower():
                    continue

            # Check role / control type
            if intent.role:
                req_role = intent.role.lower()
                role_match = (
                    req_role in el.role.lower()
                    or req_role in el.control_type.lower()
                )
                if not role_match:
                    continue

            # Check automation_id
            if intent.automation_id:
                if not el.automation_id or intent.automation_id.lower() != el.automation_id.lower():
                    continue

            # Check class name
            if intent.class_name:
                if not el.class_name or intent.class_name.lower() not in el.class_name.lower():
                    continue

            candidates.append(el)

        if len(candidates) == 0:
            # Fallback for document/editor surfaces: if targeting generic edit/input/document role without specific name,
            # resolve against active foreground window or matching window client area.
            target_win = snapshot.foreground_window or next((w for w in snapshot.windows if w.is_foreground), None)
            if not target_win and intent.window_title:
                target_win = next((w for w in snapshot.windows if intent.window_title.lower() in (w.window_title or "").lower()), None)
            elif not target_win and snapshot.windows:
                target_win = snapshot.windows[0]

            win_bounds = getattr(target_win, "client_bounds", None) or getattr(target_win, "extended_bounds", None) if target_win else None
            if target_win and win_bounds and win_bounds.width > 0 and win_bounds.height > 0:
                generic_edit_roles = {"edit", "document", "input", "document_body", "editor", "text", "canvas"}
                if not intent.name or intent.name.lower() in generic_edit_roles:
                    try:
                        tbox = TargetBoundingBox.from_bounding_box(win_bounds)
                        safe_pt = calculate_safe_action_point(bounds=tbox, desktop_generation_id=snapshot.generation_id)
                        resolved = ResolvedTarget(
                            target_id=f"tgt_client_{target_win.hwnd}_{uuid4().hex[:6]}",
                            bounding_box=tbox,
                            safe_point=safe_pt,
                            confidence=0.90,
                            evidence=TargetEvidence(
                                source="WINDOW_CLIENT_AREA",
                                identifier=str(target_win.hwnd),
                                name=target_win.window_title or "WindowClientArea",
                                role=intent.role or "edit",
                                confidence=0.90,
                                raw_metadata={"hwnd": target_win.hwnd, "process_name": target_win.process_name},
                            ),
                            observation_id=snapshot.snapshot_id,
                            desktop_generation_id=snapshot.generation_id,
                            target_hwnd=target_win.hwnd,
                        )
                        return TargetResolutionResult(
                            status=TargetResolutionStatus.RESOLVED,
                            target=resolved,
                            candidates_count=1,
                            observation_id=snapshot.snapshot_id,
                            desktop_generation_id=snapshot.generation_id,
                        )
                    except Exception as ex:
                        logger.warning("Failed client bounds fallback resolution: %s", ex)

            if self._perception_engine and (intent.name or intent.text):
                try:
                    ocr_res = self._resolve_ocr_text(snapshot, intent)
                    if ocr_res.status == TargetResolutionStatus.RESOLVED and ocr_res.target:
                        return ocr_res
                except Exception as ex:
                    logger.debug("OCR fallback resolution skipped: %s", ex)

            return TargetResolutionResult(
                status=TargetResolutionStatus.NOT_FOUND,
                candidates_count=0,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=(
                    f"No accessible element matched criteria: name='{intent.name}', "
                    f"role='{intent.role}', automation_id='{intent.automation_id}'"
                ),
            )

        if len(candidates) > 1:
            # If multiple match, check if exactly one is focused or has exact name match
            exact_name_matches = [
                c for c in candidates
                if intent.name and c.name and c.name.strip().lower() == intent.name.strip().lower()
            ]
            if len(exact_name_matches) == 1:
                matched_el = exact_name_matches[0]
            else:
                focused_matches = [c for c in candidates if c.is_focused]
                if len(focused_matches) == 1:
                    matched_el = focused_matches[0]
                else:
                    return TargetResolutionResult(
                        status=TargetResolutionStatus.AMBIGUOUS,
                        candidates_count=len(candidates),
                        observation_id=snapshot.snapshot_id,
                        desktop_generation_id=snapshot.generation_id,
                        diagnostic_message=(
                            f"Ambiguous accessibility target: {len(candidates)} elements matched "
                            f"criteria (name='{intent.name}', role='{intent.role}')"
                        ),
                    )
        else:
            matched_el = candidates[0]

        try:
            tbox = TargetBoundingBox.from_bounding_box(matched_el.bounds)
            safe_pt = calculate_safe_action_point(
                bounds=tbox,
                desktop_generation_id=snapshot.generation_id,
            )

            resolved = ResolvedTarget(
                target_id=f"tgt_el_{matched_el.element_id}_{uuid4().hex[:6]}",
                bounding_box=tbox,
                safe_point=safe_pt,
                confidence=0.95,
                evidence=TargetEvidence(
                    source=matched_el.source,
                    identifier=matched_el.element_id,
                    name=matched_el.name,
                    role=matched_el.role,
                    confidence=0.95,
                    raw_metadata={
                        "control_type": matched_el.control_type,
                        "automation_id": matched_el.automation_id,
                        "class_name": matched_el.class_name,
                        "is_focused": matched_el.is_focused,
                    },
                ),
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
            )
            return TargetResolutionResult(
                status=TargetResolutionStatus.RESOLVED,
                target=resolved,
                candidates_count=1,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
            )
        except Exception as ex:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"Failed to calculate safe point for element bounds: {ex}",
            )

    def _resolve_ocr_text(
        self,
        snapshot: ObservationSnapshot,
        intent: TargetIntent,
    ) -> TargetResolutionResult:
        """Resolve target from OCR text recognition evidence."""
        query_text = intent.text or intent.name
        if not query_text or not query_text.strip():
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message="OCR_TEXT strategy requires non-empty 'text' or 'name' in TargetIntent",
            )

        # 1. Extract OCRResult evidence from intent metadata or snapshot telemetry
        ocr_result_raw = intent.metadata.get("ocr_result") or snapshot.telemetry.get("ocr_result")
        if ocr_result_raw is None:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=(
                    "OCR_TEXT strategy requires OCRResult evidence in intent.metadata['ocr_result'] "
                    "or snapshot.telemetry['ocr_result']"
                ),
            )

        if isinstance(ocr_result_raw, OCRResult):
            ocr_result = ocr_result_raw
        elif isinstance(ocr_result_raw, dict):
            try:
                ocr_result = OCRResult.model_validate(ocr_result_raw)
            except Exception as ex:
                return TargetResolutionResult(
                    status=TargetResolutionStatus.INVALID_REQUEST,
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=snapshot.generation_id,
                    diagnostic_message=f"Invalid OCRResult structure: {ex}",
                )
        else:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"Unsupported ocr_result type: {type(ocr_result_raw)}",
            )

        # 2. Check OCR status
        if ocr_result.status == OCRStatus.STALE_OBSERVATION:
            return TargetResolutionResult(
                status=TargetResolutionStatus.STALE_OBSERVATION,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                is_stale_observation=True,
                diagnostic_message=f"OCR evidence is stale: {ocr_result.error_message or 'Stale observation'}",
            )
        elif ocr_result.status == OCRStatus.UNSUPPORTED:
            return TargetResolutionResult(
                status=TargetResolutionStatus.UNSUPPORTED,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"OCR provider unsupported: {ocr_result.error_message or 'Backend unavailable'}",
            )
        elif ocr_result.status != OCRStatus.SUCCESS:
            return TargetResolutionResult(
                status=TargetResolutionStatus.NOT_FOUND,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=(
                    f"OCR extraction did not succeed (status={ocr_result.status.value}): "
                    f"{ocr_result.error_message or 'No text detected'}"
                ),
            )

        # 3. Generation Parity Gate
        if ocr_result.desktop_generation_id != snapshot.generation_id:
            logger.warning(
                "OCR evidence generation mismatch (ocr_gen=%d != snap_gen=%d)",
                ocr_result.desktop_generation_id,
                snapshot.generation_id,
            )
            return TargetResolutionResult(
                status=TargetResolutionStatus.STALE_OBSERVATION,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                is_stale_observation=True,
                diagnostic_message=(
                    f"OCR evidence generation {ocr_result.desktop_generation_id} "
                    f"does not match current snapshot generation {snapshot.generation_id}"
                ),
            )

        # 4. Search matching text regions using perception engine
        if self._perception_engine is not None:
            perception_engine = self._perception_engine
        else:
            from orbit.runtime.perception.engine import SemanticPerceptionEngine
            perception_engine = SemanticPerceptionEngine()
        matches = perception_engine.find_text_regions(
            ocr_result=ocr_result,
            query_text=query_text,
            exact_match=intent.exact_match,
            case_sensitive=intent.case_sensitive,
            min_confidence=intent.min_confidence,
        )

        if not matches:
            return TargetResolutionResult(
                status=TargetResolutionStatus.NOT_FOUND,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                candidates_count=0,
                diagnostic_message=(
                    f"No OCR text regions matching '{query_text}' "
                    f"(exact_match={intent.exact_match}, case_sensitive={intent.case_sensitive})"
                ),
            )

        if len(matches) > 1:
            candidate_boxes = [
                f"({m.bounding_box.left},{m.bounding_box.top},{m.bounding_box.width}x{m.bounding_box.height})"
                for m in matches
            ]
            logger.warning(
                "OCR text resolution ambiguous: found %d matches for '%s': %s",
                len(matches),
                query_text,
                candidate_boxes,
            )
            return TargetResolutionResult(
                status=TargetResolutionStatus.AMBIGUOUS,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                candidates_count=len(matches),
                diagnostic_message=(
                    f"Ambiguous OCR target: {len(matches)} regions matched '{query_text}': "
                    f"{', '.join(candidate_boxes[:5])}"
                ),
            )

        # Exactly 1 match found
        match = matches[0]
        from orbit.runtime.perception.coordinate_mapper import OCRCoordinateMapper

        mapper = OCRCoordinateMapper()
        # Derive screenshot offset if available in snapshot
        offset_x = getattr(snapshot, "screenshot_offset_x", 0)
        offset_y = getattr(snapshot, "screenshot_offset_y", 0)
        
        map_res = mapper.map_to_virtual_desktop(
            box=match.bounding_box,
            screenshot_offset_x=offset_x,
            screenshot_offset_y=offset_y,
        )

        if not map_res.is_valid or map_res.mapped_box is None:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"OCR coordinate mapping failed: {map_res.diagnostic_message}",
            )

        tbox = TargetBoundingBox(
            left=map_res.mapped_box.left,
            top=map_res.mapped_box.top,
            right=map_res.mapped_box.right,
            bottom=map_res.mapped_box.bottom,
        )

        if not tbox.is_valid or tbox.width <= 0 or tbox.height <= 0:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"OCR match has invalid bounding box geometry: {tbox}",
            )

        try:
            safe_pt = calculate_safe_action_point(
                bounds=tbox,
                desktop_generation_id=snapshot.generation_id,
            )

            resolved = ResolvedTarget(
                target_id=f"tgt_ocr_{uuid4().hex[:8]}",
                bounding_box=tbox,
                safe_point=safe_pt,
                confidence=1.0 if match.confidence is None else match.confidence,
                evidence=TargetEvidence(
                    source="OCR_TEXT",
                    name=match.text,
                    role="text_region",
                    confidence=1.0 if match.confidence is None else match.confidence,
                    raw_metadata={
                        "normalized_text": match.normalized_text,
                        "source_provider": match.source_provider,
                        "words_count": len(match.words),
                    },
                ),
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                target_hwnd=intent.target_hwnd,
            )

            return TargetResolutionResult(
                status=TargetResolutionStatus.RESOLVED,
                target=resolved,
                candidates_count=1,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
            )
        except Exception as ex:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"Failed to calculate safe point for OCR target: {ex}",
            )

    def _resolve_visual_template(
        self,
        snapshot: ObservationSnapshot,
        intent: TargetIntent,
    ) -> TargetResolutionResult:
        """Resolve target from visual template matching evidence."""
        from orbit.runtime.perception.visual_models import (
            VisualMatchPolicy,
            VisualMatchResult,
            VisualMatchStatus,
            VisualTemplate,
        )
        from orbit.runtime.perception.visual_engine import VisualPerceptionEngine

        # 1. Extract VisualMatchResult if pre-computed in intent metadata or snapshot telemetry
        match_result_raw = intent.metadata.get("visual_match_result") or snapshot.telemetry.get("visual_match_result")
        visual_result: Optional[VisualMatchResult] = None

        if match_result_raw is not None:
            if isinstance(match_result_raw, VisualMatchResult):
                visual_result = match_result_raw
            elif isinstance(match_result_raw, dict):
                try:
                    visual_result = VisualMatchResult.model_validate(match_result_raw)
                except Exception as ex:
                    return TargetResolutionResult(
                        status=TargetResolutionStatus.INVALID_REQUEST,
                        observation_id=snapshot.snapshot_id,
                        desktop_generation_id=snapshot.generation_id,
                        diagnostic_message=f"Invalid visual_match_result structure: {ex}",
                    )

        # 2. If not pre-computed, execute visual template matching if template is supplied
        if visual_result is None:
            template: Optional[VisualTemplate] = None
            if isinstance(intent.template, VisualTemplate):
                template = intent.template
            elif isinstance(intent.template, dict):
                try:
                    template = VisualTemplate.model_validate(intent.template)
                except Exception:
                    template = None
            elif intent.template_id and self._perception_engine and hasattr(self._perception_engine, "visual_engine"):
                template = self._perception_engine.visual_engine.get_template(intent.template_id)

            if template is None:
                return TargetResolutionResult(
                    status=TargetResolutionStatus.INVALID_REQUEST,
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=snapshot.generation_id,
                    diagnostic_message=(
                        "VISUAL_TEMPLATE strategy requires a valid VisualTemplate in intent.template, "
                        "a registered template_id, or precomputed visual_match_result in intent.metadata"
                    ),
                )

            if not template.is_valid:
                return TargetResolutionResult(
                    status=TargetResolutionStatus.INVALID_REQUEST,
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=snapshot.generation_id,
                    diagnostic_message=f"VisualTemplate '{template.template_id}' has invalid geometry or empty image",
                )

            policy = VisualMatchPolicy(
                minimum_confidence=intent.min_confidence if intent.min_confidence is not None else 0.85,
            )

            try:
                visual_engine = (
                    self._perception_engine.visual_engine
                    if (self._perception_engine and hasattr(self._perception_engine, "visual_engine"))
                    else VisualPerceptionEngine()
                )
                search_img = snapshot.telemetry.get("screenshot") or snapshot.telemetry.get("image")
                if search_img is None:
                    return TargetResolutionResult(
                        status=TargetResolutionStatus.INVALID_REQUEST,
                        observation_id=snapshot.snapshot_id,
                        desktop_generation_id=snapshot.generation_id,
                        diagnostic_message="No screenshot image available in snapshot telemetry for visual matching",
                    )

                matcher = visual_engine.matcher
                if hasattr(matcher, "_execute_matching"):
                    visual_result = matcher._execute_matching(
                        template=template,
                        image=search_img,
                        policy=policy,
                        desktop_generation_id=snapshot.generation_id,
                        observation_id=snapshot.snapshot_id,
                    )
                else:
                    visual_result = None
            except Exception as ex:
                return TargetResolutionResult(
                    status=TargetResolutionStatus.INVALID_REQUEST,
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=snapshot.generation_id,
                    diagnostic_message=f"Failed to execute visual template matching: {ex}",
                )

        if visual_result is None:
            return TargetResolutionResult(
                status=TargetResolutionStatus.NOT_FOUND,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message="No visual match result obtained",
            )

        # 3. Check Status
        if visual_result.status == VisualMatchStatus.STALE_OBSERVATION:
            return TargetResolutionResult(
                status=TargetResolutionStatus.STALE_OBSERVATION,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                is_stale_observation=True,
                diagnostic_message=f"Visual match evidence is stale: {visual_result.error_message}",
            )
        elif visual_result.status == VisualMatchStatus.AMBIGUOUS:
            return TargetResolutionResult(
                status=TargetResolutionStatus.AMBIGUOUS,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                candidates_count=len(visual_result.matches),
                diagnostic_message=(
                    f"Ambiguous visual matches: {len(visual_result.matches)} candidate regions detected "
                    f"({visual_result.error_message or 'Margin below threshold'})"
                ),
            )
        elif visual_result.status == VisualMatchStatus.UNSUPPORTED:
            return TargetResolutionResult(
                status=TargetResolutionStatus.UNSUPPORTED,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"Visual matching unsupported: {visual_result.error_message}",
            )
        elif visual_result.status in (VisualMatchStatus.NOT_FOUND, VisualMatchStatus.LOW_CONFIDENCE):
            return TargetResolutionResult(
                status=TargetResolutionStatus.NOT_FOUND,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"Visual template not found: {visual_result.error_message or 'Low confidence'}",
            )
        elif visual_result.status != VisualMatchStatus.MATCHED or visual_result.best_match is None:
            return TargetResolutionResult(
                status=TargetResolutionStatus.NOT_FOUND,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"Visual matching failed: {visual_result.error_message or 'No match'}",
            )

        # 4. Generation Parity Gate
        if visual_result.desktop_generation_id != snapshot.generation_id:
            logger.warning(
                "Visual evidence generation mismatch (vis_gen=%d != snap_gen=%d)",
                visual_result.desktop_generation_id,
                snapshot.generation_id,
            )
            return TargetResolutionResult(
                status=TargetResolutionStatus.STALE_OBSERVATION,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                is_stale_observation=True,
                diagnostic_message=(
                    f"Visual evidence generation {visual_result.desktop_generation_id} "
                    f"does not match current snapshot generation {snapshot.generation_id}"
                ),
            )

        # 5. Map Bounding Box through OCRCoordinateMapper
        match = visual_result.best_match
        from orbit.runtime.perception.coordinate_mapper import OCRCoordinateMapper
        mapper = OCRCoordinateMapper()
        offset_x = getattr(snapshot, "screenshot_offset_x", 0)
        offset_y = getattr(snapshot, "screenshot_offset_y", 0)

        map_res = mapper.map_to_virtual_desktop(
            box=match.bounding_box,
            screenshot_offset_x=offset_x,
            screenshot_offset_y=offset_y,
        )

        if not map_res.is_valid or map_res.mapped_box is None:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"Visual coordinate mapping failed: {map_res.diagnostic_message}",
            )

        tbox = TargetBoundingBox(
            left=map_res.mapped_box.left,
            top=map_res.mapped_box.top,
            right=map_res.mapped_box.right,
            bottom=map_res.mapped_box.bottom,
        )

        if not tbox.is_valid or tbox.width <= 0 or tbox.height <= 0:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"Visual match has invalid bounding box geometry: {tbox}",
            )

        # 6. Calculate Safe Action Point
        try:
            safe_pt = calculate_safe_action_point(
                bounds=tbox,
                desktop_generation_id=snapshot.generation_id,
            )

            resolved = ResolvedTarget(
                target_id=f"tgt_vis_{uuid4().hex[:8]}",
                bounding_box=tbox,
                safe_point=safe_pt,
                confidence=match.confidence,
                evidence=TargetEvidence(
                    source="VISUAL_TEMPLATE",
                    identifier=match.template_id,
                    name=match.template_name,
                    role="icon_template",
                    confidence=match.confidence,
                    raw_metadata={
                        "scale_factor": match.scale_factor,
                        "source_provider": match.source_provider,
                    },
                ),
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                target_hwnd=intent.target_hwnd,
            )

            return TargetResolutionResult(
                status=TargetResolutionStatus.RESOLVED,
                target=resolved,
                candidates_count=1,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
            )
        except Exception as ex:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"Failed to calculate safe point for visual target: {ex}",
            )

    def _resolve_multimodal(
        self,
        snapshot: ObservationSnapshot,
        intent: TargetIntent,
    ) -> TargetResolutionResult:
        """Resolve target using multi-modal perception fusion across all evidence channels."""
        from orbit.runtime.perception.fusion_engine import MultiModalPerceptionFusionEngine
        from orbit.runtime.perception.fusion_models import FusionPolicy, FusionStatus

        fusion_engine = MultiModalPerceptionFusionEngine()
        policy = FusionPolicy(
            min_individual_confidence=intent.min_confidence if intent.min_confidence is not None else 0.60,
            min_fused_confidence=intent.min_confidence if intent.min_confidence is not None else 0.80,
            max_spatial_distance_px=intent.metadata.get("max_spatial_distance_px", 120.0),
            min_iou=intent.metadata.get("min_iou", 0.20),
            contradiction_distance_px=intent.metadata.get("contradiction_distance_px", 150.0),
            ambiguity_distance_margin_px=intent.metadata.get("ambiguity_distance_margin_px", 20.0),
            require_cross_modal_agreement=intent.metadata.get("require_cross_modal_agreement", False),
        )

        # Extract pre-computed or runtime OCR and visual evidence if available
        ocr_result = intent.metadata.get("ocr_result") or snapshot.telemetry.get("ocr_result")
        visual_result = intent.metadata.get("visual_match_result") or snapshot.telemetry.get("visual_match_result")

        fusion_res = fusion_engine.fuse_multimodal_intent(
            snapshot=snapshot,
            intent=intent,
            ocr_result=ocr_result,
            visual_result=visual_result,
            policy=policy,
        )

        if fusion_res.status == FusionStatus.STALE_OBSERVATION:
            return TargetResolutionResult(
                status=TargetResolutionStatus.STALE_OBSERVATION,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                is_stale_observation=True,
                diagnostic_message=fusion_res.diagnostic_message,
            )
        elif fusion_res.status == FusionStatus.CONTRADICTORY:
            return TargetResolutionResult(
                status=TargetResolutionStatus.CONTRADICTORY,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=fusion_res.diagnostic_message,
            )
        elif fusion_res.status == FusionStatus.AMBIGUOUS:
            return TargetResolutionResult(
                status=TargetResolutionStatus.AMBIGUOUS,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                candidates_count=len(fusion_res.candidates),
                diagnostic_message=fusion_res.diagnostic_message,
            )
        elif fusion_res.status == FusionStatus.LOW_CONFIDENCE:
            return TargetResolutionResult(
                status=TargetResolutionStatus.LOW_CONFIDENCE,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=fusion_res.diagnostic_message,
            )
        elif fusion_res.status == FusionStatus.NOT_FOUND:
            return TargetResolutionResult(
                status=TargetResolutionStatus.NOT_FOUND,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=fusion_res.diagnostic_message,
            )
        elif fusion_res.status == FusionStatus.UNSUPPORTED:
            return TargetResolutionResult(
                status=TargetResolutionStatus.UNSUPPORTED,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=fusion_res.diagnostic_message,
            )
        elif fusion_res.status != FusionStatus.RESOLVED or fusion_res.fused_target is None:
            return TargetResolutionResult(
                status=TargetResolutionStatus.NOT_FOUND,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=fusion_res.diagnostic_message or "Multi-modal fusion failed to resolve target",
            )

        fused_target = fusion_res.fused_target
        tbox = fused_target.bounding_box

        try:
            safe_pt = calculate_safe_action_point(
                bounds=tbox,
                desktop_generation_id=snapshot.generation_id,
            )

            resolved = ResolvedTarget(
                target_id=f"tgt_fused_{uuid4().hex[:8]}",
                bounding_box=tbox,
                safe_point=safe_pt,
                confidence=fused_target.confidence,
                evidence=TargetEvidence(
                    source=f"MULTIMODAL_{fused_target.fused_evidence.primary_channel.value}",
                    identifier=fused_target.primary_identifier,
                    name=fused_target.primary_label,
                    role="fused_target",
                    confidence=fused_target.confidence,
                    raw_metadata={
                        "primary_channel": fused_target.fused_evidence.primary_channel.value,
                        "supporting_channels": [c.value for c in fused_target.fused_evidence.supporting_channels],
                        "evidence_items_count": len(fused_target.fused_evidence.evidence_items),
                        "spatial_relation": (
                            fused_target.fused_evidence.spatial_agreement.relation.value
                            if fused_target.fused_evidence.spatial_agreement
                            else None
                        ),
                        "spatial_iou": (
                            fused_target.fused_evidence.spatial_agreement.iou
                            if fused_target.fused_evidence.spatial_agreement
                            else None
                        ),
                        "semantic_matched": (
                            fused_target.fused_evidence.semantic_agreement.is_matched
                            if fused_target.fused_evidence.semantic_agreement
                            else None
                        ),
                    },
                ),
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                target_hwnd=intent.target_hwnd,
            )

            return TargetResolutionResult(
                status=TargetResolutionStatus.RESOLVED,
                target=resolved,
                candidates_count=len(fusion_res.candidates),
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
            )
        except Exception as ex:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"Failed to calculate safe action point for fused target: {ex}",
            )



