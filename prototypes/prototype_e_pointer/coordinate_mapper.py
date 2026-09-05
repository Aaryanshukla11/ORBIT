"""
Virtual Desktop Coordinate Engine & SendInput Normalization for ORBIT Prototype E.
(Mathematical and Win32 Virtual Desktop Geometry Mapping)

CRITICAL INVARIANT:
This module performs MATHEMATICAL AND SPATIAL TRANSFORMATIONS ONLY.
It contains NO SendInput calls, mouse movement, or pointer injection.
"""

import ctypes
from ctypes import wintypes
import time
from typing import Optional, Tuple

from app_types import (
    VirtualDesktopMetrics,
    VirtualDesktopTopologyIdentity,
    VirtualDesktopTopologyObservation,
    NormalizedCoordinate,
    PointerValidationResult,
    TargetValidationStatus,
    ValidationFailureReason,
)
from dpi_awareness import initialize_dpi_awareness

# Win32 System Metrics Constants
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SM_CMONITORS = 80

user32 = ctypes.windll.user32


def get_virtual_desktop_metrics() -> VirtualDesktopMetrics:
    """
    Retrieves the live physical bounding geometry of the Windows virtual desktop.
    Ensures DPI awareness is initialized so physical pixels are returned.
    """
    # Ensure DPI awareness is active
    initialize_dpi_awareness()

    x_origin = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y_origin = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

    # Fallback to primary screen metrics if virtual screen metrics return 0 width/height
    if width <= 0:
        width = user32.GetSystemMetrics(0)  # SM_CXSCREEN
    if height <= 0:
        height = user32.GetSystemMetrics(1)  # SM_CYSCREEN

    is_valid = width > 0 and height > 0

    return VirtualDesktopMetrics(
        x_origin=x_origin,
        y_origin=y_origin,
        width=width,
        height=height,
        is_valid=is_valid,
        timestamp_ns=time.perf_counter_ns(),
    )


def get_topology_identity() -> VirtualDesktopTopologyIdentity:
    """
    Retrieves the stable structural display topology identity.
    Excludes observation timestamps to ensure accurate identity comparison.
    """
    metrics = get_virtual_desktop_metrics()
    monitor_count = user32.GetSystemMetrics(SM_CMONITORS) or 1

    return VirtualDesktopTopologyIdentity(
        origin_x=metrics.x_origin,
        origin_y=metrics.y_origin,
        width=metrics.width,
        height=metrics.height,
        monitor_count=monitor_count,
    )


def get_topology_observation() -> VirtualDesktopTopologyObservation:
    """
    Retrieves a timestamped observation of the display topology.
    Combines stable topology identity with an observation timestamp.
    """
    identity = get_topology_identity()
    return VirtualDesktopTopologyObservation(
        identity=identity,
        observed_at_ns=time.perf_counter_ns(),
    )


