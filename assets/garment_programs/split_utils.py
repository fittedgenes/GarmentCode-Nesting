# split_utils.py
"""
Utility functions for per-panel splits
"""
from typing import NamedTuple, Optional
import itertools
import numpy as np


from typing import Iterable

def collect_edges_by_label(panel, labels: Iterable[str] = (), prefixes: Iterable[str] = ("")):
    """
    Collect edges from a panel whose semantic labels match any of the given labels or start with any of the given prefixes.

    Args:
        panel: The panel object containing edges with semantic labels.
        labels: An iterable of exact label strings to match.
        prefixes: An iterable of string prefixes; any label starting with one of these will match.

    Returns:
        List of edges matching the criteria.
    """
    labels = set(labels)
    prefixes = tuple(prefixes)
    return [
        e for e in panel.edges
        if any(label in e.semantic_labels for label in labels)
        or any(any(lbl.startswith(prefix) for prefix in prefixes) for lbl in e.semantic_labels)
    ]


def dart_number(label: str) -> Optional[str]:
    """
    Extract the dart number from a label string of the form 'dart_X'.

    Args:
        label: The label string (e.g., 'dart_1', 'dart_2_left').

    Returns:
        The dart number as a string if present, otherwise None.
    """
    parts = label.split("_")
    return parts[1] if len(parts) >= 2 and parts[1].isdigit() else None


def cut_number(label: str) -> Optional[str]:
    """
    Extract the cut number from a label string of the form 'cut_X'.

    Args:
        label: The label string (e.g., 'cut_1', 'cut_2_left').

    Returns:
        The cut number as a string if present, otherwise None.
    """
    parts = label.split("_")
    return parts[1] if len(parts) >= 2 and parts[1].isdigit() else None


def find_dart_tips(top_edges, dart_nums):
    """
    Find the tip points for each dart number among the given edges.

    Args:
        top_edges: List of edges to search for dart tips.
        dart_nums: Iterable of dart numbers to look for.

    Returns:
        Dictionary mapping dart number to its tip point (coordinate tuple).
    """
    tips = {}
    for num in sorted(dart_nums):
        dart_edges = [e for e in top_edges if any(lbl.startswith(f"dart_{num}") for lbl in e.semantic_labels)]
        pt = None
        for e1, e2 in itertools.combinations(dart_edges, 2):
            for a in (e1.start, e1.end):
                for b in (e2.start, e2.end):
                    if np.allclose(a, b, atol=1e-6):
                        pt = a
                        break
                if pt is not None:
                    break
            if pt is not None:
                break
        if pt is None:
            points = [p for de in dart_edges for p in (de.start, de.end)]
            if points:
                pt = min(points, key=lambda p: p[1])
        if pt is not None:
            tips[num] = pt
    return tips


def find_cut_tips(bottom_edges, cut_nums):
    """
    Find the tip points for each cut number among the given edges.
    Cuts are similar to darts but typically found on bottom edges.

    Args:
        bottom_edges: List of edges to search for cut tips.
        cut_nums: Iterable of cut numbers to look for.

    Returns:
        Dictionary mapping cut number to its tip point (coordinate tuple).
    """
    tips = {}
    for num in sorted(cut_nums):
        cut_edges = [e for e in bottom_edges if any(lbl.startswith(f"cut_{num}") for lbl in e.semantic_labels)]
        pt = None
        for e1, e2 in itertools.combinations(cut_edges, 2):
            for a in (e1.start, e1.end):
                for b in (e2.start, e2.end):
                    if np.allclose(a, b, atol=1e-6):
                        pt = a
                        break
                if pt is not None:
                    break
            if pt is not None:
                break
        if pt is None:
            points = [p for ce in cut_edges for p in (ce.start, ce.end)]
            if points:
                pt = max(points, key=lambda p: p[1])  # Cut tips are typically at the highest point (closest to waist)
        if pt is not None:
            tips[num] = pt
    return tips


