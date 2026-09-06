"""Concrete evidence-based verification strategy evaluators."""

from __future__ import annotations

from typing import List, Optional, Tuple
from orbit.adapters.observation.snapshot import ObservationSnapshot, ObservedElement, ObservedWindow
from orbit.runtime.verification.models import (
    ExpectedOutcome,
    ExpectedOutcomeType,
    VerificationOutcome,
)


def evaluate_window_state_change(
    pre_snap: ObservationSnapshot,
    post_snap: ObservationSnapshot,
    expected: ExpectedOutcome,
) -> Tuple[VerificationOutcome, float, List[str], Optional[str]]:
    """Verify window state transitions (appearance, closure, focus)."""
    pre_hwnds = {w.hwnd for w in pre_snap.windows}
    post_hwnds = {w.hwnd for w in post_snap.windows}

    if expected.outcome_type == ExpectedOutcomeType.WINDOW_APPEARED:
        # Check if new window matching title or HWND appeared
        new_hwnds = post_hwnds - pre_hwnds
        matching_new_windows = [
            w for w in post_snap.windows
            if w.hwnd in new_hwnds and (
                not expected.window_title
                or expected.window_title.lower() in w.window_title.lower()
            )
        ]
        if matching_new_windows:
            win = matching_new_windows[0]
            msg = f"Expected window appeared: '{win.window_title}' (HWND: {win.hwnd})"
            return VerificationOutcome.VERIFIED_SUCCESS, 0.95, [msg], None

        # Check if title matches any visible window that was previously not visible
        matching_visible = [
            w for w in post_snap.windows
            if expected.window_title and expected.window_title.lower() in w.window_title.lower() and w.hwnd not in pre_hwnds
        ]
        if matching_visible:
            win = matching_visible[0]
            msg = f"Expected window appeared: '{win.window_title}' (HWND: {win.hwnd})"
            return VerificationOutcome.VERIFIED_SUCCESS, 0.95, [msg], None

        return (
            VerificationOutcome.VERIFIED_FAILURE,
            0.90,
            [],
            f"Expected window '{expected.window_title}' did not appear in post-action window list",
        )

    elif expected.outcome_type == ExpectedOutcomeType.WINDOW_CLOSED:
        # Check if window was in pre_snap but is missing in post_snap
        closed_hwnds = pre_hwnds - post_hwnds
        target_was_open = any(
            (expected.target_hwnd and w.hwnd == expected.target_hwnd)
            or (expected.window_title and expected.window_title.lower() in w.window_title.lower())
            for w in pre_snap.windows
        )
        if not target_was_open:
            return (
                VerificationOutcome.INCONCLUSIVE,
                0.50,
                [],
                f"Target window '{expected.window_title or expected.target_hwnd}' was not open before action",
            )

        target_still_open = any(
            (expected.target_hwnd and w.hwnd == expected.target_hwnd)
            or (expected.window_title and expected.window_title.lower() in w.window_title.lower())
            for w in post_snap.windows
        )
        if not target_still_open:
            msg = f"Target window '{expected.window_title or expected.target_hwnd}' closed successfully"
            return VerificationOutcome.VERIFIED_SUCCESS, 0.95, [msg], None
        else:
            return (
                VerificationOutcome.VERIFIED_FAILURE,
                0.90,
                [],
                f"Target window '{expected.window_title or expected.target_hwnd}' remains open after action",
            )

    elif expected.outcome_type == ExpectedOutcomeType.WINDOW_FOCUSED:
        fg_post = post_snap.foreground_window
        title_query = (expected.window_title or expected.target_name or "").lower()

        if fg_post is None:
            # Fallback to checking if target window is visible in post_snap
            target_present = any(
                (expected.target_hwnd and w.hwnd == expected.target_hwnd)
                or (title_query and ((w.window_title and title_query in w.window_title.lower()) or (w.process_name and title_query in w.process_name.lower())))
                for w in post_snap.windows
            )
            if target_present:
                display_title = expected.window_title or expected.target_name or "Target Window"
                msg = f"Target window '{display_title}' is confirmed visible on desktop"
                return VerificationOutcome.VERIFIED_SUCCESS, 0.85, [msg], None
            return VerificationOutcome.VERIFIED_FAILURE, 0.85, [], "No foreground window present after action"

        title_match = (
            not title_query
            or (fg_post.window_title and title_query in fg_post.window_title.lower())
            or (fg_post.process_name and title_query in fg_post.process_name.lower())
            or any(
                w.process_id == fg_post.process_id and title_query in (w.window_title or "").lower()
                for w in post_snap.windows
            )
        )
        hwnd_match = (
            expected.target_hwnd is None
            or expected.target_hwnd == fg_post.hwnd
            or any(
                w.hwnd == expected.target_hwnd and w.process_id == fg_post.process_id
                for w in post_snap.windows
            )
        )
        if title_match and hwnd_match:
            display_title = fg_post.window_title or fg_post.process_name or f"HWND {fg_post.hwnd}"
            msg = f"Target window '{display_title}' (HWND: {fg_post.hwnd}) is in foreground focus"
            return VerificationOutcome.VERIFIED_SUCCESS, 0.95, [msg], None
        else:
            target_present = any(
                (expected.target_hwnd and w.hwnd == expected.target_hwnd)
                or (title_query and ((w.window_title and title_query in w.window_title.lower()) or (w.process_name and title_query in w.process_name.lower())))
                for w in post_snap.windows
            )
            if target_present:
                display_title = expected.window_title or expected.target_name or "Target Window"
                msg = f"Target window '{display_title}' is confirmed visible on desktop"
                return VerificationOutcome.VERIFIED_SUCCESS, 0.85, [msg], None
            return (
                VerificationOutcome.VERIFIED_FAILURE,
                0.85,
                [],
                f"Target window '{expected.window_title or expected.target_name}' is not foreground or visible (active: '{fg_post.window_title or fg_post.process_name}')",
            )

    return VerificationOutcome.INCONCLUSIVE, 0.50, [], f"Unsupported window outcome type: {expected.outcome_type}"


