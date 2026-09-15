"""
Observation Snapshot Adapter Boundary for ORBIT Prototype E.
(Cross-Prototype Contract Adapter for Prototype D Snapshots)

Converts external observation snapshots into immutable ValidatedPointerTarget contracts.
Enforces strict schema validation without fabricating missing data or modifying Prototype D.
"""

from typing import Any, Dict, Optional, Tuple, Union
import time

from app_types import (
    Rect,
    ValidatedPointerTarget,
    SnapshotValidationResult,
    ValidationFailureReason,
)


def _safe_get(obj: Any, attr: str, default: Any = None) -> Any:
    """Helper to retrieve field from either dataclass/object attribute or dictionary."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def adapt_observation_snapshot(
    snapshot: Any,
    target_id: Optional[str] = None,
    click_point: Optional[Tuple[int, int]] = None,
    require_foreground: bool = True,
    validity_ttl_ms: float = 500.0,
) -> SnapshotValidationResult:
    """
    Adapts an external observation snapshot (from Prototype D or mock testbeds)
    into an immutable ValidatedPointerTarget.

    Enforces mandatory presence of:
    - generation_id (int)
    - timestamp_ns (int)
    - native_hwnd (int)
    - process_id (int)
    - target spatial bounds (Rect)

    Fails explicitly if any required field is missing, None, or invalid.
    NEVER fabricates missing identity data.
    """
    if snapshot is None:
        return SnapshotValidationResult(
            is_valid=False,
            failure_reason=ValidationFailureReason.ADAPTER_MISSING_REQUIRED_FIELD,
            target=None,
            error_message="Snapshot object is None.",
        )

    # 1. Extract generation_id
    generation_id = _safe_get(snapshot, "generation_id")
    if generation_id is None or not isinstance(generation_id, int):
        return SnapshotValidationResult(
            is_valid=False,
            failure_reason=ValidationFailureReason.ADAPTER_MISSING_REQUIRED_FIELD,
            target=None,
            error_message="Snapshot missing mandatory integer 'generation_id'.",
        )

    # 2. Extract snapshot timestamp_ns
    timestamp_ns = _safe_get(snapshot, "timestamp_ns")
    if timestamp_ns is None or not isinstance(timestamp_ns, int) or timestamp_ns <= 0:
        return SnapshotValidationResult(
            is_valid=False,
            failure_reason=ValidationFailureReason.ADAPTER_MISSING_REQUIRED_FIELD,
            target=None,
            error_message="Snapshot missing mandatory integer 'timestamp_ns'.",
        )

    # 3. Locate target window and target element
    foreground_window = _safe_get(snapshot, "foreground_window")
    detected_targets = _safe_get(snapshot, "detected_targets", ())
    windows = _safe_get(snapshot, "windows", ())

    # Find the target element/window
    chosen_target = None
    if target_id and detected_targets:
        for t in detected_targets:
            if _safe_get(t, "target_id") == target_id:
                chosen_target = t
                break
    elif detected_targets and len(detected_targets) > 0:
        chosen_target = detected_targets[0]

    # Resolve HWND and PID
    native_hwnd = None
    process_id = None
    class_name = None

    if foreground_window:
        native_hwnd = _safe_get(foreground_window, "hwnd")
        process_id = _safe_get(foreground_window, "process_id")
        class_name = _safe_get(foreground_window, "class_name")
    elif windows and len(windows) > 0:
        native_hwnd = _safe_get(windows[0], "hwnd")
        process_id = _safe_get(windows[0], "process_id")
        class_name = _safe_get(windows[0], "class_name")

    # If target has its own native_hwnd / process_id override
    if chosen_target:
        if _safe_get(chosen_target, "native_hwnd") is not None:
            native_hwnd = _safe_get(chosen_target, "native_hwnd")
        if _safe_get(chosen_target, "process_id") is not None:
            process_id = _safe_get(chosen_target, "process_id")

    if native_hwnd is None or not isinstance(native_hwnd, int) or native_hwnd <= 0:
        return SnapshotValidationResult(
            is_valid=False,
            failure_reason=ValidationFailureReason.ADAPTER_MISSING_REQUIRED_FIELD,
            target=None,
            error_message="Snapshot missing valid target 'native_hwnd'.",
        )

    if process_id is None or not isinstance(process_id, int) or process_id <= 0:
        return SnapshotValidationResult(
            is_valid=False,
            failure_reason=ValidationFailureReason.ADAPTER_MISSING_REQUIRED_FIELD,
            target=None,
            error_message="Snapshot missing valid target 'process_id'.",
        )

    # 4. Resolve spatial bounding box
    raw_bounds = None
    if chosen_target:
        raw_bounds = _safe_get(chosen_target, "physical_bounds") or _safe_get(chosen_target, "bounds")
    elif foreground_window:
        raw_bounds = _safe_get(foreground_window, "extended_bounds") or _safe_get(foreground_window, "client_bounds")

    if raw_bounds is None:
        return SnapshotValidationResult(
            is_valid=False,
            failure_reason=ValidationFailureReason.ADAPTER_MISSING_REQUIRED_FIELD,
            target=None,
            error_message="Snapshot missing target bounding box ('physical_bounds' or 'extended_bounds').",
        )

    # Convert bounds to Rect
    if isinstance(raw_bounds, Rect):
        target_bounds = raw_bounds
    elif hasattr(raw_bounds, "left") and hasattr(raw_bounds, "right"):
        target_bounds = Rect(
            left=raw_bounds.left,
            top=raw_bounds.top,
            right=raw_bounds.right,
            bottom=raw_bounds.bottom,
        )
    elif isinstance(raw_bounds, (tuple, list)) and len(raw_bounds) == 4:
        target_bounds = Rect(
            left=raw_bounds[0],
            top=raw_bounds[1],
            right=raw_bounds[2],
            bottom=raw_bounds[3],
        )
    else:
        return SnapshotValidationResult(
            is_valid=False,
            failure_reason=ValidationFailureReason.ADAPTER_MISSING_REQUIRED_FIELD,
            target=None,
            error_message=f"Bounding box format is unrecognized: {type(raw_bounds)}.",
        )

    # 5. Resolve Click Point
    if click_point is None:
        click_point = target_bounds.center

    # 6. Resolve Confidence
    raw_conf = _safe_get(chosen_target, "confidence") or _safe_get(snapshot, "confidence", "HIGH")
    if hasattr(raw_conf, "value"):
        confidence_str = str(raw_conf.value)
    else:
        confidence_str = str(raw_conf)

    resolved_target_id = (
        target_id
        or _safe_get(chosen_target, "target_id")
        or f"target_hwnd_{native_hwnd}_{timestamp_ns}"
    )

    target = ValidatedPointerTarget(
        target_id=resolved_target_id,
        native_hwnd=native_hwnd,
        process_id=process_id,
        class_name=class_name,
        expected_bounds=target_bounds,
        click_point=click_point,
        source_generation_id=generation_id,
        source_snapshot_timestamp_ns=timestamp_ns,
        confidence=confidence_str,
        require_foreground=require_foreground,
        validity_ttl_ms=validity_ttl_ms,
    )

    return SnapshotValidationResult(
        is_valid=True,
        failure_reason=ValidationFailureReason.NONE,
        target=target,
        error_message=None,
    )