def split_point(top_edges, proportion, dart_tips = None, bottom_edges=None, cut_tips=None):
    """
    Find the split point along a set of edges, accounting for darts if present.
    This function calculates the split point based on the total length of the edges and the specified proportion.

    Args:
        top_edges: List of edges to split along.
        proportion: Proportion (0-1) along the total edge length to split.
        dart_tips: Dictionary of dart number to tip point.
        bottom_edges: List of bottom edges to check for cuts (optional).
        cut_tips: Dictionary of cut number to tip point (optional).

    Returns:
        The coordinate tuple of the split point, or None if not found.
    """
    lengths = [e.length() for e in top_edges]
    total = sum(lengths)
    if not total:
        return None, None

    target = proportion * total
    cur = 0
    for e, l in zip(top_edges, lengths):
        if cur <= target < cur + l:
            local_prop = (target - cur) / l
            if any("dart_" in lbl for lbl in e.semantic_labels):
                # NOTE: semantic_labels is a set and holds 'dart_left'/'dart_right'
                # next to the numbered label, so it is sorted first -- picking
                # whichever label came out of the set first used to land on a
                # different dart from one run to the next
                dnum = next((n for n in (dart_number(lbl) for lbl in sorted(e.semantic_labels))
                             if n is not None), None)
                if dnum and dart_tips and dnum in dart_tips:
                    return dart_tips[dnum], e
                if dart_tips:
                    # Unnumbered dart: its tip is the endpoint the two legs share
                    own = [tip for tip in dart_tips.values()
                           if np.allclose(tip, e.start, atol=1e-6)
                           or np.allclose(tip, e.end, atol=1e-6)]
                    if own:
                        return own[0], e
                return e.point_at(local_prop), e
            point = e.point_at(local_prop)
            
            # Check if we should snap to a cut tip instead
            if cut_tips and bottom_edges:
                prox = total * 0.05  # 5% proximity threshold
                for cut_pt in cut_tips.values():
                    if abs(point[0] - cut_pt[0]) < prox:  # Check x-coordinate proximity
                        return cut_pt, e
                        
            return point, e
        cur += l
    return None, None


# ---------------------------------------------------------------------------
# Dart-aware panel splitting
# ---------------------------------------------------------------------------
# A panel is split by a vertical cut. Where that cut lands w.r.t. the panel's
# darts decides what has to happen:
#   * clear of every dart          -> plain cut, nothing to do
#   * through a dart's legs        -> each piece would be left with half a dart,
#                                     so the cut is snapped onto the dart tip
#   * through a dart's tip, notch
#     straddling the cut (waist
#     darts, pant top darts)       -> the dart becomes part of the new seam for
#                                     free: one leg per piece
#   * through a dart's tip, notch
#     entirely on one side (the
#     bodice bust dart)            -> the cut alone would pinch that side into
#                                     two lobes joined at the tip only, so the
#                                     dart is closed into the seam instead
#                                     (see absorb_dart_split)

class Dart(NamedTuple):
    """A triangular dart: two legs meeting at `tip`, opening at `ends`."""
    tip: np.ndarray
    ends: tuple
    edges: tuple


def _close(a, b, tol):
    return np.allclose(np.asarray(a, dtype=float), np.asarray(b, dtype=float), atol=tol)


def _shared_point(e1, e2, tol):
    """The endpoint the two edges have in common, if any."""
    for a in (e1.start, e1.end):
        for b in (e2.start, e2.end):
            if _close(a, b, tol):
                return np.asarray(a, dtype=float)
    return None


def find_darts(panel, tol=1e-6):
    """Collect the darts of a panel as (tip, open ends) pairs.

    Uses the 'dart' semantic label that Panel.add_dart() puts on both legs of
    every dart, so this works for any panel regardless of the extra numbered
    labels some garments add on top of it (e.g. 'dart_1' in PantPanel).
    """
    legs = [e for e in panel.edges if 'dart' in e.semantic_labels]
    darts, used = [], set()
    for i, e1 in enumerate(legs):
        if i in used:
            continue
        for j in range(i + 1, len(legs)):
            if j in used:
                continue
            tip = _shared_point(e1, e2 := legs[j], tol)
            if tip is None:
                continue
            ends = tuple(
                np.asarray(e.end if _close(e.start, tip, tol) else e.start, dtype=float)
                for e in (e1, e2)
            )
            darts.append(Dart(tip=tip, ends=ends, edges=(e1, e2)))
            used.update((i, j))
            break
    return darts


def dart_is_cut(dart, x, tol=1e-9):
    """True if a vertical cut at `x` runs through one of the dart's legs."""
    return any((dart.tip[0] - x) * (end[0] - x) < -tol for end in dart.ends)