def evaluate_accessibility_state_change(
    pre_snap: ObservationSnapshot,
    post_snap: ObservationSnapshot,
    expected: ExpectedOutcome,
) -> Tuple[VerificationOutcome, float, List[str], Optional[str]]:
    """Verify accessibility control state transitions."""
    if expected.outcome_type == ExpectedOutcomeType.TARGET_DISAPPEARED:
        # Check if target was present before and disappeared after
        pre_matches = [
            el for el in pre_snap.detected_elements
            if (expected.target_name and el.name and expected.target_name.lower() in el.name.lower())
            or (expected.target_id and el.element_id == expected.target_id)
        ]
        post_matches = [
            el for el in post_snap.detected_elements
            if (expected.target_name and el.name and expected.target_name.lower() in el.name.lower())
            or (expected.target_id and el.element_id == expected.target_id)
        ]
        if pre_matches and not post_matches:
            msg = f"Target element '{expected.target_name or expected.target_id}' disappeared as expected"
            return VerificationOutcome.VERIFIED_SUCCESS, 0.95, [msg], None
        elif post_matches:
            return (
                VerificationOutcome.VERIFIED_FAILURE,
                0.90,
                [],
                f"Target element '{expected.target_name or expected.target_id}' remains present after action",
            )
        else:
            return (
                VerificationOutcome.INCONCLUSIVE,
                0.50,
                [],
                f"Target element '{expected.target_name}' was not detected in pre-action observation",
            )

    elif expected.outcome_type == ExpectedOutcomeType.TARGET_APPEARED:
        pre_matches = [
            el for el in pre_snap.detected_elements
            if (expected.target_name and el.name and expected.target_name.lower() in el.name.lower())
            or (expected.target_id and el.element_id == expected.target_id)
        ]
        post_matches = [
            el for el in post_snap.detected_elements
            if (expected.target_name and el.name and expected.target_name.lower() in el.name.lower())
            or (expected.target_id and el.element_id == expected.target_id)
        ]
        if post_matches and not pre_matches:
            msg = f"Target element '{expected.target_name or expected.target_id}' appeared as expected"
            return VerificationOutcome.VERIFIED_SUCCESS, 0.95, [msg], None
        elif not post_matches:
            return (
                VerificationOutcome.VERIFIED_FAILURE,
                0.90,
                [],
                f"Target element '{expected.target_name or expected.target_id}' did not appear",
            )
        else:
            return (
                VerificationOutcome.INCONCLUSIVE,
                0.50,
                [],
                f"Target element '{expected.target_name}' was already present before action",
            )

    elif expected.outcome_type == ExpectedOutcomeType.ELEMENT_STATE_CHANGED:
        def _matches(el) -> bool:
            if expected.target_name and el.name and expected.target_name.lower() in el.name.lower():
                return True
            if expected.target_id and el.element_id == expected.target_id:
                return True
            if not expected.target_name and not expected.target_id and expected.target_role:
                if el.role and expected.target_role.lower() == el.role.lower():
                    return True
                if el.control_type and expected.target_role.lower() == el.control_type.lower():
                    return True
            return False

        # Find element in both snapshots
        pre_el = next((el for el in pre_snap.detected_elements if _matches(el)), None)
        post_el = next((el for el in post_snap.detected_elements if _matches(el)), None)
        if pre_el is None or post_el is None:
            if post_snap.windows and (post_snap.foreground_window or post_snap.generation_id > pre_snap.generation_id):
                return VerificationOutcome.VERIFIED_SUCCESS, 0.85, ["Target window is active on desktop and observation state progressed"], None
            return (
                VerificationOutcome.INCONCLUSIVE,
                0.50,
                [],
                f"Target element '{expected.target_name or expected.target_role or 'element'}' could not be compared across pre/post observations",
            )

        prop = expected.expected_property or "is_focused"
        pre_val = getattr(pre_el, prop, None)
        post_val = getattr(post_el, prop, None)

        if expected.expected_value is not None:
            if post_val == expected.expected_value:
                msg = f"Element property '{prop}' changed to expected value '{expected.expected_value}'"
                return VerificationOutcome.VERIFIED_SUCCESS, 0.95, [msg], None
            else:
                return (
                    VerificationOutcome.VERIFIED_FAILURE,
                    0.90,
                    [],
                    f"Element property '{prop}' is '{post_val}' (expected: '{expected.expected_value}')",
                )
        else:
            if pre_val != post_val or post_val is True:
                msg = f"Element property '{prop}' is active / changed ('{pre_val}' -> '{post_val}')"
                return VerificationOutcome.VERIFIED_SUCCESS, 0.90, [msg], None
            else:
                return (
                    VerificationOutcome.VERIFIED_FAILURE,
                    0.85,
                    [],
                    f"Element property '{prop}' remained unchanged ('{pre_val}')",
                )

    elif expected.outcome_type == ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE:
        return evaluate_observation_state_delta(pre_snap, post_snap, expected)

    return VerificationOutcome.INCONCLUSIVE, 0.50, [], f"Unsupported accessibility outcome type: {expected.outcome_type}"


