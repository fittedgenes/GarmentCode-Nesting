from collections import OrderedDict
from enum import Enum
import random
from typing import Literal, List, Optional, Tuple, Union

import numpy as np
from scipy.spatial import Delaunay
from shapely.geometry import MultiLineString, MultiPoint, MultiPolygon, Point, Polygon
from shapely.ops import polygonize, unary_union

from nesting.core.layout import Layout, Container, Piece
import nesting.config as config
from nesting.core import utils


# ── SIMPLE SORTING FUNCTIONS ──────────────────────────────────────────────────

def sort_pieces_by_bbox_area(pieces: List[Piece], reverse: bool = True) -> List[Piece]:
    """Sort pieces by bounding box area"""
    return sorted(pieces, key=lambda p: p.bbox_area, reverse=reverse)

def sort_pieces_by_area(pieces: List[Piece], reverse: bool = True) -> List[Piece]:
    """Sort pieces by actual polygon area"""
    return sorted(pieces, key=lambda p: utils.polygon_area(p.get_outer_path()), reverse=reverse)

def sort_pieces_by_length(pieces: List[Piece], reverse: bool = True) -> List[Piece]:
    """Sort pieces by width"""
    return sorted(pieces, key=lambda p: p.width, reverse=reverse)

def get_piece_order_by_criteria(layout: Layout, criteria: str, reverse: bool = True) -> List[str]:
    """Get piece IDs sorted by criteria"""
    pieces = list(layout.order.values())
    
    if criteria == 'bbox_area':
        sorted_pieces = sort_pieces_by_bbox_area(pieces, reverse)
    elif criteria == 'area':
        sorted_pieces = sort_pieces_by_area(pieces, reverse)
    elif criteria == 'length':
        sorted_pieces = sort_pieces_by_length(pieces, reverse)
    else:
        raise ValueError(f"Unknown criteria: {criteria}")
    
    return [piece.id for piece in sorted_pieces]


class PlacementMode(Enum):
    """Placement mode for selecting the best position from NFP candidates."""
    BOTTOM_LEFT = "bottom_left"          # Traditional bottom-left fill
    MAX_OVERLAP = "max_overlap"          # Maximize overlap with existing pieces
    MIN_BBOX_LENGTH = "min_bbox_length"  # Minimize bounding box length
    MIN_BBOX_AREA = "min_bbox_area"      # Minimize bounding box area


DECODER_REGISTRY: dict[str, type] = {}

def register_decoder(name: str):
    def deco(cls):
        DECODER_REGISTRY[name] = cls
        return cls
    return deco


