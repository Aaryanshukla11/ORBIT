"""Deterministic safe action-point calculation within target bounding boxes."""

from __future__ import annotations

import math
from typing import Union

from orbit.models.common import BoundingBox
from orbit.runtime.targeting.models import SafeActionPoint, TargetBoundingBox


# Strict bounds for 32-bit signed integer virtual desktop coordinates
WIN32_COORD_MIN = -32768
WIN32_COORD_MAX = 32767


def calculate_safe_action_point(
    bounds: Union[TargetBoundingBox, BoundingBox],
    desktop_generation_id: int,
    relative_x: float = 0.5,
    relative_y: float = 0.5,
) -> SafeActionPoint:
    """Calculate a deterministic, safe interior action point within a target bounding box.

    Fail-closed rules:
    1. Rejects zero-area targets (width <= 0 or height <= 0).
    2. Rejects inverted geometry (right <= left or bottom <= top).
    3. Rejects non-finite or invalid coordinates.
    4. Rejects coordinates outside Win32 safe virtual desktop integer bounds.
    5. Rejects relative offsets outside [0.0, 1.0].
    6. Ensures action point strictly resides inside the bounding box.

    Args:
        bounds: TargetBoundingBox or BoundingBox specifying target geometry.
        desktop_generation_id: Desktop generation under which the target was observed.
        relative_x: Horizontal fraction inside bounds (default 0.5 for center).
        relative_y: Vertical fraction inside bounds (default 0.5 for center).

    Returns:
        SafeActionPoint with exact physical desktop coordinates and provenance.

    Raises:
        ValueError: If geometry is zero-area, inverted, or outside integer safety limits.
    """
    if isinstance(bounds, BoundingBox):
        tbox = TargetBoundingBox.from_bounding_box(bounds)
    elif isinstance(bounds, TargetBoundingBox):
        tbox = bounds
    else:
        raise ValueError(f"Unsupported bounds type: {type(bounds)}")

    # 1. Validate orientation and area
    if not tbox.is_valid or tbox.width <= 0 or tbox.height <= 0:
        raise ValueError(
            f"Invalid target bounding box: left={tbox.left}, top={tbox.top}, "
            f"right={tbox.right}, bottom={tbox.bottom} (width={tbox.width}, height={tbox.height}). "
            f"Targets must have strictly positive dimensions."
        )

    # 2. Validate generation ID
    if desktop_generation_id < 0:
        raise ValueError(f"desktop_generation_id must be non-negative (got {desktop_generation_id})")

    # 3. Validate relative offsets
    if not (0.0 <= relative_x <= 1.0) or math.isnan(relative_x):
        raise ValueError(f"relative_x must be in [0.0, 1.0] (got {relative_x})")
    if not (0.0 <= relative_y <= 1.0) or math.isnan(relative_y):
        raise ValueError(f"relative_y must be in [0.0, 1.0] (got {relative_y})")

    # 4. Safe interior clamping rule:
    # For large targets, default center is fine. If relative offsets are requested on border (0.0 or 1.0),
    # clamp slightly inward by at least 1 pixel (or 10%) so clicks don't hit edge resizing borders.
    if tbox.width > 2:
        inset_x = max(1, int(tbox.width * 0.05))
        min_x = tbox.left + inset_x
        max_x = tbox.right - inset_x - 1
    else:
        min_x = tbox.left
        max_x = tbox.left

    if tbox.height > 2:
        inset_y = max(1, int(tbox.height * 0.05))
        min_y = tbox.top + inset_y
        max_y = tbox.bottom - inset_y - 1
    else:
        min_y = tbox.top
        max_y = tbox.top

    # Compute coordinate
    raw_x = tbox.left + int((tbox.width - 1) * relative_x)
    raw_y = tbox.top + int((tbox.height - 1) * relative_y)

    action_x = max(min_x, min(max_x, raw_x))
    action_y = max(min_y, min(max_y, raw_y))

    # 5. Check integer-safety ranges
    if not (WIN32_COORD_MIN <= action_x <= WIN32_COORD_MAX):
        raise ValueError(f"Computed action X ({action_x}) exceeds Win32 integer bounds [{WIN32_COORD_MIN}, {WIN32_COORD_MAX}]")
    if not (WIN32_COORD_MIN <= action_y <= WIN32_COORD_MAX):
        raise ValueError(f"Computed action Y ({action_y}) exceeds Win32 integer bounds [{WIN32_COORD_MIN}, {WIN32_COORD_MAX}]")

    # 6. Verify strictly inside target bounding box
    if not (tbox.left <= action_x < tbox.right and tbox.top <= action_y < tbox.bottom):
        raise ValueError(
            f"Calculated action point ({action_x}, {action_y}) is outside target bounding box "
            f"[{tbox.left}, {tbox.top}, {tbox.right}, {tbox.bottom}]"
        )

    return SafeActionPoint(
        x=action_x,
        y=action_y,
        bounding_box=tbox,
        relative_x=relative_x,
        relative_y=relative_y,
        desktop_generation_id=desktop_generation_id,
    )
