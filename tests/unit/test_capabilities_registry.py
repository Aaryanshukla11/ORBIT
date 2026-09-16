"""Unit tests for CapabilityRegistry and Capability models."""

import pytest
from orbit.runtime.capabilities.models import (
    Capability,
    CapabilityCategory,
    CapabilityLimitation,
)
from orbit.runtime.capabilities.registry import CapabilityRegistry


def test_capability_registry_defaults():
    registry = CapabilityRegistry(register_defaults=True)
    caps = registry.list_all()
    assert len(caps) >= 8

    cap_ids = {c.capability_id for c in caps}
    assert "LAUNCH_APPLICATION" in cap_ids
    assert "FOCUS_WINDOW" in cap_ids
    assert "TYPE_TEXT" in cap_ids
    assert "CLICK_ELEMENT" in cap_ids
    assert "DRAW_BASIC_GEOMETRY" in cap_ids
    assert "DRAW_FREEFORM_STROKES" in cap_ids
    assert "IMAGE_GENERATE_AND_INSERT" in cap_ids
    assert "CLIPBOARD_PASTE" in cap_ids


def test_draw_basic_geometry_limitations():
    registry = CapabilityRegistry(register_defaults=True)
    geom = registry.get("DRAW_BASIC_GEOMETRY")
    assert geom is not None

    # Supported shapes
    assert geom.can_handle_subtype("cube") is True
    assert geom.can_handle_subtype("circle") is True
    assert geom.can_handle_subtype("square") is True
    assert geom.can_handle_subtype("star") is True

    # Unsupported complex artwork & portraits violate limitations
    lim1 = geom.violates_limitation("draw a portrait of a boy")
    assert lim1 is not None
    assert "portrait" in lim1.unsupported_patterns or "boy" in lim1.unsupported_patterns

    lim2 = geom.violates_limitation("sketch a realistic face")
    assert lim2 is not None

    # Basic shape does not violate limitations
    lim3 = geom.violates_limitation("draw a cube in paint")
    assert lim3 is None


def test_custom_capability_registration():
    registry = CapabilityRegistry(register_defaults=False)
    assert len(registry.list_all()) == 0

    custom = Capability(
        capability_id="SPECIALIZED_SPREADSHEET_MATH",
        name="Spreadsheet Calculation Skill",
        description="Executes formula calculations in Excel",
        category=CapabilityCategory.DATA,
        supported_goal_types=["calculate_spreadsheet"],
        reliability_score=0.99,
        is_available=True,
    )
    registry.register(custom)

    retrieved = registry.get("SPECIALIZED_SPREADSHEET_MATH")
    assert retrieved is not None
    assert retrieved.category == CapabilityCategory.DATA
    assert len(registry.list_available()) == 1