def normalize_to_sendinput(
    physical_x: int,
    physical_y: int,
    metrics: Optional[VirtualDesktopMetrics] = None,
) -> Tuple[NormalizedCoordinate, PointerValidationResult]:
    """
    Normalizes a physical virtual screen coordinate (x, y) into the Win32 SendInput
    normalized absolute domain [0, 65535].

    Formula:
        delta_x = physical_x - x_virtual_origin
        delta_y = physical_y - y_virtual_origin

        norm_x = round(delta_x * 65535.0 / (width - 1))
        norm_y = round(delta_y * 65535.0 / (height - 1))

    Returns:
        Tuple[NormalizedCoordinate, PointerValidationResult]
        If the coordinate is outside the virtual desktop, PointerValidationResult
        explicitly indicates COORDINATE_OUT_OF_BOUNDS and the coordinate is marked
        as was_out_of_bounds=True.
    """
    start_ns = time.perf_counter_ns()

    if metrics is None:
        metrics = get_virtual_desktop_metrics()

    # Guard: Invalid or zero dimensions
    if not metrics.is_valid or metrics.width <= 0 or metrics.height <= 0:
        elapsed_us = (time.perf_counter_ns() - start_ns) / 1000.0
        return (
            NormalizedCoordinate(
                norm_x=0,
                norm_y=0,
                raw_x=physical_x,
                raw_y=physical_y,
                is_clamped=True,
                was_out_of_bounds=True,
            ),
            PointerValidationResult(
                is_valid=False,
                status=TargetValidationStatus.REJECTED,
                failure_reason=ValidationFailureReason.INVALID_VIRTUAL_DIMENSIONS,
                diagnostic_message=f"Virtual desktop dimensions are invalid: {metrics.width}x{metrics.height}",
                metrics_snapshot=metrics,
                validation_duration_us=elapsed_us,
            ),
        )

    # Check bounds containment
    is_in_bounds = metrics.contains_point(physical_x, physical_y)
    was_out_of_bounds = not is_in_bounds

    # Shift relative to virtual desktop origin (handles negative origins)
    delta_x = physical_x - metrics.x_origin
    delta_y = physical_y - metrics.y_origin

    # Compute normalization with denominator safety
    if metrics.width > 1:
        raw_norm_x = round(delta_x * 65535.0 / (metrics.width - 1))
    else:
        raw_norm_x = 0

    if metrics.height > 1:
        raw_norm_y = round(delta_y * 65535.0 / (metrics.height - 1))
    else:
        raw_norm_y = 0

    # Clamp to strictly valid 0..65535 domain
    clamped_x = max(0, min(65535, raw_norm_x))
    clamped_y = max(0, min(65535, raw_norm_y))
    is_clamped = (clamped_x != raw_norm_x) or (clamped_y != raw_norm_y)

    norm_coord = NormalizedCoordinate(
        norm_x=clamped_x,
        norm_y=clamped_y,
        raw_x=physical_x,
        raw_y=physical_y,
        is_clamped=is_clamped,
        was_out_of_bounds=was_out_of_bounds,
    )

    elapsed_us = (time.perf_counter_ns() - start_ns) / 1000.0

    if was_out_of_bounds:
        result = PointerValidationResult(
            is_valid=False,
            status=TargetValidationStatus.REJECTED,
            failure_reason=ValidationFailureReason.COORDINATE_OUT_OF_BOUNDS,
            diagnostic_message=(
                f"Coordinate ({physical_x}, {physical_y}) is outside virtual desktop bounds "
                f"[{metrics.x_origin}..{metrics.right}), [{metrics.y_origin}..{metrics.bottom})"
            ),
            metrics_snapshot=metrics,
            validation_duration_us=elapsed_us,
        )
    else:
        result = PointerValidationResult(
            is_valid=True,
            status=TargetValidationStatus.VALID,
            failure_reason=ValidationFailureReason.NONE,
            diagnostic_message=None,
            metrics_snapshot=metrics,
            validation_duration_us=elapsed_us,
        )

    return norm_coord, result


def denormalize_from_sendinput(
    norm_x: int,
    norm_y: int,
    metrics: Optional[VirtualDesktopMetrics] = None,
) -> Tuple[int, int]:
    """
    Inverse mapping from SendInput 0..65535 domain back to physical virtual screen pixels.
    Used for mathematical precision auditing and roundtrip verification.
    """
    if metrics is None:
        metrics = get_virtual_desktop_metrics()

    if not metrics.is_valid or metrics.width <= 1 or metrics.height <= 1:
        return metrics.x_origin, metrics.y_origin

    clamped_norm_x = max(0, min(65535, norm_x))
    clamped_norm_y = max(0, min(65535, norm_y))

    physical_x = metrics.x_origin + round(clamped_norm_x * (metrics.width - 1) / 65535.0)
    physical_y = metrics.y_origin + round(clamped_norm_y * (metrics.height - 1) / 65535.0)

    return physical_x, physical_y