class PlacementEngine:
    """
    Base class for all placement strategies.
    Provides:
      - _fits(...) container‐bounds/overlap testing
      - anchor/gravitate for BL logic
      - unified alpha_shape(...) to compute concave hull
      - _update_exterior_contour(...) that reuses alpha_shape
      - usage_BB(), rest_length(), layout_is_valid() for metrics
    """

    def __init__(self, layout: Layout, container: Container, gravitate_once: bool = False, **kwargs):
        self.layout = layout
        self.container = container
        self.placed: List[Piece] = []
        self.gravitate_once = gravitate_once
        # Will hold either a Polygon or a MultiPolygon representing
        # the “exterior contour” of all placed pieces
        self._exterior_contour: Optional[Union[Polygon, MultiPolygon]] = None

        # Last computed concave hull (for utilization, via alpha_shape)
        self._last_hull: Optional[Polygon] = None

    @property
    def last_hull(self) -> Optional[Polygon]:
        """Return the last computed concave hull, or None if not computed yet."""
        return self._last_hull

    # ── EXISTING UTILITY METHODS (unchanged) ──────────────────────────────────────

    def _fits(self, piece: Piece, dx: float, dy: float) -> bool:
        """Return True if piece at ``(dx, dy)`` lies inside container and does not overlap."""

        # ---- bounding box check against container ----
        cand_min_x = piece.min_x + dx
        cand_max_x = piece.max_x + dx
        cand_min_y = piece.min_y + dy
        cand_max_y = piece.max_y + dy

        if (
            cand_min_x < 0 or cand_max_x > self.container.width
            or cand_min_y < 0 or cand_max_y > self.container.height
        ):
            return False

        poly = utils._translate_polygon(piece.get_outer_path(), dx, dy)

        # ---- overlap checks ----
        for other in self.placed:
            ox, oy = other.translation

            other_min_x = other.min_x + ox
            other_max_x = other.max_x + ox
            other_min_y = other.min_y + oy
            other_max_y = other.max_y + oy

            if (
                cand_max_x <= other_min_x or cand_min_x >= other_max_x
                or cand_max_y <= other_min_y or cand_min_y >= other_max_y
            ):
                # Bounding boxes do not intersect → cannot overlap.
                continue

            other_poly = utils._translate_polygon(other.get_outer_path(), ox, oy)
            if utils.polygons_overlap(poly, other_poly):
                return False

        return True

    def anchor(self, piece: Piece) -> Tuple[float, float]:
        """Push piece against the container’s top‐right corner."""
        vertices = piece.get_outer_path()
        xs = [v[0] for v in vertices]
        min_x, max_x = min(xs), max(xs)
        start_x = self.container.width - (max_x - min_x)
        start_y = 0.0
        return start_x, start_y

    def gravitate(self, piece: Piece, x: float, y: float, step: float = config.GRAVITATE_STEP) -> Tuple[float, float]:
        """Slide piece left until jammed, then down, repeating until no movement."""
        moved = True
        while moved:
            moved = False
            while x - step >= 0 and self._fits(piece, x - step, y):
                x -= step
                moved = True
            while y + step <= self.container.height and self._fits(piece, x, y + step):
                y += step
                moved = True
        return x, y

    def BLCompact(self, compact_order: List[str]): # -> List[Tuple[float, float]]:
        """
        Given the ids of pieces in `compact_order`, shift the pieces in self.placed
        """
        for piece_id in compact_order:
            piece = next((p for p in self.placed if p.id == piece_id), None)
            if piece is None:
                raise ValueError(f"BLCompact: piece id '{piece_id}' not found in placed pieces")
            x0, y0 = piece.translation
            x_new, y_new = self.gravitate(piece, x0, y0)
            piece.translation = (x_new, y_new)

    def decode_in_order(self, piece_order: List[str]) -> list[Tuple[str, float, float, float]]:
        """
        Interface method - subclasses must implement this with their specific placement logic
        """
        raise NotImplementedError("Subclasses must implement decode_in_order")
            
    

    def _gravitate_once(self, piece: Piece, x: float, y: float, step: float = config.GRAVITATE_STEP) -> Tuple[float, float]:
        """
        “Traditional” fully-left then fully-down:
        1. From (x,y), move left in discrete steps until you can't go further.
        2. From that leftmost location, move down in discrete steps until you can’t go further.
        No iteration back to left after moving down.
        """
        # 1) Slide left as far as possible
        while x - step >= 0 and self._fits(piece, x - step, y):
            x -= step

        # 2) Slide down as far as possible
        while y + step <= self.container.height and self._fits(piece, x, y + step):
            y += step

        return x, y


    def _flatten_piece_list(self) -> List[Tuple[float, float]]:
        return [
            (x + p.translation[0], y + p.translation[1])
            for p in self.placed
            for x, y in p.get_outer_path()
        ]

    def layout_is_valid(self) -> bool:
        """
        Check if all pieces have been placed and the layout is valid.
        A valid layout means:
        1. All pieces from the original layout have been placed
        2. All placed pieces are within container bounds
        3. No pieces overlap
        """
        # Check if all pieces from the original layout have been placed
        if len(self.placed) != len(self.layout.order):
            return False
            
        # Check if all pieces fit within container and don't overlap
        n = len(self.placed)
        for i in range(n):
            pi = self.placed[i]
            poly_i = utils._translate_polygon(pi.get_outer_path(), *pi.translation)
            xs_i, ys_i = zip(*poly_i)
            if (
                min(xs_i) < 0 or max(xs_i) > self.container.width
                or min(ys_i) < 0 or max(ys_i) > self.container.height
            ):
                return False
            for j in range(i + 1, n):
                pj = self.placed[j]
                poly_j = utils._translate_polygon(pj.get_outer_path(), *pj.translation)
                if utils.polygons_overlap(poly_i, poly_j):
                    return False
        return True

    def bbox_area(self) -> float:
        """
        Calculate the utilization ratio based on the bounding box.
        Returns 0.0 if not all pieces have been placed or if the layout is invalid.
        """
        # First check if the layout is valid (includes check that all pieces are placed)
        if not self.layout_is_valid():
            return 0.0
            
        flattened = self._flatten_piece_list()
        if not flattened:
            return 0.0
        xs = [v[0] for v in flattened]
        ys = [v[1] for v in flattened]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return (max_x - min_x) * (max_y - min_y)

    def usage_BB(self) -> float:
        """
        Calculate the utilization ratio based on the bounding box.
        Returns 0.0 if not all pieces have been placed or if the layout is invalid.
        """
        bbox_area = self.bbox_area()
        total_area = sum(utils.polygon_area(p.get_outer_path()) for p in self.placed)
        ratio = total_area / bbox_area if bbox_area > 0 else 0.0
        return ratio

    def rest_length(self) -> float:
        flattened = self._flatten_piece_list()
        if not flattened:
            return self.container.width
        xs = [v[0] for v in flattened]
        return self.container.width - max(xs)
    
    def rest_height(self) -> float:
        flattened = self._flatten_piece_list()
        if not flattened:
            return self.container.height
        ys = [v[1] for v in flattened]
        return min(ys)

    # ──  α-SHAPE (CONCAVE HULL) HELPER ────────────────────────────────────

    def alpha_shape(self,
                    points: List[Tuple[float, float]],
                    *,
                    trim_ratio: float = 7.0,
                    interior_spacing: float = 5.0,
                    boundary_spacing: float = 1.0
                   ) -> Polygon:
        """
        Compute a concave hull of `points` via alpha-shape
        Stores result in self._last_hull.
        """
        interior_spacing = float(interior_spacing)
        boundary_spacing = float(boundary_spacing)

        def sample_interior(poly: Polygon) -> List[Tuple[float, float]]:
            minx, miny, maxx, maxy = poly.bounds
            xs = np.arange(minx + interior_spacing/2.0, maxx, interior_spacing)
            ys = np.arange(miny + interior_spacing/2.0, maxy, interior_spacing)
            pts = []
            for x in xs:
                for y in ys:
                    if poly.contains(Point(x, y)):
                        pts.append((float(x), float(y)))
            return pts

        def sample_boundary(poly: Polygon) -> List[Tuple[float, float]]:
            coords = list(poly.exterior.coords)
            pts = []
            for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
                edge_len = float(np.hypot(x1 - x0, y1 - y0))
                n_samples = max(int(edge_len / boundary_spacing), 1)
                for t in np.linspace(0.0, 1.0, n_samples, endpoint=False):
                    pts.append((float(x0 + t * (x1 - x0)),
                                float(y0 + t * (y1 - y0))))
            return pts

        # Build sampled point cloud over all placed pieces
        all_pts: List[Tuple[float, float]] = []
        centroids = []
        for piece in self.placed:
            raw = piece.get_outer_path()
            # Clean coordinates and translate
            translated_coords = [(x + piece.translation[0], y + piece.translation[1]) for x, y in raw]
            cleaned_coords = utils.clean_polygon_coordinates(translated_coords)
            poly = Polygon(cleaned_coords)
            
            # Only proceed if polygon is valid
            if poly.is_valid and not poly.is_empty:
                all_pts.extend(sample_boundary(poly))
                all_pts.extend(sample_interior(poly))
                centroids.append(poly.centroid.coords[0])

        pts = np.array(all_pts, dtype=float)
        if pts.shape[0] < 4:
            hull = MultiPoint(pts).convex_hull
            self._last_hull = hull
            return hull

        tri = Delaunay(pts)

        # Edge length computation for all simplices
        simplices = tri.simplices
        tri_pts = pts[simplices]  # (n, 3, 2)
        edges = np.stack([
            tri_pts[:, 0] - tri_pts[:, 1],
            tri_pts[:, 1] - tri_pts[:, 2],
            tri_pts[:, 2] - tri_pts[:, 0],
        ], axis=1)
        edge_lengths = np.linalg.norm(edges, axis=2)

        median_len = float(np.median(edge_lengths))
        max_edge = median_len * trim_ratio

        mask = np.all(edge_lengths <= max_edge, axis=1)
        kept_simplices = simplices[mask]

        if kept_simplices.size == 0:
            hull = MultiPoint(pts).convex_hull
            self._last_hull = hull
            return hull

        # Collect unique edges from kept simplices
        edge_pairs = np.stack([
            kept_simplices[:, [0, 1]],
            kept_simplices[:, [1, 2]],
            kept_simplices[:, [2, 0]],
        ], axis=1).reshape(-1, 2)
        edge_pairs = np.sort(edge_pairs, axis=1)
        kept = {tuple(e) for e in np.unique(edge_pairs, axis=0)}
        if not kept:
            hull = MultiPoint(pts).convex_hull
            self._last_hull = hull
            return hull

        mls = MultiLineString([ (tuple(pts[i]), tuple(pts[j])) for i, j in kept ])
        regions = list(polygonize(unary_union(mls)))
        if not regions:
            hull = MultiPoint(pts).convex_hull
            self._last_hull = hull
            return hull

        merged = unary_union(regions)
        if hasattr(merged, "geoms"):
            hull = max(merged.geoms, key=lambda p: p.area)
        else:
            hull = merged

        missing = [c for c in centroids if not hull.contains(Point(c))]
        if missing:
            full_hull = MultiPoint(pts).convex_hull
            hull = unary_union([hull, full_hull])

        if config.SNAP:
            w, h = self.container.width, self.container.height
            tol_x = config.SNAP_TOLERANCE * w
            tol_y = config.SNAP_TOLERANCE * h
            coords = list(hull.exterior.coords)
            snapped: List[Tuple[float, float]] = []
            n = len(coords)

            def is_on_horiz(pt: Tuple[float, float]) -> bool:
                return abs(pt[1]) < tol_y or abs(pt[1] - h) < tol_y

            def is_on_vert(pt: Tuple[float, float]) -> bool:
                return abs(pt[0]) < tol_x or abs(pt[0] - w) < tol_x

            for i, (x, y) in enumerate(coords):
                prev = coords[i - 1]
                nxt = coords[(i + 1) % n]

                if abs(x) < tol_x or (abs(prev[0]) < tol_x and abs(nxt[0]) < tol_x):
                    x = 0.0
                elif abs(x - w) < tol_x or (abs(prev[0] - w) < tol_x and abs(nxt[0] - w) < tol_x):
                    x = w
                # snap if adjacent to vertical boundary segment
                elif is_on_vert(prev) and is_on_vert(nxt):
                    x = 0.0 if abs(x) < abs(x - w) else w

                if abs(y) < tol_y or (abs(prev[1]) < tol_y and abs(nxt[1]) < tol_y):
                    y = 0.0
                elif abs(y - h) < tol_y or (abs(prev[1] - h) < tol_y and abs(nxt[1] - h) < tol_y):
                    y = h
                # snap if adjacent to horizontal boundary segment
                elif is_on_horiz(prev) and is_on_horiz(nxt):
                    y = 0.0 if abs(y) < abs(y - h) else h

                curr = (x, y)
                snapped.append(curr)
                x2, y2 = coords[(i + 1) % n]
                if abs(x2) < tol_x:
                    x2 = 0.0
                elif abs(x2 - w) < tol_x:
                    x2 = w
                if abs(y2) < tol_y:
                    y2 = 0.0
                elif abs(y2 - h) < tol_y:
                    y2 = h
                nxt_snapped = (x2, y2)

                if (
                    (is_on_horiz(curr) and is_on_vert(nxt_snapped)) or
                    (is_on_vert(curr) and is_on_horiz(nxt_snapped))
                ):
                    corner = (
                        curr[0] if is_on_vert(curr) else nxt_snapped[0],
                        curr[1] if is_on_horiz(curr) else nxt_snapped[1]
                    )
                    if corner not in snapped:
                        snapped.append(corner)

            # Clean the snapped coordinates before creating the polygon
            cleaned_snapped = utils.clean_polygon_coordinates(snapped)
            hull = Polygon(cleaned_snapped)

        # Check if the resulting hull is valid before returning it
        if not hull.is_valid:
            print("[alpha_shape] Generated an invalid geometry - this chromosome will be discarded")
            # Create an empty polygon as fallback
            empty_hull = Polygon()
            self._last_hull = empty_hull
            return empty_hull
    
        self._last_hull = hull
        return hull

    def _update_exterior_contour(self, new_piece: Piece) -> None:
        """
        Merge `new_piece` into the running exterior contour.  
        If config.PRESERVE_HOLES is True, keep the full union (Polygon or MultiPolygon).
        Otherwise, build one concave α‐shape over all exterior vertices of the union.
        """
        raw = new_piece.get_outer_path()
        x0, y0 = new_piece.translation
        shifted = [(x + x0, y + y0) for x, y in raw]
        
        # Clean coordinates before creating polygon
        cleaned_shifted = utils.clean_polygon_coordinates(shifted)
        piece_poly = Polygon(cleaned_shifted)

        if self._exterior_contour is None:
            self._exterior_contour = piece_poly
            return

        try:
            merged = self._exterior_contour.union(piece_poly)
        except Exception:
            # Near-coincident edges can cause GEOS TopologyException; buffer(0) cleans them
            merged = self._exterior_contour.buffer(0).union(piece_poly.buffer(0))
        self._exterior_contour = merged
        return

    def concave_hull_utilization(self) -> float:
        """
        Calculate the utilization ratio based on the concave hull.
        Returns 0.0 if not all pieces have been placed or if the layout is invalid.
        """
        # First check if the layout is valid (includes check that all pieces are placed)
        if not self.layout_is_valid():
            return 0.0
            
        if not self.placed:
            return 0.0

        pts = self._flatten_piece_list()
        hull = self.alpha_shape(pts,
                                trim_ratio=config.HULL_TRIM_RATIO,
                                interior_spacing=config.INTERIOR_SAMPLE_SPACING,
                                boundary_spacing=config.BOUNDARY_SAMPLE_SPACING)
        hull_area = hull.area if not hull.is_empty else 0.0
        total_area = sum(utils.polygon_area(p.get_outer_path()) for p in self.placed)
        return (total_area / hull_area) if hull_area > 0 else 0.0
    
    def concave_hull_area(self) -> float:
        """
        Calculate the area of the concave hull formed by all placed pieces.
        Returns 0.0 if not all pieces have been placed or if the layout is invalid.
        """
        # First check if the layout is valid (includes check that all pieces are placed)
        if not self.layout_is_valid():
            return 0.0
            
        if not self.placed:
            return 0.0

        pts = self._flatten_piece_list()
        hull = self.alpha_shape(pts,
                                trim_ratio=config.HULL_TRIM_RATIO,
                                interior_spacing=config.INTERIOR_SAMPLE_SPACING,
                                boundary_spacing=config.BOUNDARY_SAMPLE_SPACING)
        return hull.area if not hull.is_empty else 0.0

