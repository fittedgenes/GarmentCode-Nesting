"""Splitting a panel must never cut one of its darts in half."""
import numpy as np
import pytest
import yaml
from shapely.geometry import LineString
from shapely.ops import split as shapely_split

from assets.bodies.body_params import BodyParameters
from assets.garment_programs import split_utils
from assets.garment_programs.meta_garment import MetaGarment

BODICE_PANELS = ['right_ftorso', 'left_ftorso', 'right_btorso', 'left_btorso']
PANT_PANELS = ['pant_f_r', 'pant_f_l', 'pant_b_r', 'pant_b_l']
PROPORTIONS = [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7]


@pytest.fixture(scope='module')
def garment():
    """A fitted shirt over pants: darts on every bodice and pant panel."""
    body = BodyParameters('./assets/bodies/mean_all.yaml')
    with open('./assets/design_params/default.yaml', 'r', encoding='utf-8') as f:
        design = yaml.safe_load(f)['design']
    design['meta']['upper']['v'] = 'FittedShirt'
    design['meta']['bottom']['v'] = 'Pants'
    design['meta']['wb']['v'] = None

    # split() leaves the panel it is called on untouched, so one garment is enough
    return MetaGarment('test_splits', body, design)


def _area(panel):
    return split_utils.panel_polygon(panel).area


@pytest.mark.parametrize('name', BODICE_PANELS + PANT_PANELS)
@pytest.mark.parametrize('proportion', PROPORTIONS)
def test_split_gives_two_valid_pieces(garment, name, proportion):
    panel = garment.get_panel_by_name(name)

    left, right = panel.split(proportion)

    polys = [split_utils.panel_polygon(p) for p in (left, right)]
    for poly in polys:
        assert poly is not None and poly.is_valid, f'{name} @ {proportion}: invalid piece'
        assert poly.area > 1., f'{name} @ {proportion}: degenerate piece'

    original = _area(panel)
    assert sum(p.area for p in polys) == pytest.approx(original, rel=1e-6), \
        f'{name} @ {proportion}: fabric lost or gained'


@pytest.mark.parametrize('name', BODICE_PANELS + PANT_PANELS)
def test_resolved_cut_never_crosses_a_dart(garment, name):
    """Whatever is asked for, the cut ends up clear of every dart leg."""
    panel = garment.get_panel_by_name(name)
    darts = split_utils.find_darts(panel)
    if not darts:
        pytest.skip(f'{name} has no darts')

    x_min, _, x_max, _ = panel.get_bounds()
    width = x_max - x_min
    for x_req in np.linspace(x_min, x_max, 101):
        x_cut, _ = split_utils.resolve_split_x(
            darts, float(x_req), max(1e-9, width * 1e-9), max(1e-6, width * 1e-6))
        assert x_cut is not None, f'{name}: no dart-free cut found for x={x_req}'
        for dart in darts:
            assert not split_utils.dart_is_cut(dart, x_cut), \
                f'{name}: cut at {x_cut} runs through the dart at {dart.tip}'


def test_bodice_front_has_a_side_dart(garment):
    """The bust dart opens on the side seam, so no cut can pass through it."""
    panel = garment.get_panel_by_name('right_ftorso')
    darts = split_utils.find_darts(panel)

    side_darts = [d for d in darts if split_utils.dart_is_pinched(d, float(d.tip[0]))]
    assert len(side_darts) == 1, 'expected exactly one bust dart on the bodice front'
    assert len(darts) == 2, 'expected a waist dart next to the bust dart'


def test_bust_dart_is_closed_into_the_seam(garment):
    """Cutting through the bust dart tip pinches the side of the panel in two.

    Both lobes have to come back as a single piece, with the dart closed and the
    fabric all still there -- see split_utils.absorb_dart_split().
    """
    panel = garment.get_panel_by_name('right_ftorso')
    dart = next(d for d in split_utils.find_darts(panel)
                if split_utils.dart_is_pinched(d, float(d.tip[0])))

    # The plain cut through the tip leaves the side of the panel in two lobes
    poly = split_utils.panel_polygon(panel)
    x = float(dart.tip[0])
    _, miny, _, maxy = poly.bounds
    naive = [g for g in shapely_split(poly, LineString([(x, miny - 1.), (x, maxy + 1.)])).geoms
             if g.geom_type == 'Polygon' and g.area > 1e-7]
    assert len(naive) == 3, 'expected the cut through the tip to pinch the panel'

    pieces = split_utils.absorb_dart_split(panel, dart)
    assert pieces is not None, 'the dart was not closed into the seam'

    polys = [split_utils.panel_polygon(p) for p in pieces]
    assert all(p is not None and p.is_valid for p in polys)
    assert len(polys) == 2, 'the two lobes did not come back as one piece'
    assert sum(p.area for p in polys) == pytest.approx(poly.area, rel=1e-6)

    # The side piece is the two lobes joined, and it no longer carries the notch
    lobes = sorted(g.area for g in naive)[:2]
    side = max(polys, key=lambda p: abs(p.centroid.x - poly.centroid.x))
    assert side.area == pytest.approx(sum(lobes), rel=1e-6)


def test_pant_front_panel_splits_like_the_back(garment):
    """Front pant panels used to fall back on the plain split, darts and all."""
    for tag in ('pant_f_r', 'pant_f_l'):
        panel = garment.get_panel_by_name(tag)
        left, right = panel.split(0.4)
        assert split_utils.panel_polygon(left).area > 1.
        assert split_utils.panel_polygon(right).area > 1.
