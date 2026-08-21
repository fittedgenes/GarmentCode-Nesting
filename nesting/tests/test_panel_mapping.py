"""Tests for nesting/data/panel_mapping.py"""
import pytest
from nesting.data.panel_mapping import (
    BOTTOM_TYPE_TO_PARAM,
    affected_panels,
    filter_parameters,
)


# ── BOTTOM_TYPE_TO_PARAM ────────────────────────────────────────────────────

def test_bottom_type_to_param_has_expected_keys():
    expected = {"SkirtCircle", "AsymmSkirtCircle", "GodetSkirt", "PencilSkirt",
                "Skirt2", "SkirtManyPanels", "SkirtLevels", "Pants"}
    assert set(BOTTOM_TYPE_TO_PARAM.keys()) == expected


@pytest.mark.parametrize("cls,expected_key", [
    ("SkirtCircle",      "flare-skirt"),
    ("AsymmSkirtCircle", "flare-skirt"),
    ("SkirtManyPanels",  "flare-skirt"),
    ("GodetSkirt",       "godet-skirt"),
    ("PencilSkirt",      "pencil-skirt"),
    ("Skirt2",           "skirt"),
    ("SkirtLevels",      "levels-skirt"),
    ("Pants",            "pants"),
])
def test_bottom_type_param_key(cls, expected_key):
    assert expected_key in BOTTOM_TYPE_TO_PARAM[cls]


# ── filter_parameters ───────────────────────────────────────────────────────

def _minimal_design(bottom_type: str) -> dict:
    """Build the minimal design dict that filter_parameters needs."""
    return {
        "meta": {"bottom": {"v": bottom_type}, "upper": {"v": None}, "wb": {"v": None}},
        "flare-skirt": {"length": {"v": 60}},
        "godet-skirt": {"length": {"v": 60}},
        "pencil-skirt": {"length": {"v": 60}},
        "skirt": {"length": {"v": 60}},
        "levels-skirt": {"length": {"v": 60}},
        "pants": {"length": {"v": 60}},
        "shirt": {"length": {"v": 70}},
        "collar": {"width": {"v": 5}},
        "sleeve": {"length": {"v": 50}},
        "waistband": {"width": {"v": 3}},
    }


# Panel patterns from PARAM_TO_PATTERNS for common garment parts
@pytest.mark.parametrize("bottom_type,expected_top_key,panel_ids", [
    ("SkirtCircle",  "flare-skirt", {"skirt_front"}),
    ("PencilSkirt",  "pencil-skirt", {"skirt_front"}),
    ("Pants",        "pants",        {"pant_front_left"}),
    ("Skirt2",       "skirt",        {"skirt_front"}),
])
def test_filter_parameters_includes_correct_bottom(bottom_type, expected_top_key, panel_ids):
    design = _minimal_design(bottom_type)
    result = filter_parameters(design, panel_ids=panel_ids)
    assert expected_top_key in result


@pytest.mark.parametrize("bottom_type,excluded_key,panel_ids", [
    ("SkirtCircle",  "pencil-skirt", {"skirt_front"}),
    ("PencilSkirt",  "flare-skirt",  {"skirt_front"}),
    ("Pants",        "skirt",        {"pant_front_left"}),
])
def test_filter_parameters_excludes_other_bottoms(bottom_type, excluded_key, panel_ids):
    design = _minimal_design(bottom_type)
    result = filter_parameters(design, panel_ids=panel_ids)
    assert excluded_key not in result


def test_filter_parameters_always_includes_meta():
    design = _minimal_design("SkirtCircle")
    result = filter_parameters(design, panel_ids={"skirt_front"})
    assert "meta" in result


# ── affected_panels ─────────────────────────────────────────────────────────

def test_affected_panels_waistband_width_matches_wb_patterns():
    panels = affected_panels(["waistband.width"])
    assert any("wb" in p for p in panels)


def test_affected_panels_unknown_param_returns_empty():
    panels = affected_panels(["totally.unknown.param"])
    assert len(panels) == 0


def test_affected_panels_sleeve_length():
    panels = affected_panels(["sleeve.length"])
    assert any("sleeve" in p for p in panels)