def dart_is_pinched(dart, x, tol=1e-9):
    """True if the whole dart notch sits on one side of a cut through its tip.

    That is the case for darts opening on a side edge (the bodice bust dart):
    cutting through the tip leaves the side of the panel connected through that
    single point only.
    """
    return (dart.ends[0][0] - x) * (dart.ends[1][0] - x) > tol


def resolve_split_x(darts, x, tol=1e-9, snap_tol=1e-6):
    """Move a vertical cut off any dart legs it would run through.

    Returns (x, dart_to_absorb), where `dart_to_absorb` is set when the resolved
    cut leaves a whole notch on one side and the dart therefore has to be closed
    into the seam. Returns (None, None) if no dart-free cut could be found.
    """
    for _ in range(len(darts) + 1):
        crossed = [d for d in darts if dart_is_cut(d, x, tol)]
        if not crossed:
            break
        # Snap onto the tip of the dart we are cutting through
        x = float(min(crossed, key=lambda d: abs(d.tip[0] - x)).tip[0])
    else:
        return None, None

    pinching = [d for d in darts
                if abs(d.tip[0] - x) <= snap_tol and dart_is_pinched(d, x, tol)]
    return x, (pinching[0] if pinching else None)


def panel_polygon(panel):
    """The panel outline as a Shapely polygon (curvature is linearized away)."""
    import pygarment as pyg
    from shapely.geometry import Polygon
    from nesting.core.utils import clean_polygon_coordinates

    lin_edges = pyg.EdgeSequence([e.linearize() for e in panel.edges])
    coords = [(float(v[0]), float(v[1])) for v in lin_edges.verts()]
    poly = Polygon(clean_polygon_coordinates(coords))
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly if (not poly.is_empty and poly.geom_type == 'Polygon') else None


def absorb_dart_split(panel, dart, epsilon=1e-7):
    """Cut through a side dart's tip and close the dart into the new seam.

    A side dart opens on a side edge and points inwards, so a vertical cut
    through its tip leaves the whole notch on one side, pinching that side into
    an upper and a lower lobe joined at the tip alone. Rotating the lobe that
    carries one leg about the tip brings the two legs together: the notch
    closes, and the shaping it provided is taken over by the bend the rotation
    puts into the new seam -- the princess seam construction.

    dart_shape() builds a symmetric V and a rotation preserves lengths, so both
    sides of the new seam keep the same total length and still sew together.
    Fabric area is untouched as well: neither lobe changes size, the notch was
    never part of the panel to begin with.

    Returns (left_panel, right_panel), or None when the construction fails.
    """
    from shapely.geometry import LineString, Point
    from shapely.ops import split as shapely_split, unary_union
    from shapely import affinity

    poly = panel_polygon(panel)
    if poly is None:
        return None

    tip = np.asarray(dart.tip, dtype=float)
    x = float(tip[0])
    minx, miny, maxx, maxy = poly.bounds
    knife = LineString([(x, miny - 1.), (x, maxy + 1.)])

    parts = [g for g in shapely_split(poly, knife).geoms
             if g.geom_type == 'Polygon' and g.area > epsilon]

    dart_side = np.sign(dart.ends[0][0] - x)   # the notch is fully on this side
    lobes = [g for g in parts if np.sign(g.centroid.x - x) == dart_side]
    rest = [g for g in parts if np.sign(g.centroid.x - x) != dart_side]
    if len(lobes) != 2 or not rest:
        return None   # the cut did not pinch the panel the way we expect

    p1, p2 = (np.asarray(p, dtype=float) for p in dart.ends)
    holds_first = [g for g in lobes if g.boundary.distance(Point(p1[0], p1[1])) < 1e-6]
    if len(holds_first) != 1:
        return None
    lobe1 = holds_first[0]
    lobe2 = lobes[0] if lobes[1] is lobe1 else lobes[1]

    # Rotate the lobe holding the first leg until that leg lands on the second one
    v1, v2 = p1 - tip, p2 - tip
    angle = np.degrees(np.arctan2(v1[0] * v2[1] - v1[1] * v2[0], np.dot(v1, v2)))
    rotated = affinity.rotate(lobe1, angle, origin=(tip[0], tip[1]))
    # The rotation is exact in theory but not in floating point, and a leg that
    # misses its counterpart by 1e-16 leaves the two lobes as separate polygons
    rotated = snap_to(rotated, (tip, p2), tol=max(1e-9, np.linalg.norm(v2) * 1e-9))

    merged = unary_union([rotated, lobe2])
    if merged.geom_type != 'Polygon':
        # Last resort: close whatever hairline gap is left along the sewn legs
        snap = max(1e-9, (maxx - minx) * 1e-7)
        merged = merged.buffer(snap).buffer(-snap)
    if merged.geom_type != 'Polygon' or list(merged.interiors):
        return None

    other = rest[0] if len(rest) == 1 else unary_union(rest)
    if other.geom_type != 'Polygon':
        return None

    # Closing a dart moves fabric around, it never adds or removes any
    if abs(poly.area - (merged.area + other.area)) > max(1e-6, poly.area * 1e-6):
        return None

    left, right = (merged, other) if merged.centroid.x < other.centroid.x else (other, merged)
    return (
        panel.panel_from_coords(piece_coords(left), 'left'),
        panel.panel_from_coords(piece_coords(right), 'right'),
    )