@register_decoder("BL")
class BottomLeftDecoder(PlacementEngine):
    def __init__(self, layout: Layout, container: Container, *, step: Optional[float] = None, **kwargs):
        super().__init__(layout, container)
        self.step = step if step is not None else config.GRAVITATE_STEP

    def decode(self) -> list[Tuple[str, float, float, float]]:
        """Place pieces using BL heuristic"""
        print("[DECODE]: decoding")
        return self.decode_in_order(list(self.layout.order.keys()))

    def decode_in_order(self, piece_order: List[str]) -> list[Tuple[str, float, float, float]]:
        """Decode pieces in specified order using BL placement"""
        print("[DECODE IN ORDER]: decoding")

        for piece_id in piece_order:
            if piece_id not in self.layout.order:
                continue
            piece = self.layout.order[piece_id]
            x0, y0 = self.anchor(piece)
            if self.gravitate_once:
                dx, dy = self._gravitate_once(piece, x0, y0, step=self.step)
            else:
                dx, dy = self.gravitate(piece, x0, y0, step=self.step)
            piece.translation = (dx, dy)
            self.placed.append(piece)
        return [(p.id, p.translation[0], p.translation[1], p.rotation) for p in self.placed]


@register_decoder("Greedy")
class GreedyBLDecoder(BottomLeftDecoder):
    """
    A Greedy BL decoder that can sort by different metrics:
      - bbox_area       (piece.min_x→piece.max_x × piece.min_y→piece.max_y)
      - hull_area       (area of convex hull of piece’s polygon)
      - aspect_ratio    (max(width/height, height/width))
    """
    def __init__(self,
                 layout: Layout,
                 container: Container,
                 *,
                 step: Optional[float] = None,
                 traditional: bool = False,
                 sort_key: Literal["bbox_area", "hull_area", "aspect_ratio"] = "bbox_area",
                 **kwargs):
        """
        :param sort_key: One of "bbox_area", "hull_area", or "aspect_ratio".
                         Determines how pieces are ordered before placement.
        """
        self.sort_key = sort_key
        # 1) Compute the metric for each piece
        metrics = {}
        for pid, piece in layout.order.items():
            if sort_key == "bbox_area":
                # piece.bbox_area is already available
                metrics[pid] = piece.bbox_area
            elif sort_key == "hull_area":
                # Use your existing utils.polygon_area(...) on the convex hull of piece.get_outer_path()
                from shapely.geometry import Polygon
                raw_path = piece.get_outer_path()
                convex_hull_coords = Polygon(raw_path).convex_hull.exterior.coords[:]  
                # convex_hull_coords is a sequence of (x, y) tuples
                metrics[pid] = utils.polygon_area(list(convex_hull_coords))
            elif sort_key == "aspect_ratio":
                w, h = piece.width, piece.height
                # Use max(w/h, h/w) so that extremely elongated shapes rank higher
                metrics[pid] = max(w / h, h / w) if (h > 0 and w > 0) else 1.0
            else:
                raise ValueError(f"Unrecognized sort_key: {sort_key}")

        # 2) Sort piece IDs in descending order of the chosen metric
        sorted_ids = sorted(metrics.keys(), key=lambda pid: metrics[pid], reverse=True)

        # 3) Rebuild layout.order as an OrderedDict in that sorted order
        sorted_pieces = [(pid, layout.order[pid]) for pid in sorted_ids]
        new_order = OrderedDict(sorted_pieces)

        # 4) Initialize the parent BL decoder with the newly ordered layout
        super().__init__(Layout(new_order), container, step=step, traditional=traditional, **kwargs)



