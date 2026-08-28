"""Shared, dependency-free contract for the approved ``eat-v2`` loop."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

SOURCE_SIZE = (1024, 1536)
RUNTIME_SIZE = (512, 768)
FPS = 12
FRAME_COUNT = 84
DURATION_SECONDS = FRAME_COUNT / FPS

# The runtime stage is 304 CSS pixels wide while the status card is 284 pixels
# wide. A 17-pixel runtime gutter on each side maps to 34 source pixels and
# keeps the breakfast table aligned with the card without scaling the person.
SOURCE_TABLE_HORIZONTAL_INSET = 34.0
RUNTIME_TABLE_HORIZONTAL_INSET = round(
    SOURCE_TABLE_HORIZONTAL_INSET * RUNTIME_SIZE[0] / SOURCE_SIZE[0]
)
TABLE_BOUNDARY_INTERCEPT = 1127.0
TABLE_BOUNDARY_SLOPE = 0.089

SOURCE_ROOT = Path("visual-sources/kindred-default/eat-v2")
FRAME_DIRECTORY = Path("frames/scene-warp-v1")
FRAME_PREFIX = "motion"

REAR_LAYER = Path("layers/rear-static/rear-static.png")
CHARACTER_LAYER = Path("layers/character/character-surface.png")
SPOON_LAYER = Path("layers/spoon/spoon.png")
FOREGROUND_LAYER = Path("layers/foreground-occluder/foreground-occluder.png")
CHARACTER_VISIBLE_MASK = Path("layers/validation-masks/character-visible-mask.png")

# Source-space regions used only to replay pixels from the same continuous
# character surface above the rigid spoon and fixed foreground. They are not
# independently authored limb assets.
GRIP_REGION = (
    (154.0, 844.0),
    (260.0, 840.0),
    (326.0, 899.0),
    (326.0, 989.0),
    (281.0, 1042.0),
    (190.0, 1033.0),
    (143.0, 969.0),
)
SUPPORT_HAND_REGION = (
    (458.0, 1070.0),
    (594.0, 1068.0),
    (690.0, 1112.0),
    (713.0, 1198.0),
    (672.0, 1264.0),
    (538.0, 1276.0),
    (466.0, 1222.0),
    (439.0, 1142.0),
)


@dataclass(frozen=True)
class EatPose:
    """Normalized authored controls for one frame of the eat loop."""

    approach: float
    lift: float
    sip: float
    breath: float


def table_boundary_y(x: float) -> float:
    """Return the approved source-space boundary of the foreground table."""

    return TABLE_BOUNDARY_INTERCEPT + x * TABLE_BOUNDARY_SLOPE


def inside_table_gutter(x: float, y: float) -> bool:
    """Return whether a source-space point is in a transparent table gutter."""

    return (
        x < SOURCE_TABLE_HORIZONTAL_INSET or x >= SOURCE_SIZE[0] - SOURCE_TABLE_HORIZONTAL_INSET
    ) and y >= table_boundary_y(x)


def runtime_inside_table_gutter(x: int, y: int) -> bool:
    """Map a runtime pixel center to the approved source-space table gutter."""

    scale_x = SOURCE_SIZE[0] / RUNTIME_SIZE[0]
    scale_y = SOURCE_SIZE[1] / RUNTIME_SIZE[1]
    return inside_table_gutter((x + 0.5) * scale_x, (y + 0.5) * scale_y)


def smoothstep(edge_zero: float, edge_one: float, value: float) -> float:
    """Return a clamped cubic transition between two scalar edges."""

    if edge_zero == edge_one:
        return float(value >= edge_one)
    amount = max(0.0, min(1.0, (value - edge_zero) / (edge_one - edge_zero)))
    return amount * amount * (3.0 - 2.0 * amount)


def _bump(start: float, peak: float, end: float, value: float) -> float:
    if value <= start or value >= end:
        return 0.0
    if value <= peak:
        return smoothstep(start, peak, value)
    return 1.0 - smoothstep(peak, end, value)


def timeline(
    frame: int,
    frame_count: int = FRAME_COUNT,
    fps: int = FPS,
) -> EatPose:
    """Return the scoop, lift, sip, and breathing controls for a seven-second loop."""

    if not 0 <= frame < frame_count:
        raise ValueError(f"frame outside loop: {frame}")
    if frame_count < 2 or fps <= 0:
        raise ValueError("eat timeline requires at least two frames and a positive FPS")

    duration = frame_count / fps
    scale = duration / 7.0
    seconds = frame / fps

    approach = _bump(0.8 * scale, 1.65 * scale, 2.2 * scale, seconds)

    lift_start = 2.0 * scale
    lift_peak = 3.35 * scale
    lift_hold = 4.15 * scale
    lift_end = 5.8 * scale
    if seconds <= lift_start or seconds >= lift_end:
        lift = 0.0
    elif seconds < lift_peak:
        lift = smoothstep(lift_start, lift_peak, seconds)
    elif seconds <= lift_hold:
        lift = 1.0
    else:
        lift = 1.0 - smoothstep(lift_hold, lift_end, seconds)

    sip = _bump(3.35 * scale, 3.75 * scale, 4.2 * scale, seconds)
    breath = math.sin(2.0 * math.pi * frame / (frame_count - 1))
    if abs(breath) < 1e-12:
        breath = 0.0
    return EatPose(approach=approach, lift=lift, sip=sip, breath=breath)
