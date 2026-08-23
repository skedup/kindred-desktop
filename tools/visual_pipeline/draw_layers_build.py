#!/usr/bin/env python3
"""Build the FRAME2-B2a-R1 ``draw`` continuous-surface pilot.

The reviewed composite remains the authority for every normally visible pixel.
Repair plates are sampled only beneath movable regions and for the closed-eye
state.  Fine-grained partition layers remain as inspectable source provenance,
while Blender renders the limbs, sleeves, palette, and torso through one
lossless ``character_surface`` so internal cut boundaries cannot open.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from tools.visual_pipeline.draw_contract import (
    BRUSH_CORRIDOR_RADIUS,
    BRUSH_SEGMENT,
    CONTRACT_VERSION,
    SOURCE_HEIGHT,
    SOURCE_WIDTH,
    _distance_to_segment,
)
from tools.visual_pipeline.png_rgba import source_rgba, write_rgba

SIZE = (SOURCE_WIDTH, SOURCE_HEIGHT)
LAYER_CONTRACT_VERSION = "frame2-draw-layers-v5"
Mask = Callable[[int, int, tuple[int, int, int, int]], bool]

CHARACTER_SURFACE_MEMBERS = (
    "body_base",
    "support_sleeve",
    "draw_sleeve",
    "palette",
    "support_arm",
    "draw_arm",
)


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    return parser.parse_args(argv)


def _inside_polygon(x: float, y: float, points: tuple[tuple[float, float], ...]) -> bool:
    inside = False
    previous = points[-1]
    for current in points:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def _inside_ellipse(
    x: float,
    y: float,
    bounds: tuple[float, float, float, float],
) -> bool:
    left, top, right, bottom = bounds
    center_x = (left + right) / 2.0
    center_y = (top + bottom) / 2.0
    radius_x = (right - left) / 2.0
    radius_y = (bottom - top) / 2.0
    return ((x - center_x) / radius_x) ** 2 + ((y - center_y) / radius_y) ** 2 <= 1.0


def _hair_like(pixel: tuple[int, int, int, int]) -> bool:
    red, green, blue, alpha = pixel
    return (
        alpha > 8
        and red < 205
        and blue > green + 5
        and blue * 10 >= red * 9
        and red * 20 >= green * 17
        and max(red, green, blue) - min(red, green, blue) >= 12
    )


FRONT_HAIR_REGIONS = (
    (
        (330.0, 65.0),
        (505.0, 62.0),
        (530.0, 165.0),
        (500.0, 255.0),
        (454.0, 285.0),
        (398.0, 260.0),
        (350.0, 225.0),
    ),
    (
        (335.0, 170.0),
        (397.0, 195.0),
        (414.0, 440.0),
        (385.0, 570.0),
        (346.0, 505.0),
        (330.0, 310.0),
    ),
    ((458.0, 145.0), (520.0, 165.0), (515.0, 405.0), (475.0, 470.0), (455.0, 340.0)),
)
BACK_HAIR_REGIONS = (
    (
        (300.0, 65.0),
        (390.0, 40.0),
        (515.0, 70.0),
        (585.0, 185.0),
        (574.0, 340.0),
        (505.0, 430.0),
        (360.0, 410.0),
        (305.0, 285.0),
    ),
    ((320.0, 245.0), (515.0, 245.0), (520.0, 510.0), (355.0, 565.0)),
)
HEAD_FACE_REGION = (
    (352.0, 155.0),
    (505.0, 145.0),
    (535.0, 275.0),
    (505.0, 380.0),
    (480.0, 455.0),
    (385.0, 455.0),
    (350.0, 340.0),
)
HEAD_CROWN_RESIDUAL_REGION = (
    (300.0, 35.0),
    (570.0, 35.0),
    (570.0, 300.0),
    (300.0, 300.0),
)
DRAW_ARM_REGION = (
    (494.0, 402.0),
    (535.0, 411.0),
    (563.0, 456.0),
    (596.0, 458.0),
    (617.0, 426.0),
    (652.0, 425.0),
    (688.0, 458.0),
    (681.0, 497.0),
    (650.0, 524.0),
    (624.0, 526.0),
    (615.0, 544.0),
    (640.0, 575.0),
    (627.0, 607.0),
    (596.0, 633.0),
    (558.0, 616.0),
    (535.0, 577.0),
    (519.0, 542.0),
    (525.0, 507.0),
    (536.0, 477.0),
    (520.0, 442.0),
)
DRAW_FOREARM_HAND_REGION = (
    (548.0, 460.0),
    (575.0, 438.0),
    (597.0, 417.0),
    (630.0, 412.0),
    (652.0, 426.0),
    (677.0, 446.0),
    (690.0, 471.0),
    (682.0, 494.0),
    (662.0, 514.0),
    (635.0, 523.0),
    (610.0, 512.0),
    (594.0, 492.0),
    (570.0, 490.0),
)
SUPPORT_SLEEVE_REGION = (
    (233.0, 402.0),
    (277.0, 411.0),
    (304.0, 445.0),
    (307.0, 493.0),
    (328.0, 535.0),
    (358.0, 561.0),
    (383.0, 585.0),
    (420.0, 600.0),
    (444.0, 618.0),
    (449.0, 640.0),
    (433.0, 657.0),
    (386.0, 665.0),
    (349.0, 657.0),
    (310.0, 653.0),
    (270.0, 638.0),
    (230.0, 616.0),
    (202.0, 585.0),
    (188.0, 548.0),
    (198.0, 496.0),
    (216.0, 449.0),
)
SUPPORT_ARM_REGION = (
    (362.0, 594.0),
    (386.0, 581.0),
    (420.0, 592.0),
    (448.0, 609.0),
    (491.0, 617.0),
    (529.0, 628.0),
    (542.0, 650.0),
    (526.0, 670.0),
    (490.0, 681.0),
    (447.0, 678.0),
    (406.0, 667.0),
    (390.0, 635.0),
    (368.0, 620.0),
)
PALETTE_REGION = (
    (430.0, 613.0),
    (735.0, 606.0),
    (783.0, 626.0),
    (778.0, 644.0),
    (737.0, 673.0),
    (527.0, 665.0),
    (500.0, 656.0),
    (455.0, 648.0),
)
SUPPORT_REPAIR_REGION = (
    (171.0, 375.0),
    (292.0, 370.0),
    (365.0, 450.0),
    (455.0, 545.0),
    (790.0, 580.0),
    (810.0, 706.0),
    (484.0, 732.0),
    (320.0, 742.0),
    (202.0, 662.0),
    (164.0, 548.0),
)
DRAW_ASSEMBLY_REPAIR_REGION = (
    (455.0, 365.0),
    (710.0, 380.0),
    (735.0, 535.0),
    (650.0, 655.0),
    (500.0, 675.0),
    (455.0, 555.0),
)
EYE_REGIONS = (
    (386.0, 200.0, 445.0, 248.0),
    (449.0, 195.0, 510.0, 244.0),
)
FIXED_PROP_REGIONS = (
    # Canvas, mast and horizontal easel assembly.
    ((650.0, 315.0), (930.0, 340.0), (880.0, 710.0), (645.0, 700.0)),
    ((817.0, 250.0), (885.0, 270.0), (854.0, 748.0), (790.0, 735.0)),
    ((651.0, 665.0), (928.0, 651.0), (930.0, 730.0), (655.0, 772.0)),
    # Only unobscured easel-leg runs: the character pixels crossing the legs
    # stay in character layers instead of being frozen as a prop.
    ((700.0, 696.0), (763.0, 698.0), (719.0, 838.0), (668.0, 842.0)),
    ((604.0, 1210.0), (656.0, 1208.0), (646.0, 1352.0), (588.0, 1365.0)),
    ((875.0, 682.0), (907.0, 674.0), (950.0, 1406.0), (893.0, 1411.0)),
    # Visible chair pieces around (rather than through) the seated character.
    ((144.0, 786.0), (262.0, 786.0), (245.0, 871.0), (157.0, 914.0)),
    ((158.0, 875.0), (225.0, 878.0), (239.0, 1370.0), (178.0, 1387.0)),
    ((192.0, 1160.0), (350.0, 1164.0), (352.0, 1228.0), (205.0, 1222.0)),
    ((438.0, 1165.0), (519.0, 1167.0), (525.0, 1233.0), (442.0, 1230.0)),
)


def _brush(x: int, y: int, _pixel: tuple[int, int, int, int]) -> bool:
    return _distance_to_segment(x + 0.5, y + 0.5, *BRUSH_SEGMENT) <= (BRUSH_CORRIDOR_RADIUS + 2.0)


def _draw_arm(x: int, y: int, _pixel: tuple[int, int, int, int]) -> bool:
    return _inside_polygon(x + 0.5, y + 0.5, DRAW_FOREARM_HAND_REGION)


def _draw_sleeve(x: int, y: int, _pixel: tuple[int, int, int, int]) -> bool:
    return _inside_polygon(x + 0.5, y + 0.5, DRAW_ARM_REGION)


def _support_sleeve(x: int, y: int, _pixel: tuple[int, int, int, int]) -> bool:
    return _inside_polygon(x + 0.5, y + 0.5, SUPPORT_SLEEVE_REGION)


def _support_arm(x: int, y: int, _pixel: tuple[int, int, int, int]) -> bool:
    return _inside_polygon(x + 0.5, y + 0.5, SUPPORT_ARM_REGION)


def _palette(x: int, y: int, _pixel: tuple[int, int, int, int]) -> bool:
    return _inside_polygon(x + 0.5, y + 0.5, PALETTE_REGION)


def _eyes(x: int, y: int, _pixel: tuple[int, int, int, int]) -> bool:
    return any(_inside_ellipse(x + 0.5, y + 0.5, region) for region in EYE_REGIONS)


def _hair_front(x: int, y: int, pixel: tuple[int, int, int, int]) -> bool:
    return _hair_like(pixel) and any(
        _inside_polygon(x + 0.5, y + 0.5, region) for region in FRONT_HAIR_REGIONS
    )


def _hair_back(x: int, y: int, pixel: tuple[int, int, int, int]) -> bool:
    return _hair_like(pixel) and any(
        _inside_polygon(x + 0.5, y + 0.5, region) for region in BACK_HAIR_REGIONS
    )


def _head_face(x: int, y: int, _pixel: tuple[int, int, int, int]) -> bool:
    return _inside_polygon(x + 0.5, y + 0.5, HEAD_FACE_REGION)


def _fixed_props(x: int, y: int, _pixel: tuple[int, int, int, int]) -> bool:
    return any(_inside_polygon(x + 0.5, y + 0.5, region) for region in FIXED_PROP_REGIONS)


def _hidden_region(x: int, y: int) -> bool:
    return (
        _inside_ellipse(x + 0.5, y + 0.5, (285.0, 35.0, 610.0, 585.0))
        or _inside_polygon(x + 0.5, y + 0.5, DRAW_ARM_REGION)
        or _distance_to_segment(x + 0.5, y + 0.5, *BRUSH_SEGMENT) <= 24.0
    )


def _support_hidden_region(x: int, y: int) -> bool:
    return _inside_polygon(x + 0.5, y + 0.5, SUPPORT_REPAIR_REGION)


def _canvas_repair_region(x: int, y: int) -> bool:
    """Limit fixed repair pixels to the canvas exposed by brush motion."""

    return (
        650 <= x <= 790
        and 360 <= y <= 570
        and _distance_to_segment(x + 0.5, y + 0.5, *BRUSH_SEGMENT) <= 34.0
    )


def repair_plate_authority(x: int, y: int) -> str | None:
    """Return the clean plate authorized to fill one hidden-underlay pixel."""

    # ``support-clean`` intentionally preserves the drawing-side sleeve and
    # head.  The older localized clean plate must therefore remain authoritative
    # wherever its drawing/head repair intersects the broader support region.
    if _hidden_region(x, y):
        return "hidden"
    if _support_hidden_region(x, y):
        return "support"
    return None


PARTITION: tuple[tuple[str, Mask], ...] = (
    ("brush", _brush),
    ("draw_arm", _draw_arm),
    ("support_arm", _support_arm),
    ("palette", _palette),
    ("draw_sleeve", _draw_sleeve),
    ("support_sleeve", _support_sleeve),
    ("fixed_props", _fixed_props),
    ("eyes_open", _eyes),
    ("hair_front", _hair_front),
    ("hair_back", _hair_back),
    ("head_face", _head_face),
)


def _pixel(image: bytes, index: int) -> tuple[int, int, int, int]:
    offset = index * 4
    return tuple(image[offset : offset + 4])  # type: ignore[return-value]


def _put(target: bytearray, index: int, pixel: tuple[int, int, int, int]) -> None:
    offset = index * 4
    target[offset : offset + 4] = bytes(pixel)


def _copy_visible(target: bytearray, source: bytes) -> None:
    for offset in range(0, len(source), 4):
        if source[offset + 3] > 0:
            target[offset : offset + 4] = source[offset : offset + 4]


def _promote_repair_residuals(
    key: bytes,
    repair: bytes,
    layers: dict[str, bytearray],
    counts: dict[str, int],
    *,
    labels: tuple[str, ...],
    predicate: Callable[[int, int], bool],
    difference_threshold: int = 160,
    max_distance: int = 40,
) -> dict[str, int]:
    """Move missed assembly fragments out of ``body_base`` by nearest seed.

    The hand-authored polygons provide conservative, unambiguous seeds.  A
    repair plate then identifies high-confidence pixels belonging to the
    removed assembly, and a bounded multi-source flood assigns only nearby
    fallback pixels to the closest seeded layer.  This closes elbow fragments
    without turning the generative repair plate into visible source authority.
    """

    size = SOURCE_WIDTH * SOURCE_HEIGHT
    unvisited = 255
    distance = bytearray((unvisited,)) * size
    owner = bytearray(size)
    pending: deque[int] = deque()
    for label_index, name in enumerate(labels, start=1):
        for index, alpha in enumerate(layers[name][3::4]):
            if alpha <= 8 or distance[index] == 0:
                continue
            distance[index] = 0
            owner[index] = label_index
            pending.append(index)

    while pending:
        index = pending.popleft()
        next_distance = distance[index] + 1
        if next_distance > max_distance:
            continue
        x = index % SOURCE_WIDTH
        neighbours = []
        if x > 0:
            neighbours.append(index - 1)
        if x + 1 < SOURCE_WIDTH:
            neighbours.append(index + 1)
        if index >= SOURCE_WIDTH:
            neighbours.append(index - SOURCE_WIDTH)
        if index + SOURCE_WIDTH < size:
            neighbours.append(index + SOURCE_WIDTH)
        for neighbour in neighbours:
            if distance[neighbour] <= next_distance:
                continue
            distance[neighbour] = next_distance
            owner[neighbour] = owner[index]
            pending.append(neighbour)

    promoted = {name: 0 for name in labels}
    body = layers["body_base"]
    for index, body_alpha in enumerate(body[3::4]):
        if body_alpha <= 8 or distance[index] > max_distance or owner[index] == 0:
            continue
        x = index % SOURCE_WIDTH
        y = index // SOURCE_WIDTH
        if not predicate(x, y):
            continue
        offset = index * 4
        difference = sum(
            abs(key[offset + channel] - repair[offset + channel]) for channel in range(4)
        )
        if difference <= difference_threshold:
            continue
        name = labels[owner[index] - 1]
        layers[name][offset : offset + 4] = key[offset : offset + 4]
        body[offset : offset + 4] = b"\x00\x00\x00\x00"
        counts[name] += 1
        counts["body_base"] -= 1
        promoted[name] += 1
    return promoted


def _restore_repair_matched_props(
    key: bytes,
    repair: bytes,
    layers: dict[str, bytearray],
    counts: dict[str, int],
    *,
    labels: tuple[str, ...],
    predicate: Callable[[int, int], bool],
    difference_threshold: int = 160,
) -> dict[str, int]:
    """Return fixed pixels accidentally captured by broad limb polygons.

    The hand-authored limb polygons are deliberately generous so translucent
    cuffs and antialiased fingers are not cut off.  Where those polygons cross
    the canvas, easel, or chair they also select visible prop pixels.  A clean
    repair plate identifies the pixels that were already present behind the
    removed limb; those pixels belong to ``fixed_props`` and must not enter the
    deforming character mesh.
    """

    restored = {name: 0 for name in labels}
    fixed = layers["fixed_props"]
    for name in labels:
        source = layers[name]
        for index, alpha in enumerate(source[3::4]):
            if alpha <= 8:
                continue
            x = index % SOURCE_WIDTH
            y = index // SOURCE_WIDTH
            pixel = _pixel(key, index)
            if not predicate(x, y) or not _fixed_props(x, y, pixel):
                continue
            offset = index * 4
            repair_pixel = repair[offset : offset + 4]
            if repair_pixel[3] <= 8:
                continue
            difference = sum(
                abs(key[offset + channel] - repair_pixel[channel]) for channel in range(4)
            )
            if difference > difference_threshold:
                continue
            fixed[offset : offset + 4] = key[offset : offset + 4]
            source[offset : offset + 4] = b"\x00\x00\x00\x00"
            counts["fixed_props"] += 1
            counts[name] -= 1
            restored[name] += 1
    return restored


def _promote_head_crown_residuals(
    key: bytes,
    layers: dict[str, bytearray],
    counts: dict[str, int],
) -> int:
    """Keep every visible crown/accessory pixel on the rotating head.

    Color-only hair selection intentionally rejects pale rim highlights and
    metallic ornaments.  Above the shoulders the reviewed composite contains
    only the head assembly, so geometry is a safer authority for those missed
    antialiased pixels than another color heuristic.
    """

    promoted = 0
    body = layers["body_base"]
    hair = layers["hair_front"]
    for index, alpha in enumerate(body[3::4]):
        if alpha <= 8:
            continue
        x = index % SOURCE_WIDTH
        y = index // SOURCE_WIDTH
        if not _inside_polygon(x + 0.5, y + 0.5, HEAD_CROWN_RESIDUAL_REGION):
            continue
        offset = index * 4
        hair[offset : offset + 4] = key[offset : offset + 4]
        body[offset : offset + 4] = b"\x00\x00\x00\x00"
        counts["hair_front"] += 1
        counts["body_base"] -= 1
        promoted += 1
    return promoted


def layer_manifest() -> dict[str, object]:
    def layer(
        name: str,
        order: int,
        role: str,
        *,
        pivot: tuple[int, int] | None = None,
        neutral: bool = True,
        partition: bool = True,
        render: bool = True,
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "name": name,
            "file": f"generated/{order:02d}-{name.replace('_', '-')}.png",
            "order": order,
            "role": role,
            "visible_in_neutral": neutral,
            "partition_member": partition,
            "render_in_rig": render,
        }
        if pivot is not None:
            result["pivot"] = list(pivot)
        return result

    return {
        "schema_version": 1,
        "contract": LAYER_CONTRACT_VERSION,
        "parent_contract": CONTRACT_VERSION,
        "canvas": {"width": SOURCE_WIDTH, "height": SOURCE_HEIGHT},
        "runtime_renderer": "frames",
        "layers": [
            layer(
                "hidden_underlay",
                0,
                "repair_source",
                neutral=False,
                partition=False,
                render=False,
            ),
            layer("fixed_props", 10, "fixed_props"),
            layer(
                "canvas_underlay",
                11,
                "fixed_canvas_repair",
                partition=False,
            ),
            layer(
                "character_surface",
                18,
                "continuous_character_surface",
                partition=False,
            ),
            layer(
                "body_base",
                20,
                "character_surface_source",
                neutral=False,
                render=False,
            ),
            layer("hair_back", 30, "head_follow", pivot=(420, 350)),
            layer(
                "head_underlay",
                35,
                "head_follow_repair",
                pivot=(420, 350),
                partition=False,
            ),
            layer("head_face", 40, "head", pivot=(420, 350)),
            layer(
                "eyes_closed",
                50,
                "blink_closed",
                pivot=(420, 350),
                neutral=False,
                partition=False,
            ),
            layer("eyes_open", 51, "blink_open", pivot=(420, 350)),
            layer("hair_front", 60, "head_follow", pivot=(420, 350)),
            layer(
                "support_sleeve",
                64,
                "character_surface_source",
                neutral=False,
                render=False,
            ),
            layer(
                "draw_sleeve",
                65,
                "character_surface_source",
                neutral=False,
                render=False,
            ),
            layer(
                "palette",
                66,
                "character_surface_source",
                neutral=False,
                render=False,
            ),
            layer(
                "support_arm",
                67,
                "character_surface_source",
                neutral=False,
                render=False,
            ),
            layer(
                "draw_arm",
                70,
                "character_surface_source",
                neutral=False,
                render=False,
            ),
            layer("brush", 71, "draw_stroke", pivot=(565, 405)),
        ],
    }


def expected_layer_payloads(repository: Path) -> tuple[dict[str, bytes], dict[str, int]]:
    """Derive every generated layer from the reviewed key and repair plates."""

    source_root = repository / "visual-sources/kindred-default/frame2"
    layer_root = source_root / "layers/draw"
    key = source_rgba(source_root / "keys/draw-key.png", size=SIZE)
    hidden = source_rgba(layer_root / "plates/hidden-clean.png", size=SIZE)
    support = source_rgba(layer_root / "plates/support-clean.png", size=SIZE)
    closed = source_rgba(layer_root / "plates/eyes-closed.png", size=SIZE)

    layer_names = [name for name, _selector in PARTITION] + ["body_base"]
    layers = {name: bytearray(len(key)) for name in layer_names}
    hidden_underlay = bytearray(len(key))
    eyes_closed = bytearray(len(key))
    counts = {name: 0 for name in layer_names}
    counts.update(hidden_underlay=0, eyes_closed=0)

    for index in range(SOURCE_WIDTH * SOURCE_HEIGHT):
        x = index % SOURCE_WIDTH
        y = index // SOURCE_WIDTH
        original_pixel = _pixel(key, index)
        if original_pixel[3] > 0:
            selected = "body_base"
            for name, selector in PARTITION:
                if selector(x, y, original_pixel):
                    selected = name
                    break
            _put(layers[selected], index, original_pixel)
            counts[selected] += 1

        repair_authority = repair_plate_authority(x, y)
        if repair_authority is not None:
            repair = hidden if repair_authority == "hidden" else support
            hidden_pixel = _pixel(repair, index)
            if hidden_pixel[3] > 0:
                _put(hidden_underlay, index, hidden_pixel)
                counts["hidden_underlay"] += 1

        if _eyes(x, y, original_pixel):
            closed_pixel = _pixel(closed, index)
            if closed_pixel[3] > 0:
                _put(eyes_closed, index, closed_pixel)
                counts["eyes_closed"] += 1

    _restore_repair_matched_props(
        key,
        support,
        layers,
        counts,
        labels=("support_sleeve", "support_arm", "palette"),
        predicate=_support_hidden_region,
    )
    _restore_repair_matched_props(
        key,
        hidden,
        layers,
        counts,
        labels=("draw_sleeve", "draw_arm", "brush"),
        predicate=lambda x, y: _inside_polygon(x + 0.5, y + 0.5, DRAW_ASSEMBLY_REPAIR_REGION),
    )
    _promote_head_crown_residuals(key, layers, counts)

    _promote_repair_residuals(
        key,
        support,
        layers,
        counts,
        labels=("support_sleeve", "support_arm", "palette"),
        predicate=_support_hidden_region,
    )
    _promote_repair_residuals(
        key,
        hidden,
        layers,
        counts,
        labels=("draw_sleeve", "draw_arm", "brush"),
        predicate=lambda x, y: _inside_polygon(x + 0.5, y + 0.5, DRAW_ASSEMBLY_REPAIR_REGION),
    )

    payloads = {
        **{name: bytes(pixels) for name, pixels in layers.items()},
        "hidden_underlay": bytes(hidden_underlay),
        "eyes_closed": bytes(eyes_closed),
    }
    head_underlay = bytearray(len(key))
    canvas_underlay = bytearray(len(key))
    for index in range(SOURCE_WIDTH * SOURCE_HEIGHT):
        offset = index * 4
        repair_pixel = hidden[offset : offset + 4]
        if repair_pixel[3] == 0:
            continue
        if payloads["hair_front"][offset + 3] > 0:
            head_underlay[offset : offset + 4] = repair_pixel
        x = index % SOURCE_WIDTH
        y = index // SOURCE_WIDTH
        if _canvas_repair_region(x, y):
            canvas_underlay[offset : offset + 4] = repair_pixel
    payloads["head_underlay"] = bytes(head_underlay)
    payloads["canvas_underlay"] = bytes(canvas_underlay)
    counts["head_underlay"] = sum(alpha > 8 for alpha in head_underlay[3::4])
    counts["canvas_underlay"] = sum(alpha > 8 for alpha in canvas_underlay[3::4])
    character_surface = bytearray(len(key))
    for name in CHARACTER_SURFACE_MEMBERS:
        _copy_visible(character_surface, payloads[name])
    payloads["character_surface"] = bytes(character_surface)
    counts["character_surface"] = sum(alpha > 8 for alpha in character_surface[3::4])
    return payloads, counts


def build(repository: Path) -> dict[str, int]:
    source_root = repository / "visual-sources/kindred-default/frame2"
    layer_root = source_root / "layers/draw"
    payloads, counts = expected_layer_payloads(repository)
    manifest = layer_manifest()
    entries = cast(list[dict[str, object]], manifest["layers"])
    file_by_name = {str(entry["name"]): layer_root / str(entry["file"]) for entry in entries}
    expected_files = {path.name for path in file_by_name.values()}
    for stale in (layer_root / "generated").glob("*.png"):
        if stale.name not in expected_files:
            stale.unlink()
    for name, pixels in payloads.items():
        write_rgba(file_by_name[name], size=SIZE, pixels=pixels)
    (layer_root / "layers.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    counts = build(args.repository_root.resolve())
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