@register_decoder("Random")
class RandomDecoder(PlacementEngine):
    def __init__(self,
                 layout: Layout,
                 container: Container,
                 *,
                 decoder: str = "BL",  # choose 'BL' or 'NFP'
                 rotations_on: bool = config.ENABLE_ROTATIONS,
                 **kwargs):
        # Shuffle piece order
        ids = list(layout.order)
        random.shuffle(ids)
        shuffled = OrderedDict((i, layout.order[i]) for i in ids)
        super().__init__(Layout(shuffled), container, **kwargs)
        self.decoder = decoder
        self.rotations_on = rotations_on

    def decode(self):
        # Apply random rotations if enabled
        if self.rotations_on:
            for p in self.layout.order.values():
                p.rotate(random.choice(config.ALLOWED_ROTATIONS))
        # Delegate to chosen decode strategy
        if self.decoder == "BL":
            dec = BottomLeftDecoder(self.layout, self.container, step=config.GRAVITATE_STEP)
        elif self.decoder == "NFP":
            dec = NFPDecoder(self.layout, self.container)
        else:
            raise ValueError(f"RandomDecoder: unsupported decoder '{self.decoder}'")
        placements = dec.decode()
        self.placed = dec.placed
        return placements


@register_decoder("NFP")
class NFPDecoder(PlacementEngine):
    """
    NFP-based placement engine with configurable placement modes.
    Supports bottom_left, max_overlap, min_bbox_length, and min_bbox_area placement strategies.
    """

    def __init__(self, layout: Layout, container: Container, *,
                 placement_mode: Union[PlacementMode, str] = PlacementMode.MIN_BBOX_AREA,
                 step=None, **kwargs):
        super().__init__(layout, container)
        self._nfp_cache = {}

        # Handle string or enum input for placement mode
        if isinstance(placement_mode, str):
            try:
                self.placement_mode = PlacementMode(placement_mode)
            except ValueError:
                raise ValueError(f"Invalid placement mode: {placement_mode}. Valid modes: {[m.value for m in PlacementMode]}")
        else:
            self.placement_mode = placement_mode

    def decode(self):
        return self.decode_in_order(list(self.layout.order.keys()))

    def decode_in_order(self, piece_order: List[str]) -> list[Tuple[str, float, float, float]]:
        """Decode pieces in specified order using NFP placement"""
        for piece_id in piece_order:
            if piece_id not in self.layout.order:
                continue
            piece = self.layout.order[piece_id]
            
            best_x, best_y = self._find_best_position(piece)
            if best_x is None:
                continue

            piece.translation = (best_x, best_y)
            self.placed.append(piece)
            self._update_exterior_contour(piece)

        return [(p.id, *p.translation, p.rotation) for p in self.placed]

    def _find_best_position(self, piece: Piece, gravitate_on: bool = config.NFP_GRAVITATE_ON) -> Tuple[Optional[float], Optional[float]]:
        """
        Place `piece` by generating NFP candidates against each exterior boundary
        ring in self._exterior_contour (Polygon or MultiPolygon).
        Score by bounding‐box overlap, return the best (x,y).
        """
        if not self.placed:
            return 0.0, self.container.height - piece.height

        contour = self._exterior_contour
        if contour is None or contour.is_empty:
            ax, ay = self.anchor(piece)
            return self.gravitate(piece, ax, ay)

        # 1) Gather every exterior ring
        rings: List[List[Tuple[float, float]]] = []
        if isinstance(contour, Polygon):
            rings.append(list(contour.exterior.coords))
        else:
            for geom in getattr(contour, "geoms", []):
                if isinstance(geom, Polygon):
                    rings.append(list(geom.exterior.coords))

        # 2) Compute all NFP candidates
        moving_path = piece.get_outer_path()
        cleaned_moving = utils.clean_polygon_coordinates(moving_path)
        all_nfp_pts: List[Tuple[float, float]] = []
        for ring_coords in rings:
            cleaned_ring = utils.clean_polygon_coordinates(ring_coords)
            pts = utils.no_fit_polygon(cleaned_ring, cleaned_moving, n_edge_samples=config.NFP_EDGE_SAMPLES)
            all_nfp_pts.extend(pts)

        # 3) Pre-compute placed vertices and bbox (shared across all candidates)
        placed_flat = self._flatten_piece_list()
        xs_placed = [v[0] for v in placed_flat]
        ys_placed = [v[1] for v in placed_flat]
        min_px, max_px = min(xs_placed), max(xs_placed)
        min_py, max_py = min(ys_placed), max(ys_placed)

        if self.placement_mode == PlacementMode.MAX_OVERLAP:
            best_score = -1.0
        elif self.placement_mode == PlacementMode.BOTTOM_LEFT:
            best_score = (float('inf'), float('inf'))
        else:
            best_score = float('inf')

        best_x = best_y = None

        # 4) Evaluate each candidate
        for x_cand, y_cand in all_nfp_pts:
            candidate_vertices = [(x + x_cand, y + y_cand) for x, y in moving_path]
            xs_cand = [v[0] for v in candidate_vertices]
            ys_cand = [v[1] for v in candidate_vertices]
            if (
                min(xs_cand) < 0 or max(xs_cand) > self.container.width
                or min(ys_cand) < 0 or max(ys_cand) > self.container.height
            ):
                continue
            if not self._fits(piece, x_cand, y_cand):
                continue

            if self.placement_mode == PlacementMode.MAX_OVERLAP:
                cand_min_x, cand_max_x = min(xs_cand), max(xs_cand)
                cand_min_y, cand_max_y = min(ys_cand), max(ys_cand)
                overlap_w = min(max_px, cand_max_x) - max(min_px, cand_min_x)
                overlap_h = min(max_py, cand_max_y) - max(min_py, cand_min_y)
                score = overlap_w * overlap_h if overlap_w > 0 and overlap_h > 0 else 0.0
                if score > best_score:
                    best_score, best_x, best_y = score, x_cand, y_cand
            elif self.placement_mode == PlacementMode.BOTTOM_LEFT:
                score = (y_cand, x_cand)
                if score < best_score:
                    best_score, best_x, best_y = score, x_cand, y_cand
            else:
                all_xs = xs_placed + xs_cand
                all_ys = ys_placed + ys_cand
                if self.placement_mode == PlacementMode.MIN_BBOX_LENGTH:
                    score = max(all_xs) - min(all_xs)
                else:  # MIN_BBOX_AREA
                    score = (max(all_xs) - min(all_xs)) * (max(all_ys) - min(all_ys))
                if score < best_score:
                    best_score, best_x, best_y = score, x_cand, y_cand

        if best_x is None or best_y is None:
            ax, ay = self.anchor(piece)
            best_x, best_y = self.gravitate(piece, ax, ay)
        elif gravitate_on:
            best_x, best_y = self.gravitate(piece, best_x, best_y)

        return best_x, best_y

    def _nfp(self, stationary: Piece, moving: Piece) -> List[Tuple[float, float]]:
        """
        Return (cached) no‐fit polygon between `stationary` and `moving`.  
        Only used if you need pairwise NFP, but in the code above we compute
        NFP against the entire contour of placed pieces instead.
        """
        key = (stationary.id, moving.id)
        if key not in self._nfp_cache:
            # Clean both polygons before calculating NFP
            cleaned_stationary = utils.clean_polygon_coordinates(stationary.get_outer_path())
            cleaned_moving = utils.clean_polygon_coordinates(moving.get_outer_path())
            
            self._nfp_cache[key] = utils.no_fit_polygon(
                cleaned_stationary,
                cleaned_moving
            )
        return self._nfp_cache[key]


