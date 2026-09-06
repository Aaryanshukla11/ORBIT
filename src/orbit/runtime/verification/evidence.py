"""Evidence extraction from ObservationSnapshot preserving snapshot immutability."""

from __future__ import annotations

from typing import Optional
from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.runtime.verification.models import ObservationEvidenceSummary


def summarize_observation_evidence(snapshot: Optional[ObservationSnapshot]) -> Optional[ObservationEvidenceSummary]:
    """Extract a deterministic, immutable summary of observation evidence from a snapshot.

    Guarantees:
    - Does NOT mutate the input ObservationSnapshot in any way.
    - Preserves exact generation ID, timestamp, and entity collections.
    """
    if snapshot is None:
        return None

    fg_win = snapshot.foreground_window
    fg_hwnd = fg_win.hwnd if fg_win else None
    fg_title = fg_win.window_title if fg_win else None

    element_ids = [el.element_id for el in snapshot.detected_elements]
    window_hwnds = [w.hwnd for w in snapshot.windows]

    return ObservationEvidenceSummary(
        snapshot_id=snapshot.snapshot_id,
        desktop_generation_id=snapshot.generation_id,
        timestamp_ns=snapshot.timestamp_ns,
        is_stale=snapshot.is_stale,
        foreground_hwnd=fg_hwnd,
        foreground_title=fg_title,
        visible_window_count=len(snapshot.windows),
        element_count=len(snapshot.detected_elements),
        element_ids=element_ids,
        window_hwnds=window_hwnds,
        metadata={
            "freshness_state": snapshot.freshness_state.value,
            "invalidation_reason": snapshot.invalidation_reason,
            "desktop_width": snapshot.desktop_geometry.width,
            "desktop_height": snapshot.desktop_geometry.height,
        },
    )
