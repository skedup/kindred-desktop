"""Shared geometry contract for the FRAME2 ``draw`` source and validator."""

from __future__ import annotations

import math

CONTRACT_VERSION = "frame2-draw-v2"
SOURCE_WIDTH = 1024
SOURCE_HEIGHT = 1536
RUNTIME_WIDTH = 512
RUNTIME_HEIGHT = 768
FRAME_COUNT = 24
ENTER_COUNT = 4
FPS = 6

# Source-canvas regions containing the visible easel/canvas/chair assembly.  The
# generator freezes a slightly expanded form of these regions so interpolation
# at the mesh boundary cannot move pixels covered by the validator mask.
PROP_ANCHOR_RECTS = (
    (665.0, 245.0, 935.0, 775.0),  # easel, canvas and crossbar
    (575.0, 660.0, 765.0, 1335.0),  # easel left support/leg
    (790.0, 640.0, 945.0, 1400.0),  # easel right support/leg
    (130.0, 770.0, 570.0, 1390.0),  # chair seat, legs and foot rail
)
PROP_GENERATOR_FEATHER = 28.0
PROP_VALIDATION_INSET = 24.0

# The brush crosses the canvas.  It belongs to the moving hand rather than the
# fixed easel, so carve a narrow corridor through the easel mask.
BRUSH_SEGMENT = ((565.0, 405.0), (755.0, 515.0))
BRUSH_CORRIDOR_RADIUS = 10.0
BRUSH_CORRIDOR_FEATHER = 36.0
PROP_VALIDATION_BRUSH_PADDING = BRUSH_CORRIDOR_FEATHER + 24.0

# Runtime-canvas ROI containing the drawing hand and brush shaft but excluding
# most breathing torso/fabric motion.  The validator compares stroke frames to
# idle-only frame pairs in the same ROI.
STROKE_RUNTIME_ROI = (285, 195, 370, 255)


def _inside_rect(
    x: float,
    y: float,
    rect: tuple[float, float, float, float],
    *,
    margin: float = 0.0,
) -> bool:
    left, top, right, bottom = rect
    return left - margin <= x <= right + margin and top - margin <= y <= bottom + margin


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    if edge0 == edge1:
        return float(value >= edge1)
    amount = min(1.0, max(0.0, (value - edge0) / (edge1 - edge0)))
    return amount * amount * (3.0 - 2.0 * amount)


def _rect_anchor_weight(
    x: float,
    y: float,
    rect: tuple[float, float, float, float],
) -> float:
    left, top, right, bottom = rect
    outside_x = max(left - x, 0.0, x - right)
    outside_y = max(top - y, 0.0, y - bottom)
    outside_distance = math.hypot(outside_x, outside_y)
    return 1.0 - _smoothstep(0.0, PROP_GENERATOR_FEATHER, outside_distance)


def _distance_to_segment(
    x: float,
    y: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    start_x, start_y = start
    end_x, end_y = end
    delta_x = end_x - start_x
    delta_y = end_y - start_y
    length_squared = delta_x * delta_x + delta_y * delta_y
    if length_squared == 0.0:
        return math.hypot(x - start_x, y - start_y)
    amount = ((x - start_x) * delta_x + (y - start_y) * delta_y) / length_squared
    amount = min(1.0, max(0.0, amount))
    closest_x = start_x + amount * delta_x
    closest_y = start_y + amount * delta_y
    return math.hypot(x - closest_x, y - closest_y)


def _inside_brush_corridor(x: float, y: float, *, padding: float = 0.0) -> bool:
    return _distance_to_segment(x, y, *BRUSH_SEGMENT) <= BRUSH_CORRIDOR_RADIUS + padding


def prop_anchor_weight(x: float, y: float) -> float:
    """Return a feathered prop anchor while preserving the moving brush corridor."""

    region_weight = max(_rect_anchor_weight(x, y, rect) for rect in PROP_ANCHOR_RECTS)
    brush_distance = _distance_to_segment(x, y, *BRUSH_SEGMENT)
    brush_factor = _smoothstep(
        BRUSH_CORRIDOR_RADIUS,
        BRUSH_CORRIDOR_RADIUS + BRUSH_CORRIDOR_FEATHER,
        brush_distance,
    )
    return region_weight * brush_factor


def is_prop_validation_pixel(x: int, y: int) -> bool:
    """Return whether a runtime pixel belongs to the reviewed prop mask."""

    source_x = (x + 0.5) * SOURCE_WIDTH / RUNTIME_WIDTH
    source_y = (y + 0.5) * SOURCE_HEIGHT / RUNTIME_HEIGHT
    if _inside_brush_corridor(
        source_x,
        source_y,
        padding=PROP_VALIDATION_BRUSH_PADDING,
    ):
        return False
    return any(
        _inside_rect(
            source_x,
            source_y,
            rect,
            margin=-PROP_VALIDATION_INSET,
        )
        for rect in PROP_ANCHOR_RECTS
    )


def is_stroke_validation_pixel(x: int, y: int) -> bool:
    """Return whether a runtime pixel belongs to the hand/brush stroke ROI."""

    left, top, right, bottom = STROKE_RUNTIME_ROI
    return left <= x < right and top <= y < bottom