def snap_to(poly, points, tol):
    """Pull the polygon's vertices onto `points` where they all but coincide."""
    from shapely.geometry import Polygon

    targets = [np.asarray(pt, dtype=float) for pt in points]
    coords = []
    for c in poly.exterior.coords:
        v = np.asarray(c, dtype=float)
        near = [t for t in targets if np.linalg.norm(v - t) <= tol]
        coords.append(tuple(near[0]) if near else c)
    return Polygon(coords)


def piece_coords(poly, tol=1e-3):
    """Outline of a split piece, ready to be turned back into edges.

    Closing the dart leaves the two sewn legs on top of each other, which shows
    up in the union as collinear and all but coincident vertices. Edges cannot
    be built from those (Edge asserts a start and end that differ), so they are
    dropped here.
    """
    ring = list(poly.simplify(0).exterior.coords)[:-1]
    coords = []
    for pt in ring:
        if not coords or max(abs(pt[0] - coords[-1][0]), abs(pt[1] - coords[-1][1])) > tol:
            coords.append(pt)
    if (len(coords) > 2
            and max(abs(coords[0][0] - coords[-1][0]), abs(coords[0][1] - coords[-1][1])) <= tol):
        coords.pop()
    return coords


def interface_chain(panel, interface_name):
    """The edges of one of the panel's interfaces, as a list to measure along.

    Interfaces skip the dart legs cut into them, which is what we want here: a
    dart is about as deep as the panel is tall, so walking its legs would spend
    most of a [0, 1] proportion inside the darts and collapse nearly every split
    onto a dart tip. Along the interface alone, the proportion stays a position
    on the actual waistline.
    """
    interfaces = getattr(panel, 'interfaces', None)
    if not isinstance(interfaces, dict):
        return None
    edges = getattr(interfaces.get(interface_name), 'edges', None)
    return list(edges) if edges else None


def dart_aware_split(panel, proportion=0.5, chain=None, dart_tips=None):
    """Split a panel in two without cutting any of its darts in half.

    `proportion` is measured along `chain` -- the panel boundary the darts open
    on, e.g. the pant top or the bodice waistline -- and along the panel's
    bounding box when no chain is given. The cut is then moved onto a dart tip
    if it would otherwise run through a dart, and side darts are closed into the
    new seam.
    """
    from pygarment.garmentcode.panel import Panel

    x_min, _, x_max, _ = panel.get_bounds()
    width = x_max - x_min
    if width <= 0:
        return Panel.split(panel, proportion)

    x = None
    if chain:
        point, _ = split_point(chain, proportion, dart_tips)
        if point is not None:
            x = float(point[0])
    if x is None:
        x = x_min + proportion * width

    darts = find_darts(panel)
    tol = max(1e-9, width * 1e-9)
    x_cut, to_absorb = resolve_split_x(darts, x, tol, snap_tol=max(1e-6, width * 1e-6)) \
        if darts else (x, None)

    if x_cut is None:
        # Every vertical cut runs through a dart -- take the plain cut and let
        # the pieces carry half a dart each rather than failing the split
        print(f'{panel.name}::WARNING::No dart-free split found, cutting through a dart')
        return Panel.split(panel, proportion)

    if to_absorb is not None:
        pieces = absorb_dart_split(panel, to_absorb)
        if pieces is not None:
            return pieces
        print(f'{panel.name}::WARNING::Could not close the dart into the split seam')

    # NOTE: Panel.split() is called explicitly (rather than through the panel)
    # since this function implements the panels' own split()
    return Panel.split(panel, (x_cut - x_min) / width)