@register_decoder("NFPwithRots")
class NFPwithRotsDecoder(PlacementEngine):
    """
    NFP-based placement that tries all allowed rotations of each piece and
    chooses the best (rotation, position) pair according to placement_mode.

    Behavior matches NFPDecoder except that candidate evaluation is repeated
    for each rotation in config.ALLOWED_ROTATIONS when rotations are enabled.
    """

    def __init__(self, layout: Layout, container: Container, *,
                 placement_mode: Union[PlacementMode, str] = PlacementMode.MIN_BBOX_AREA,
                 step=None, **kwargs):
        super().__init__(layout, container)
        self._nfp_cache: dict[tuple[str, str], list[tuple[float, float]]] = {}

        if isinstance(placement_mode, str):
            try:
                self.placement_mode = PlacementMode(placement_mode)
            except ValueError:
                raise ValueError(f"Invalid placement mode: {placement_mode}. Valid modes: {[m.value for m in PlacementMode]}")
        else:
            self.placement_mode = placement_mode

    def decode(self):
        return self.decode_in_order(list(self.layout.order.keys()))

    def decode_in_order(self, piece_order: List[str]) -> list[Tuple[str, float, float, float]]:
        for piece_id in piece_order:
            if piece_id not in self.layout.order:
                continue
            piece = self.layout.order[piece_id]

            best_x, best_y, best_angle = self._find_best_position_with_rotations(piece)
            if best_x is None:
                continue

            # Commit chosen rotation and placement
            piece.rotate(best_angle)
            piece.translation = (best_x, best_y)
            self.placed.append(piece)
            self._update_exterior_contour(piece)

        return [(p.id, *p.translation, p.rotation) for p in self.placed]

    def _find_best_position_with_rotations(self, piece: Piece, *,
                                            gravitate_on: bool = config.NFP_GRAVITATE_ON) -> Tuple[Optional[float], Optional[float], float]:
        """
        Like NFPDecoder._find_best_position, but evaluates every allowed rotation
        of `piece` and returns the best (x, y, angle).
        """
        allowed_angles = config.ALLOWED_ROTATIONS if config.ENABLE_ROTATIONS else [piece.rotation]
        orig_rot = piece.rotation

        # If nothing is placed yet, choose rotation that optimizes placement_mode
        if not self.placed:
            best_score = None
            best_xy = (None, None)
            best_angle = orig_rot
            for angle in allowed_angles:
                try:
                    piece.rotate(angle)
                    # Start from BL-like initial position; mirror NFP behaviour
                    x0, y0 = 0.0, self.container.height - piece.height
                    if gravitate_on:
                        x0, y0 = self.gravitate(piece, x0, y0)
                    # Score according to placement mode
                    score = self._score_with_current_rotation(piece, x0, y0)
                    if (best_score is None) or (score < best_score):
                        best_score = score
                        best_xy = (x0, y0)
                        best_angle = angle
                finally:
                    # restore for next trial
                    piece.rotate(orig_rot)
            return best_xy[0], best_xy[1], best_angle

        # Build exterior rings once (unchanged across rotations)
        contour = self._exterior_contour
        rings: List[List[Tuple[float, float]]] = []
        if isinstance(contour, Polygon):
            rings.append(list(contour.exterior.coords))
        elif contour is not None:
            for geom in getattr(contour, "geoms", []):
                if isinstance(geom, Polygon):
                    rings.append(list(geom.exterior.coords))

        # Pre-compute placed vertices once — unchanged across rotations
        placed_flat = self._flatten_piece_list()
        xs_placed = [v[0] for v in placed_flat]
        ys_placed = [v[1] for v in placed_flat]
        min_px, max_px = min(xs_placed), max(xs_placed)
        min_py, max_py = min(ys_placed), max(ys_placed)

        global_best_score = None
        global_best = (None, None, orig_rot)  # x, y, angle

        for angle in allowed_angles:
            try:
                piece.rotate(angle)
                moving_path = piece.get_outer_path()
                cleaned_moving = utils.clean_polygon_coordinates(moving_path)

                all_nfp_pts: List[Tuple[float, float]] = []
                for ring_coords in rings:
                    cleaned_ring = utils.clean_polygon_coordinates(ring_coords)
                    pts = utils.no_fit_polygon(cleaned_ring, cleaned_moving, n_edge_samples=config.NFP_EDGE_SAMPLES)
                    all_nfp_pts.extend(pts)

                local_best_score = None
                local_best_xy = (None, None)

                for x_cand, y_cand in all_nfp_pts:
                    candidate_vertices = [(x + x_cand, y + y_cand) for x, y in moving_path]
                    xs_cand = [v[0] for v in candidate_vertices]
                    ys_cand = [v[1] for v in candidate_vertices]
                    if (
                        min(xs_cand) < 0 or max(xs_cand) > self.container.width
                        or min(ys_cand) < 0 or max(ys_cand) > self.container.height
                    ):
                        continue
                    if not self._fits(piece, x_cand, y_cand):
                        continue

                    if self.placement_mode == PlacementMode.MAX_OVERLAP:
                        cand_min_x, cand_max_x = min(xs_cand), max(xs_cand)
                        cand_min_y, cand_max_y = min(ys_cand), max(ys_cand)
                        overlap_w = min(max_px, cand_max_x) - max(min_px, cand_min_x)
                        overlap_h = min(max_py, cand_max_y) - max(min_py, cand_min_y)
                        score = overlap_w * overlap_h if overlap_w > 0 and overlap_h > 0 else 0.0
                        better = (local_best_score is None) or (score > local_best_score)
                    elif self.placement_mode == PlacementMode.BOTTOM_LEFT:
                        score = (y_cand, x_cand)
                        better = (local_best_score is None) or (score < local_best_score)
                    else:
                        all_xs = xs_placed + xs_cand
                        all_ys = ys_placed + ys_cand
                        if self.placement_mode == PlacementMode.MIN_BBOX_LENGTH:
                            score = max(all_xs) - min(all_xs)
                        else:  # MIN_BBOX_AREA
                            score = (max(all_xs) - min(all_xs)) * (max(all_ys) - min(all_ys))
                        better = (local_best_score is None) or (score < local_best_score)

                    if better:
                        local_best_score = score
                        local_best_xy = (x_cand, y_cand)

                if local_best_xy[0] is not None:
                    # Normalize to "lower is better" for cross-angle comparison
                    cmp_score = -local_best_score if self.placement_mode == PlacementMode.MAX_OVERLAP else local_best_score
                    if (global_best_score is None) or (cmp_score < global_best_score):
                        global_best_score = cmp_score
                        global_best = (local_best_xy[0], local_best_xy[1], angle)
            finally:
                piece.rotate(orig_rot)

        x_best, y_best, ang_best = global_best
        if x_best is None or y_best is None:
            # Fallback: try BL gravity for each angle and choose best
            best_score = None
            best_xy = (None, None)
            best_angle = orig_rot
            for angle in allowed_angles:
                try:
                    piece.rotate(angle)
                    x0, y0 = 0.0, self.container.height - piece.height
                    if gravitate_on:
                        x0, y0 = self.gravitate(piece, x0, y0)
                    score = self._score_with_current_rotation(piece, x0, y0)
                    if (best_score is None) or (score < best_score):
                        best_score = score
                        best_xy = (x0, y0)
                        best_angle = angle
                finally:
                    piece.rotate(orig_rot)
            return best_xy[0], best_xy[1], best_angle

        if gravitate_on:
            # Polish with gravity; keep angle
            try:
                piece.rotate(ang_best)
                gx, gy = self.gravitate(piece, x_best, y_best)
                return gx, gy, ang_best
            finally:
                piece.rotate(orig_rot)
        return x_best, y_best, ang_best

    def _score_with_current_rotation(self, piece: Piece, dx: float, dy: float) -> float:
        """Scalar score at (dx, dy) consistent with placement_mode (lower = better).
        BOTTOM_LEFT uses bbox area as a scalar proxy when comparing rotations.
        """
        placed_flat = self._flatten_piece_list()
        cand_verts = [(x + dx, y + dy) for x, y in piece.get_outer_path()]
        all_verts = placed_flat + cand_verts
        xs = [v[0] for v in all_verts]
        ys = [v[1] for v in all_verts]

        if self.placement_mode == PlacementMode.MIN_BBOX_LENGTH:
            return max(xs) - min(xs)
        if self.placement_mode in (PlacementMode.MIN_BBOX_AREA, PlacementMode.BOTTOM_LEFT):
            return (max(xs) - min(xs)) * (max(ys) - min(ys))
        # MAX_OVERLAP: return negative overlap (for minimization)
        if not self.placed:
            return 0.0
        xs_p = [v[0] for v in placed_flat]
        ys_p = [v[1] for v in placed_flat]
        xs_c = [v[0] for v in cand_verts]
        ys_c = [v[1] for v in cand_verts]
        dxo = min(max(xs_p), max(xs_c)) - max(min(xs_p), min(xs_c))
        dyo = min(max(ys_p), max(ys_c)) - max(min(ys_p), min(ys_c))
        return -(max(0.0, dxo) * max(0.0, dyo))

