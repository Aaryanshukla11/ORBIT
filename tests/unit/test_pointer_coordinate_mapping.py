"""Unit tests for pointer coordinate normalization and bounds validation."""

import time
import pytest

from orbit.adapters.pointer.movement import normalize_to_sendinput
from orbit.adapters.pointer.safety import VirtualDesktopMetrics


def test_origin_mapping():
    metrics = VirtualDesktopMetrics(
        x_origin=0,
        y_origin=0,
        width=1920,
        height=1080,
        is_valid=True,
        timestamp_ns=time.perf_counter_ns(),
    )
    norm_x, norm_y, is_valid = normalize_to_sendinput(0, 0, metrics)
    assert is_valid is True
    assert norm_x == 0
    assert norm_y == 0


def test_bottom_right_mapping():
    metrics = VirtualDesktopMetrics(
        x_origin=0,
        y_origin=0,
        width=1920,
        height=1080,
        is_valid=True,
        timestamp_ns=time.perf_counter_ns(),
    )
    norm_x, norm_y, is_valid = normalize_to_sendinput(1919, 1079, metrics)
    assert is_valid is True
    assert norm_x == 65535
    assert norm_y == 65535


def test_center_mapping():
    metrics = VirtualDesktopMetrics(
        x_origin=0,
        y_origin=0,
        width=1920,
        height=1080,
        is_valid=True,
        timestamp_ns=time.perf_counter_ns(),
    )
    norm_x, norm_y, is_valid = normalize_to_sendinput(960, 540, metrics)
    assert is_valid is True
    # 960 / 1919 * 65535 = 32784
    assert 32700 <= norm_x <= 32850
    # 540 / 1079 * 65535 = 32797
    assert 32700 <= norm_y <= 32850


def test_out_of_bounds_rejection():
    metrics = VirtualDesktopMetrics(
        x_origin=0,
        y_origin=0,
        width=1920,
        height=1080,
        is_valid=True,
        timestamp_ns=time.perf_counter_ns(),
    )
    # Negative coordinate
    _, _, is_valid_neg = normalize_to_sendinput(-5, 500, metrics)
    assert is_valid_neg is False

    # Past width
    _, _, is_valid_over_w = normalize_to_sendinput(1920, 500, metrics)
    assert is_valid_over_w is False

    # Past height
    _, _, is_valid_over_h = normalize_to_sendinput(500, 1080, metrics)
    assert is_valid_over_h is False


def test_negative_origin_synthetic_mapping():
    """Test multi-monitor layout with negative virtual desktop origin."""
    metrics = VirtualDesktopMetrics(
        x_origin=-1920,
        y_origin=-500,
        width=3840,
        height=1580,
        is_valid=True,
        timestamp_ns=time.perf_counter_ns(),
    )
    # Top-left of secondary monitor
    norm_x, norm_y, is_valid = normalize_to_sendinput(-1920, -500, metrics)
    assert is_valid is True
    assert norm_x == 0
    assert norm_y == 0

    # Bottom-right
    norm_x_br, norm_y_br, is_valid_br = normalize_to_sendinput(-1920 + 3840 - 1, -500 + 1580 - 1, metrics)
    assert is_valid_br is True
    assert norm_x_br == 65535
    assert norm_y_br == 65535


def test_invalid_dimension_protection():
    metrics = VirtualDesktopMetrics(
        x_origin=0,
        y_origin=0,
        width=0,
        height=0,
        is_valid=False,
        timestamp_ns=time.perf_counter_ns(),
    )
    norm_x, norm_y, is_valid = normalize_to_sendinput(0, 0, metrics)
    assert is_valid is False
