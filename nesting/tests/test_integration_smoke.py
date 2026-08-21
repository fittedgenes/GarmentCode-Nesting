"""Integration smoke test: load a pattern, run RandomSearch, verify layout validity."""
import copy
import pytest
from pathlib import Path
from shapely.geometry import Polygon

import nesting.config as config
from nesting.data.path_extractor import PatternPathExtractor
from nesting.core.layout import Container, Piece
from nesting.search.random_search import RandomSearch

PATTERN_FILE = (
    Path(__file__).resolve().parents[3]
    / "nesting-assets"
    / "default_pattern.json"
)

pytestmark = pytest.mark.skipif(
    not PATTERN_FILE.exists(),
    reason=f"Pattern file not found: {PATTERN_FILE}",
)

CONTAINER_W = 200.0
CONTAINER_H = 140.0


@pytest.fixture(autouse=True)
def restore_config():
    saved = copy.deepcopy(config.ACTIVE)
    saved_sys = copy.deepcopy(config.SYSTEM)
    config.load_config(
        container_width_cm=CONTAINER_W,
        container_height_cm=CONTAINER_H,
        seam_allowance_cm=0.001,
        allowed_rotations=[0, 180],
        selected_decoder="NFP",
        selected_fitness_metric="bb_with_rest_length",
    )
    yield
    config.ACTIVE.__dict__.update(saved.__dict__)
    config.SYSTEM.__dict__.update(saved_sys.__dict__)


@pytest.fixture
def pieces() -> list[Piece]:
    extractor = PatternPathExtractor(str(PATTERN_FILE))
    all_pieces = extractor.get_all_panel_pieces(samples_per_edge=5)
    return list(all_pieces.values())


@pytest.fixture
def container() -> Container:
    return Container(CONTAINER_W, CONTAINER_H)


def test_random_search_produces_valid_layout(pieces, container):
    rs = RandomSearch(
        pieces,
        container,
        num_samples=10,
        verbose=False,
        seed=42,
    )
    rs.run()

    assert rs.best_fitness > float("-inf"), "RandomSearch found no valid layout"
    assert len(rs.best_state) > 0, "Best state is empty"

    # All placed pieces must be within the container bounds (with tolerance)
    tol = 1e-3
    for piece in rs.best_state:
        xs = [pt[0] for pt in piece.outer_path]
        ys = [pt[1] for pt in piece.outer_path]
        assert min(xs) >= -tol, f"Piece {piece.id} extends left of container"
        assert min(ys) >= -tol, f"Piece {piece.id} extends above container"
        assert max(xs) <= CONTAINER_W + tol, f"Piece {piece.id} extends right of container"
        assert max(ys) <= CONTAINER_H + tol, f"Piece {piece.id} extends below container"
