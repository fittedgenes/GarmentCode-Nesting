"""Tests for nesting/core/layout.py — Piece class"""
import math
import pytest
from nesting.core.layout import Piece


def _square(size: float = 10.0) -> list:
    """Return a simple square polygon as a list of (x, y) tuples."""
    return [(0, 0), (size, 0), (size, size), (0, size)]


def _make_piece(size: float = 10.0) -> Piece:
    return Piece([[x, y] for x, y in _square(size)], id="test")


# ── Bounding box ────────────────────────────────────────────────────────────

def test_bbox_initial():
    p = _make_piece(10)
    assert p.bbox_width == pytest.approx(10.0)
    assert p.bbox_height == pytest.approx(10.0)
    assert p.bbox_area == pytest.approx(100.0)


def test_width_height_properties():
    p = _make_piece(10)
    assert p.width == pytest.approx(10.0)
    assert p.height == pytest.approx(10.0)


# ── Rotation ────────────────────────────────────────────────────────────────

def test_rotate_zero_is_noop():
    p = _make_piece(10)
    original = [list(pt) for pt in p.outer_path]
    p.rotate(0)
    assert p.outer_path == original


def test_rotate_180_doubles_and_returns_same_bbox():
    p = _make_piece(10)
    w_before = p.bbox_width
    h_before = p.bbox_height
    p.rotate(180)
    assert p.rotation == 180
    assert p.bbox_width == pytest.approx(w_before, abs=1e-6)
    assert p.bbox_height == pytest.approx(h_before, abs=1e-6)


def test_rotate_90_swaps_bbox_dimensions():
    p = _make_piece(6)
    # Make a non-square rectangle so width != height
    p2 = Piece([[0, 0], [6, 0], [6, 3], [0, 3]], id="rect")
    p2.update_bbox()
    w_before, h_before = p2.bbox_width, p2.bbox_height
    p2.rotate(90)
    assert p2.bbox_width == pytest.approx(h_before, abs=1e-6)
    assert p2.bbox_height == pytest.approx(w_before, abs=1e-6)


def test_rotation_accumulates():
    p = _make_piece(10)
    p.rotate(90)
    p.rotate(90)
    assert p.rotation == 180


def test_rotation_wraps_at_360():
    p = _make_piece(10)
    p.rotate(180)
    p.rotate(180)
    assert p.rotation == 0


# ── Translation ─────────────────────────────────────────────────────────────

def test_translate_moves_points():
    p = _make_piece(10)
    p.translate(5, 3)
    assert p.translation == pytest.approx((5, 3))


def test_translate_accumulates():
    p = _make_piece(10)
    p.translate(3, 0)
    p.translate(0, 4)
    assert p.translation == pytest.approx((3, 4))


# ── Seam allowance ──────────────────────────────────────────────────────────

def test_add_seam_allowance_expands_bbox():
    p = _make_piece(10)
    p.add_seam_allowance(1.0)
    assert p.bbox_width > 10.0
    assert p.bbox_height > 10.0


def test_add_seam_allowance_preserves_inner_path():
    p = _make_piece(10)
    inner_before = [list(pt) for pt in p.inner_path]
    p.add_seam_allowance(1.0)
    assert p.inner_path == inner_before
