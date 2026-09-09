"""Evidence-driven target locator resolving UI intent against ObservationSnapshot."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import sys
import time
from typing import TYPE_CHECKING, List, Optional, Protocol, Tuple, runtime_checkable
from uuid import uuid4

from orbit.adapters.observation.snapshot import (
    BoundingBox,
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

if sys.platform == "win32":
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL



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
        arg1: Any,
        arg2: Any = None,
        *,
        snapshot: Optional[Any] = None,
        intent: Optional[Any] = None,
        observation: Optional[Any] = None,
    ) -> TargetResolutionResult:
        """Resolve TargetIntent/SemanticTarget against ObservationSnapshot/DesktopObservation using evidence-based matching."""
        actual_snapshot: Optional[ObservationSnapshot] = None
        actual_intent: Optional[TargetIntent] = None

        # Disambiguate arguments
        candidates = [arg1, arg2, snapshot, observation, intent]
        for c in candidates:
            if c is None:
                continue
            if isinstance(c, ObservationSnapshot):
                actual_snapshot = c
            elif hasattr(c, "uia_elements") or hasattr(c, "visible_windows"):
                # Canonical DesktopObservation
                actual_snapshot = ObservationSnapshot.from_desktop_observation(c)
            elif hasattr(c, "desktop_observation") and c.desktop_observation is not None:
                # CurrentStateObservation with attached DesktopObservation
                actual_snapshot = ObservationSnapshot.from_desktop_observation(c.desktop_observation)
            elif hasattr(c, "raw_evidence") and hasattr(c, "visible_windows"):
                # CurrentStateObservation without attached DesktopObservation
                from orbit.models.common import BoundingBox
                windows = [
                    ObservedWindow(
                        hwnd=w.get("hwnd", 0),
                        process_id=w.get("process_id", 0) or 0,
                        process_name=w.get("process_name", "") or "",
                        window_title=w.get("title", "") or "",
                        extended_bounds=BoundingBox(left=0, top=0, width=1920, height=1080),
                        is_foreground=w.get("is_foreground", False),
                        is_visible=True,
                    )
                    for w in c.visible_windows
                ]
                actual_snapshot = ObservationSnapshot(
                    snapshot_id=getattr(c, "observation_id", f"obs_{uuid4().hex[:8]}"),
                    generation_id=1,
                    timestamp_ns=int(time.time() * 1e9),
                    desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
                    windows=windows,
                )
            elif isinstance(c, TargetIntent):
                actual_intent = c
            elif hasattr(c, "name") or hasattr(c, "role"):
                # SemanticTarget or similar model
                strat = TargetStrategy.ACCESSIBILITY_ELEMENT
                c_role = getattr(c, "role", "") or ""
                if c_role.lower() in ("window", "app", "application") or "window" in str(getattr(c, "context", "")).lower():
                    strat = TargetStrategy.WINDOW_TITLE
                actual_intent = TargetIntent(
                    name=getattr(c, "name", None),
                    role=getattr(c, "role", None),
                    window_title=getattr(c, "name", None) if strat == TargetStrategy.WINDOW_TITLE else None,
                    strategy=strat,
                )

        if actual_intent is None:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                diagnostic_message="No valid TargetIntent or SemanticTarget provided to TargetLocator",
            )

        if actual_snapshot is None:
            # Create synthetic snapshot fallback
            from orbit.models.common import BoundingBox
            actual_snapshot = ObservationSnapshot(
                snapshot_id=f"snap_{uuid4().hex[:8]}",
                generation_id=1,
                timestamp_ns=int(time.time() * 1e9),
                desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
            )

        # 1. Stale Observation Gate
        if actual_snapshot.is_stale or actual_snapshot.freshness_state == FreshnessState.STALE:
            reason = actual_snapshot.invalidation_reason or "Observation snapshot TTL expired or generation invalid"
            logger.warning("Target localization rejected: snapshot %s is stale (%s)", actual_snapshot.snapshot_id, reason)
            return TargetResolutionResult(
                status=TargetResolutionStatus.STALE_OBSERVATION,
                observation_id=actual_snapshot.snapshot_id,
                desktop_generation_id=actual_snapshot.generation_id,
                is_stale_observation=True,
                diagnostic_message=f"Target localization aborted: Observation snapshot is stale ({reason})",
            )

        # 2. Dispatch based on strategy
        if actual_intent.strategy == TargetStrategy.COORDINATE_REGION:
            return self._resolve_coordinate_region(actual_snapshot, actual_intent)
        elif actual_intent.strategy == TargetStrategy.WINDOW_TITLE:
            return self._resolve_window(actual_snapshot, actual_intent)
        elif actual_intent.strategy == TargetStrategy.ACCESSIBILITY_ELEMENT:
            return self._resolve_accessibility_element(actual_snapshot, actual_intent)
        elif actual_intent.strategy == TargetStrategy.OCR_TEXT:
            return self._resolve_ocr_text(actual_snapshot, actual_intent)
        elif actual_intent.strategy in (
            TargetStrategy.VISUAL_TEMPLATE,
            TargetStrategy.ICON_TEMPLATE,
            TargetStrategy.IMAGE_REGION,
            TargetStrategy.VISUAL_SEMANTIC,
        ):
            return self._resolve_visual_template(actual_snapshot, actual_intent)
        elif actual_intent.strategy in (TargetStrategy.MULTIMODAL, TargetStrategy.FUSED_MULTIMODAL):
            return self._resolve_multimodal(actual_snapshot, actual_intent)
        else:
            return TargetResolutionResult(
                status=TargetResolutionStatus.UNSUPPORTED,
                observation_id=actual_snapshot.snapshot_id,
                desktop_generation_id=actual_snapshot.generation_id,
                diagnostic_message=f"Unsupported target resolution strategy: {actual_intent.strategy}",
            )

    resolve = locate_target


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

    @staticmethod
    def _get_proc_name_by_hwnd(hwnd: int) -> Tuple[int, str]:
        """Extract process ID and image name for an HWND on Win32."""
        if sys.platform != "win32" or not hwnd:
            return (0, "")
        pid = wintypes.DWORD(0)
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return (0, "")
        h_proc = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
        if not h_proc:
            return (pid.value, "")
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        name = ""
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
            name = os.path.basename(buf.value)
        ctypes.windll.kernel32.CloseHandle(h_proc)
        return (pid.value, name)

    @staticmethod
    def _force_foreground_window(hwnd: int) -> bool:
        """Robustly bring window to foreground using Win32 thread input attachment and Alt key simulation."""
        if sys.platform != "win32" or not hwnd:
            return False
        try:
            u32 = ctypes.windll.user32
            k32 = ctypes.windll.kernel32
            if not u32.IsWindow(hwnd):
                return False

            root_hwnd = u32.GetAncestor(hwnd, 2)  # GA_ROOT = 2
            if not root_hwnd or not u32.IsWindow(root_hwnd):
                root_hwnd = hwnd

            if u32.IsIconic(root_hwnd):
                u32.ShowWindow(root_hwnd, 9)  # SW_RESTORE
            else:
                u32.ShowWindow(root_hwnd, 5)  # SW_SHOW

            cur_fg = u32.GetForegroundWindow()
            if cur_fg == root_hwnd or cur_fg == hwnd:
                return True

            cur_tid = k32.GetCurrentThreadId()
            fg_tid = u32.GetWindowThreadProcessId(cur_fg, None) if cur_fg else 0
            target_tid = u32.GetWindowThreadProcessId(root_hwnd, None)

            if fg_tid and fg_tid != cur_tid:
                u32.AttachThreadInput(cur_tid, fg_tid, True)
            if target_tid and target_tid != cur_tid:
                u32.AttachThreadInput(cur_tid, target_tid, True)

            # Bypass Windows SetForegroundWindow lock using Alt key simulation
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            u32.keybd_event(VK_MENU, 0, 0, 0)
            u32.SetForegroundWindow(root_hwnd)
            u32.BringWindowToTop(root_hwnd)
            u32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            if hwnd != root_hwnd and u32.IsWindow(hwnd):
                u32.SetFocus(hwnd)
            else:
                u32.SetFocus(root_hwnd)

            if fg_tid and fg_tid != cur_tid:
                u32.AttachThreadInput(cur_tid, fg_tid, False)
            if target_tid and target_tid != cur_tid:
                u32.AttachThreadInput(cur_tid, target_tid, False)

            time.sleep(0.05)
            final_fg = u32.GetForegroundWindow()
            return final_fg == root_hwnd or final_fg == hwnd or (u32.GetAncestor(final_fg, 2) == root_hwnd)
        except Exception:
            return False

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
        tq_clean = (title_query or "").strip().lower()
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
            if tq_clean:
                w_title = (win.window_title or "").lower()
                w_proc = (win.process_name or "").lower()
                proc_match = bool(w_proc and (tq_clean in w_proc or w_proc.startswith(tq_clean) or (tq_clean in ("calculator", "calc") and "calc" in w_proc)))
                title_exact = bool(w_title and (w_title == tq_clean or w_title.endswith(f" - {tq_clean}") or w_title.startswith(f"{tq_clean} - ") or w_title.startswith(f"{tq_clean} ")))
                title_words = [word.strip(' -–_()[],.') for word in w_title.split()]
                word_match = bool(tq_clean in title_words or (tq_clean in ("calculator", "calc") and ("calc" in title_words or "calculator" in title_words)))
                title_substr = bool(w_title and (tq_clean in w_title or (len(w_title) >= 4 and w_title in tq_clean)))

                # Exclude IDE/editor tabs matching utility app names unless process matches
                is_ide = any(ide in w_proc for ide in ("antigravity", "code.exe", "devenv.exe", "pycharm", "idea", "studio"))
                if is_ide and tq_clean in ("notepad", "calculator", "calc", "paint", "mspaint", "cmd", "terminal") and not proc_match:
                    continue

                if tq_clean in ("browser", "web browser", "internet"):
                    known_browsers = ("chrome", "msedge", "edge", "brave", "firefox", "opera")
                    if any(b in w_proc or b in w_title for b in known_browsers):
                        proc_match = True

                if not (proc_match or title_exact or word_match or title_substr):
                    continue

            candidates.append(win)

        # If candidate windows are empty, target is not found on live desktop (no process launch bypass)

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
            def score_win(w: ObservedWindow) -> tuple:
                w_title = (w.window_title or "").lower()
                w_proc = (w.process_name or "").lower()
                proc_exact = 1 if (tq_clean and (w_proc == f"{tq_clean}.exe" or w_proc.startswith(tq_clean))) else 0
                title_exact = 1 if (tq_clean and (w_title == tq_clean or w_title.endswith(f" - {tq_clean}") or w_title.startswith(f"{tq_clean} - ") or w_title.startswith(f"{tq_clean} "))) else 0
                has_title = 1 if bool(w.window_title and w.window_title.strip()) else 0
                title_matches = 1 if (tq_clean and tq_clean in w_title) else 0
                is_fg = 1 if w.is_foreground else 0
                area = (w.extended_bounds.width or 0) * (w.extended_bounds.height or 0) if w.extended_bounds else 0
                z_rank = getattr(w, "z_order_rank", 9999)
                return (proc_exact, title_exact, has_title, title_matches, is_fg, area, -z_rank)

            matched_win = max(candidates, key=score_win)
        else:
            matched_win = candidates[0]

        if sys.platform == "win32" and matched_win.hwnd:
            self._force_foreground_window(matched_win.hwnd)

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

    @staticmethod
    def _find_target_window(snapshot: ObservationSnapshot, intent: TargetIntent) -> Optional[ObservedWindow]:
        """Resolve the active or intended target window from snapshot and intent."""
        # 1. Match explicit HWND
        if intent.target_hwnd:
            for w in snapshot.windows:
                if w.hwnd == intent.target_hwnd:
                    return w
            if snapshot.foreground_window and snapshot.foreground_window.hwnd == intent.target_hwnd:
                return snapshot.foreground_window

        # 2. Match Window Title or Process Name
        tq = (intent.window_title or "").strip().lower()
        pq = (intent.process_name or "").strip().lower()
        if tq or pq:
            scored_candidates: List[Tuple[float, ObservedWindow]] = []
            all_wins = list(snapshot.windows)
            if snapshot.foreground_window and snapshot.foreground_window not in all_wins:
                all_wins.append(snapshot.foreground_window)

            for w in all_wins:
                if not w.is_visible:
                    continue
                w_title = (w.window_title or "").lower()
                w_proc = (w.process_name or "").lower()
                
                is_ide = any(ide in w_proc for ide in ("antigravity", "code.exe", "devenv.exe", "pycharm", "idea", "studio"))
                if is_ide and tq in ("notepad", "calculator", "calc", "paint", "mspaint", "cmd", "terminal") and not (tq in w_proc):
                    continue

                score = 0.0
                if pq and (pq == w_proc or pq in w_proc):
                    score += 100.0
                if tq:
                    if w_proc == f"{tq}.exe" or w_proc.startswith(tq):
                        score += 100.0
                    elif tq in w_proc or (tq in ("calc", "calculator") and "calc" in w_proc):
                        score += 80.0
                    
                    if w_title == tq:
                        score += 90.0
                    elif w_title.endswith(f" - {tq}") or w_title.startswith(f"{tq} - ") or w_title.startswith(f"{tq} "):
                        score += 85.0
                    elif tq in w_title.split() or (tq in ("calc", "calculator") and "calculator" in w_title.split()):
                        score += 50.0
                    elif tq in w_title or (tq in ("calc", "calculator") and "calculator" in w_title):
                        score += 10.0

                if score > 0:
                    if w.is_foreground:
                        score += 5.0
                    scored_candidates.append((score, w))

            if scored_candidates:
                scored_candidates.sort(key=lambda item: item[0], reverse=True)
                return scored_candidates[0][1]

            # Check live desktop windows if window just launched
            if sys.platform == "win32":
                try:
                    from window_tracker import WindowTracker
                    from orbit.adapters.observation.mapper import map_rect_to_bounding_box
                    wt = WindowTracker()
                    live_candidates: List[Tuple[float, ObservedWindow]] = []
                    for w_obs in wt.enumerate_visible_windows():
                        w_title = (w_obs.window_title or "").lower()
                        w_proc = (w_obs.process_name or "").lower()
                        
                        is_ide = any(ide in w_proc for ide in ("antigravity", "code.exe", "devenv.exe", "pycharm", "idea", "studio"))
                        if is_ide and tq in ("notepad", "calculator", "calc", "paint", "mspaint", "cmd", "terminal") and not (tq in w_proc):
                            continue

                        score = 0.0
                        if pq and (pq in w_proc or pq in w_title):
                            score += 100.0
                        if tq:
                            if w_proc == f"{tq}.exe" or w_proc.startswith(tq):
                                score += 100.0
                            elif tq in w_proc or (tq in ("calc", "calculator") and "calc" in w_proc):
                                score += 80.0
                            if w_title == tq:
                                score += 90.0
                            elif w_title.endswith(f" - {tq}") or w_title.startswith(f"{tq} - ") or w_title.startswith(f"{tq} "):
                                score += 85.0
                            elif tq in w_title.split() or (tq in ("calc", "calculator") and "calculator" in w_title.split()):
                                score += 50.0
                            elif tq in w_title or (tq in ("calc", "calculator") and "calculator" in w_title):
                                score += 10.0

                        if score > 0:
                            live_candidates.append((
                                score,
                                ObservedWindow(
                                    hwnd=w_obs.hwnd,
                                    process_id=w_obs.process_id or 0,
                                    window_title=w_obs.window_title or "",
                                    process_name=w_obs.process_name or "",
                                    is_visible=True,
                                    is_foreground=(ctypes.windll.user32.GetForegroundWindow() == w_obs.hwnd),
                                    extended_bounds=map_rect_to_bounding_box(w_obs.extended_bounds),
                                )
                            ))
                    if live_candidates:
                        live_candidates.sort(key=lambda item: item[0], reverse=True)
                        return live_candidates[0][1]
                except Exception:
                    pass

            return None

        # 3. Use focused / foreground window if no explicit title requested
        if snapshot.foreground_window and snapshot.foreground_window.is_visible:
            return snapshot.foreground_window

        for w in snapshot.windows:
            if w.is_visible and w.is_foreground:
                return w

        # 4. First visible window if any
        for w in snapshot.windows:
            if w.is_visible and w.extended_bounds and w.extended_bounds.width > 50:
                return w

        return None

    @staticmethod
    def _match_semantic_target(
        query: str,
        name: Optional[str],
        automation_id: Optional[str] = None,
        role: Optional[str] = None,
        control_type: Optional[str] = None,
        class_name: Optional[str] = None,
    ) -> Tuple[bool, float]:
        """Match element metadata against semantic query string, returning (is_match, score)."""
        if not query:
            return (False, 0.0)

        q = query.strip().lower()
        n = (name or "").strip().lower()
        aid = (automation_id or "").strip().lower()

        # Semantic Digit & Operator Mappings
        digit_map = {
            "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
            "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
        }
        reverse_digit_map = {v: k for k, v in digit_map.items()}
        operator_map = {
            "+": ["plus", "add", "addition", "plusbutton", "addbutton"],
            "-": ["minus", "subtract", "subtraction", "minusbutton", "subtractbutton"],
            "*": ["multiply", "multiplication", "times", "multiplybutton", "multiply by"],
            "x": ["multiply", "multiplication", "times", "multiplybutton", "multiply by"],
            "×": ["multiply", "multiplication", "times", "multiplybutton", "multiply by"],
            "/": ["divide", "division", "dividebutton", "divide by"],
            "÷": ["divide", "division", "dividebutton", "divide by"],
            "=": ["equal", "equals", "equalbutton", "equalsbutton"],
            "c": ["clear", "clearbutton"],
            "ce": ["clear entry", "clear entry button"],
        }

        # 1. Exact Name match
        if n and q == n:
            return (True, 1.0)

        # 2. Digit alias name match (e.g. "7" <-> "Seven" or "Seven" <-> "7")
        if q in digit_map and n == digit_map[q]:
            return (True, 0.98)
        if q in reverse_digit_map and n == reverse_digit_map[q]:
            return (True, 0.98)

        # 3. Operator alias name match (e.g. "+" <-> "plus")
        if q in operator_map and any(n == op for op in operator_map[q]):
            return (True, 0.98)

        # 4. Exact AutomationId match
        if aid and q == aid:
            return (True, 0.97)

        # 5. AutomationId semantic digit patterns (e.g. "num7Button", "sevenButton", "button7", "NumberPad7")
        if q in digit_map:
            word_d = digit_map[q]
            patterns = [
                f"num{q}button", f"num{word_d}button", f"{word_d}button", f"button{q}",
                f"numberpad{q}", f"numberpad_{q}", f"button_{q}", f"num{q}", f"digit{q}",
            ]
            if aid and any(p in aid for p in patterns):
                return (True, 0.96)
            if n and any(p in n for p in patterns):
                return (True, 0.96)

        # 6. AutomationId operator patterns (e.g. "plusButton", "equalButton")
        if q in operator_map:
            for op in operator_map[q]:
                if aid and (f"{op}button" in aid or f"btn{op}" in aid or op in aid):
                    return (True, 0.95)

        # 7. Exact AutomationId containing target as full word/token (e.g. "SaveButton", "btnSave", "SettingsButton")
        if aid:
            tokens = [aid, aid.replace("_", ""), aid.replace("-", "")]
            if any(t.endswith(f"{q}button") or t.startswith(f"btn{q}") or t == f"{q}button" for t in tokens):
                return (True, 0.94)

        # 8. Normalized Name Substring match (e.g. "Save", "File", "Settings", "OK")
        if n and q in n:
            # Full word or clean substring
            score = 0.92 if len(n.split()) == 1 else 0.88
            return (True, score)

        # 9. AutomationId contains query substring
        if aid and q in aid:
            return (True, 0.80)

        return (False, 0.0)

    def _resolve_accessibility_element(
        self,
        snapshot: ObservationSnapshot,
        intent: TargetIntent,
    ) -> TargetResolutionResult:
        """Resolve target from UI accessibility elements (MSAA, UI Automation, Win32)."""
        target_win = self._find_target_window(snapshot, intent)
        target_hwnd = target_win.hwnd if target_win else intent.target_hwnd

        if sys.platform == "win32" and target_hwnd:
            self._force_foreground_window(target_hwnd)

        # Extract target window bounding box for spatial containment filtering
        win_box = None
        if target_win and target_win.extended_bounds:
            wb = target_win.extended_bounds
            if wb.width > 0 and wb.height > 0:
                win_box = (wb.left, wb.top, wb.left + wb.width, wb.top + wb.height)

        scored_candidates: List[Tuple[float, ObservedElement]] = []

        query = intent.name or intent.text or intent.automation_id
        for el in snapshot.detected_elements:
            # Skip disabled or offscreen elements
            if el.is_offscreen or not el.is_enabled:
                continue

            # Validate positive dimensions
            if el.bounds.width <= 0 or el.bounds.height <= 0:
                continue

            # Spatial validation: Element must lie within window bounds if window is identified
            el_cx = el.bounds.left + (el.bounds.width / 2.0)
            el_cy = el.bounds.top + (el.bounds.height / 2.0)

            if win_box:
                w_left, w_top, w_right, w_bottom = win_box
                # Allow a small 30px tolerance margin for non-client window borders/shadows
                if not (w_left - 30 <= el_cx <= w_right + 30 and w_top - 30 <= el_cy <= w_bottom + 30):
                    # Candidate is outside the target window bounds
                    continue

            # Check role / control type if specified
            role_boost = 0.0
            if intent.role:
                req_role = intent.role.lower()
                role_match = (
                    req_role in (el.role or "").lower()
                    or req_role in (el.control_type or "").lower()
                )
                if role_match:
                    role_boost = 0.05

            # Check class name if specified
            if intent.class_name:
                if not el.class_name or intent.class_name.lower() not in el.class_name.lower():
                    continue

            # Semantic match
            is_match, score = self._match_semantic_target(
                query=query,
                name=el.name,
                automation_id=el.automation_id,
                role=el.role,
                control_type=el.control_type,
                class_name=el.class_name,
            )

            if is_match:
                score += role_boost
                if el.is_focused:
                    score += 0.05
                scored_candidates.append((score, el))

        # If no snapshot elements matched, query genuine UI Automation directly for target window HWND
        if not scored_candidates and sys.platform == "win32" and target_win and target_win.hwnd:
            try:
                from accessibility_coordinator import AccessibilityCoordinator
                coord = AccessibilityCoordinator(timeout_ms=1500.0)
                live_elems, _ = coord.collect_accessibility_observations(hwnd=target_win.hwnd)
                if not live_elems:
                    time.sleep(0.3)
                    live_elems, _ = coord.collect_accessibility_observations(hwnd=target_win.hwnd)
                for uia_el in live_elems:
                    b = uia_el.bounds
                    if b.width <= 0 or b.height <= 0:
                        continue
                    el_cx = b.left + (b.width / 2.0)
                    el_cy = b.top + (b.height / 2.0)
                    if win_box:
                        w_left, w_top, w_right, w_bottom = win_box
                        if not (w_left - 30 <= el_cx <= w_right + 30 and w_top - 30 <= el_cy <= w_bottom + 30):
                            continue
                    
                    role_boost = 0.0
                    if intent.role:
                        req_role = intent.role.lower()
                        if req_role in (uia_el.role or "").lower() or req_role in (getattr(uia_el, "control_type", "") or "").lower():
                            role_boost = 0.05

                    is_match, score = self._match_semantic_target(
                        query=query,
                        name=uia_el.name,
                        automation_id=uia_el.automation_id,
                        role=uia_el.role,
                        control_type=getattr(uia_el, "control_type", None),
                        class_name=getattr(uia_el, "class_name", None),
                    )
                    if is_match:
                        score += role_boost
                        if uia_el.is_focused:
                            score += 0.05
                        src_val = getattr(uia_el, "evidence_source", None) or getattr(uia_el, "source", "UI_AUTOMATION")
                        if hasattr(src_val, "value"):
                            src_val = src_val.value
                        obs_el = ObservedElement(
                            element_id=f"el_live_{uia_el.element_id}",
                            source=str(src_val),
                            name=uia_el.name,
                            role=uia_el.role,
                            control_type=getattr(uia_el, "control_type", "Unknown") or "Unknown",
                            automation_id=uia_el.automation_id,
                            class_name=getattr(uia_el, "class_name", None),
                            bounds=BoundingBox(left=b.left, top=b.top, width=b.width, height=b.height),
                            is_enabled=uia_el.is_enabled,
                            is_focused=uia_el.is_focused,
                            is_offscreen=uia_el.is_offscreen,
                        )
                        scored_candidates.append((score, obs_el))

            except Exception as live_acc_err:
                logger.debug("Window-scoped accessibility collection notice: %s", live_acc_err)

        if not scored_candidates:
            # Fallback for document/editor surfaces: if targeting generic edit/input/document role without specific name,
            # resolve against active foreground window client area.
            if target_win:
                win_bounds = getattr(target_win, "client_bounds", None) or getattr(target_win, "extended_bounds", None)
                if win_bounds and win_bounds.width > 0 and win_bounds.height > 0:
                    generic_edit_roles = {"edit", "document", "input", "document_body", "editor", "text", "canvas"}
                    if not query or query.lower() in generic_edit_roles:

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

            # Tier 2: Attempt OCR fallback if accessibility did not resolve
            if query:
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
                    f"No accessible element matched criteria: query='{query}', "
                    f"role='{intent.role}', automation_id='{intent.automation_id}' in window {target_hwnd}"
                ),
            )

        # Sort candidates descending by score
        scored_candidates.sort(key=lambda item: item[0], reverse=True)

        top_score, top_el = scored_candidates[0]
        if len(scored_candidates) > 1:
            second_score, _ = scored_candidates[1]
            # If top two candidates have identical score and neither has exact name match or focus
            if abs(top_score - second_score) < 0.01 and not top_el.is_focused:
                exact_name_matches = [
                    c for score, c in scored_candidates
                    if query and c.name and c.name.strip().lower() == query.strip().lower()
                ]
                if len(exact_name_matches) == 1:
                    matched_el = exact_name_matches[0]
                else:
                    return TargetResolutionResult(
                        status=TargetResolutionStatus.AMBIGUOUS,
                        candidates_count=len(scored_candidates),
                        observation_id=snapshot.snapshot_id,
                        desktop_generation_id=snapshot.generation_id,
                        diagnostic_message=(
                            f"Ambiguous accessibility target: {len(scored_candidates)} elements matched "
                            f"query '{query}' (top scores: {top_score:.2f}, {second_score:.2f})"
                        ),
                    )
            else:
                matched_el = top_el
        else:
            matched_el = top_el

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
                confidence=min(1.0, top_score),
                evidence=TargetEvidence(
                    source=matched_el.source or "UI_AUTOMATION",
                    identifier=matched_el.element_id,
                    name=matched_el.name,
                    role=matched_el.role or matched_el.control_type,
                    confidence=min(1.0, top_score),
                    raw_metadata={
                        "control_type": matched_el.control_type,
                        "automation_id": matched_el.automation_id,
                        "class_name": matched_el.class_name,
                        "is_focused": matched_el.is_focused,
                        "target_hwnd": target_hwnd,
                    },
                ),
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                target_hwnd=target_hwnd,
            )
            return TargetResolutionResult(
                status=TargetResolutionStatus.RESOLVED,
                target=resolved,
                candidates_count=len(scored_candidates),
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
        """Resolve target from OCR text recognition evidence (Tier 2)."""
        query_text = intent.text or intent.name
        if not query_text or not query_text.strip():
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message="OCR_TEXT strategy requires non-empty 'text' or 'name' in TargetIntent",
            )

        has_explicit_window = bool(intent.window_title or intent.process_name or intent.target_hwnd)
        target_win = self._find_target_window(snapshot, intent) if has_explicit_window else None
        target_hwnd = target_win.hwnd if target_win else intent.target_hwnd

        # Extract target window bounding box for spatial containment filtering
        win_box = None
        if target_win and target_win.extended_bounds and has_explicit_window:
            wb = target_win.extended_bounds
            if wb.width > 0 and wb.height > 0:
                win_box = (wb.left, wb.top, wb.left + wb.width, wb.top + wb.height)

        # 1. Acquire OCR evidence: intent metadata, snapshot telemetry, or live synchronous scan
        ocr_result: Optional[OCRResult] = None
        ocr_result_raw = intent.metadata.get("ocr_result") or snapshot.telemetry.get("ocr_result")

        if ocr_result_raw is not None:
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

        if ocr_result is None:
            # Perform live synchronous OCR extraction
            engine = self._perception_engine
            if engine is None:
                from orbit.runtime.perception.engine import SemanticPerceptionEngine
                engine = SemanticPerceptionEngine()
            ocr_result = engine.scan_observation_sync(snapshot)

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
        engine = self._perception_engine
        if engine is None:
            from orbit.runtime.perception.engine import SemanticPerceptionEngine
            engine = SemanticPerceptionEngine()

        matches = engine.find_text_regions(
            ocr_result=ocr_result,
            query_text=query_text,
            exact_match=intent.exact_match,
            case_sensitive=intent.case_sensitive,
            min_confidence=intent.min_confidence,
        )

        # If direct string match returned nothing, check semantic digit aliases (e.g. query "7" matching "7" or "Seven")
        if not matches:
            digit_map = {
                "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
                "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
            }
            reverse_digit_map = {v: k for k, v in digit_map.items()}
            alt_query = digit_map.get(query_text.strip().lower()) or reverse_digit_map.get(query_text.strip().lower())
            if alt_query:
                matches = engine.find_text_regions(
                    ocr_result=ocr_result,
                    query_text=alt_query,
                    exact_match=False,
                    case_sensitive=False,
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

        # 5. Spatial window containment filter
        if win_box:
            w_left, w_top, w_right, w_bottom = win_box
            filtered_matches = []
            for m in matches:
                mc_x = m.bounding_box.left + (m.bounding_box.width / 2.0)
                mc_y = m.bounding_box.top + (m.bounding_box.height / 2.0)
                if (w_left - 30 <= mc_x <= w_right + 30) and (w_top - 30 <= mc_y <= w_bottom + 30):
                    filtered_matches.append(m)
            if filtered_matches:
                matches = filtered_matches
            else:
                return TargetResolutionResult(
                    status=TargetResolutionStatus.NOT_FOUND,
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=snapshot.generation_id,
                    candidates_count=0,
                    diagnostic_message=(
                        f"OCR text '{query_text}' was detected but lies outside the active window bounds ({win_box})"
                    ),
                )

        if len(matches) > 1:
            # Check if exactly 1 has exact text match
            exact_matches = [
                m for m in matches
                if m.text.strip().lower() == query_text.strip().lower()
            ]
            if len(exact_matches) == 1:
                match = exact_matches[0]
            else:
                candidate_boxes = [
                    f"('{m.text}' at {m.bounding_box.left},{m.bounding_box.top})"
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
        else:
            match = matches[0]

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

            # Display region containment check
            if snapshot.desktop_geometry:
                dg = snapshot.desktop_geometry
                if not (dg.left <= safe_pt.x <= dg.left + dg.width and dg.top <= safe_pt.y <= dg.top + dg.height):
                    return TargetResolutionResult(
                        status=TargetResolutionStatus.INVALID_REQUEST,
                        observation_id=snapshot.snapshot_id,
                        desktop_generation_id=snapshot.generation_id,
                        diagnostic_message=(
                            f"OCR resolved action point ({safe_pt.x}, {safe_pt.y}) "
                            f"is outside visible desktop bounds ({dg})"
                        ),
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
                        "target_hwnd": target_hwnd,
                    },
                ),
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                target_hwnd=target_hwnd,
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