def evaluate_observation_state_delta(
    pre_snap: ObservationSnapshot,
    post_snap: ObservationSnapshot,
    expected: Optional[ExpectedOutcome] = None,
) -> Tuple[VerificationOutcome, float, List[str], Optional[str]]:
    """Evaluate general observable changes between pre- and post-action observations."""
    changes: List[str] = []

    # 1. Check foreground window change
    pre_fg = pre_snap.foreground_window.hwnd if pre_snap.foreground_window else None
    post_fg = post_snap.foreground_window.hwnd if post_snap.foreground_window else None
    if pre_fg != post_fg:
        changes.append(f"Foreground window changed from HWND {pre_fg} to {post_fg}")

    # 2. Check window list delta
    pre_hwnds = {w.hwnd for w in pre_snap.windows}
    post_hwnds = {w.hwnd for w in post_snap.windows}
    new_hwnds = post_hwnds - pre_hwnds
    closed_hwnds = pre_hwnds - post_hwnds
    if new_hwnds:
        changes.append(f"{len(new_hwnds)} new window(s) appeared (HWNDs: {list(new_hwnds)})")
    if closed_hwnds:
        changes.append(f"{len(closed_hwnds)} window(s) closed (HWNDs: {list(closed_hwnds)})")

    # 3. Check element count delta
    pre_els = {el.element_id for el in pre_snap.detected_elements}
    post_els = {el.element_id for el in post_snap.detected_elements}
    new_els = post_els - pre_els
    removed_els = pre_els - post_els
    if new_els:
        changes.append(f"{len(new_els)} new element(s) appeared")
    if removed_els:
        changes.append(f"{len(removed_els)} element(s) disappeared")

    if changes:
        return VerificationOutcome.VERIFIED_SUCCESS, 0.80, changes, None
    else:
        if expected is not None and expected.outcome_type == ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE:
            return (
                VerificationOutcome.VERIFIED_FAILURE,
                0.80,
                [],
                "Zero observable UI state changes detected after action dispatch",
            )
        return (
            VerificationOutcome.INCONCLUSIVE,
            0.30,
            [],
            "Zero observable UI state changes detected and no specific outcome was declared",
        )
