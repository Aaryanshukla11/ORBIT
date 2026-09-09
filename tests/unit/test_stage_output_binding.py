"""Unit tests for StageOutputResolver and dynamic pipeline binding (M1.9 Component 4)."""

import pytest

from orbit.runtime.capabilities.execution.output_binding import (
    StageOutputBindingError,
    StageOutputResolver,
)


def test_stage_output_resolver_direct_reference():
    """Exact single template reference preserves native types."""
    stage_outputs = {
        "stage_0": {
            "image_path": "C:\\temp\\test.png",
            "hwnd": 9988,
            "success": True,
        }
    }

    raw_params = {
        "target_image": "{{stage_0.image_path}}",
        "target_hwnd": "{{stage_0.hwnd}}",
        "status": "{{stage_0.success}}",
    }

    ok, resolved, err = StageOutputResolver.resolve_parameters(raw_params, stage_outputs)
    assert ok is True
    assert err is None
    assert resolved["target_image"] == "C:\\temp\\test.png"
    assert resolved["target_hwnd"] == 9988
    assert resolved["status"] is True


def test_stage_output_resolver_string_interpolation():
    """String with embedded references interpolates correctly."""
    stage_outputs = {
        "stage_0": {"name": "Notepad", "pid": 1234},
    }

    raw_params = {
        "description": "Connecting to {{stage_0.name}} process {{stage_0.pid}}",
    }

    ok, resolved, err = StageOutputResolver.resolve_parameters(raw_params, stage_outputs)
    assert ok is True
    assert resolved["description"] == "Connecting to Notepad process 1234"


def test_stage_output_resolver_missing_stage_fails_closed():
    """Referencing an unexecuted or non-existent stage fails closed with an error."""
    stage_outputs = {
        "stage_0": {"data": "hello"},
    }

    raw_params = {
        "input": "{{stage_1.data}}",
    }

    ok, resolved, err = StageOutputResolver.resolve_parameters(raw_params, stage_outputs)
    assert ok is False
    assert "stage_1" in err
    assert "not found" in err


def test_stage_output_resolver_missing_field_fails_closed():
    """Referencing an absent field within a stage fails closed."""
    stage_outputs = {
        "stage_0": {"data": "hello"},
    }

    raw_params = {
        "input": "{{stage_0.missing_field}}",
    }

    ok, resolved, err = StageOutputResolver.resolve_parameters(raw_params, stage_outputs)
    assert ok is False
    assert "missing_field" in err
