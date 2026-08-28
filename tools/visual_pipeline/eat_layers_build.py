#!/usr/bin/env python3
"""Build the approved ``eat-v2`` source layers from reviewed plates.

The approved master remains authoritative for normally visible pixels.  The
two clean plates are sampled only for surfaces hidden by the resting pose.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Sequence
from pathlib import Path

from tools.visual_pipeline.eat_contract import (
    GRIP_REGION,
    SOURCE_SIZE,
    SUPPORT_HAND_REGION,
    inside_table_gutter,
    table_boundary_y,
)
from tools.visual_pipeline.png_rgba import source_rgba, write_rgba

SIZE = SOURCE_SIZE
WIDTH, HEIGHT = SIZE
VISIBLE_ALPHA = 8


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


def _distance_to_segment(
    x: float,
    y: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.hypot(x - start[0], y - start[1])
    projection = ((x - start[0]) * dx + (y - start[1]) * dy) / length_squared
    position = max(0.0, min(1.0, projection))
    nearest_x = start[0] + position * dx
    nearest_y = start[1] + position * dy
    return math.hypot(x - nearest_x, y - nearest_y)


SPOON_BOWL = (
    (348.0, 1005.0),
    (365.0, 993.0),
    (394.0, 992.0),
    (430.0, 1002.0),
    (459.0, 1019.0),
    (470.0, 1035.0),
    (466.0, 1048.0),
    (448.0, 1057.0),
    (420.0, 1058.0),
    (386.0, 1048.0),
    (360.0, 1034.0),
    (349.0, 1017.0),
)
SPOON_SEGMENTS = (
    ((184.0, 868.0), (294.0, 939.0)),
    ((276.0, 923.0), (382.0, 1019.0)),
)

BOWL_FRONT = (
    (307.0, 1124.0),
    (334.0, 1098.0),
    (393.0, 1080.0),
    (501.0, 1084.0),
    (566.0, 1102.0),
    (606.0, 1137.0),
    (599.0, 1217.0),
    (561.0, 1264.0),
    (474.0, 1283.0),
    (382.0, 1274.0),
    (328.0, 1234.0),
)


def _metal_like(pixel: tuple[int, int, int, int]) -> bool:
    red, green, blue, alpha = pixel
    return (
        alpha > VISIBLE_ALPHA
        and 35 <= max(red, green, blue) <= 252
        and max(red, green, blue) - min(red, green, blue) <= 45
        and not (red > green + 12 and red > blue + 12)
    )


def _skin_like(pixel: tuple[int, int, int, int]) -> bool:
    red, green, blue, alpha = pixel
    return (
        alpha > VISIBLE_ALPHA
        and red > 150
        and green > 90
        and blue > 80
        and red > green + 8
        and red > blue + 5
        and max(red, green, blue) - min(red, green, blue) < 130
    )


def _spoon(x: int, y: int, pixel: tuple[int, int, int, int]) -> bool:
    center_x = x + 0.5
    center_y = y + 0.5
    if _inside_polygon(center_x, center_y, SPOON_BOWL):
        return pixel[3] > VISIBLE_ALPHA
    return _metal_like(pixel) and any(
        _distance_to_segment(center_x, center_y, start, end) <= 6.0 for start, end in SPOON_SEGMENTS
    )


def _foreground_occluder(x: int, y: int) -> bool:
    center_x = x + 0.5
    center_y = y + 0.5
    table_front = center_y >= table_boundary_y(center_x)
    bowl_front = _inside_polygon(center_x, center_y, BOWL_FRONT)
    return table_front or bowl_front


def _pixel(pixels: bytes | bytearray, index: int) -> tuple[int, int, int, int]:
    offset = index * 4
    return tuple(pixels[offset : offset + 4])  # type: ignore[return-value]


def _put(destination: bytearray, index: int, pixel: tuple[int, int, int, int]) -> None:
    offset = index * 4
    destination[offset : offset + 4] = bytes(pixel)


def _distance(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> int:
    return sum(abs(left[channel] - right[channel]) for channel in range(3)) + abs(
        left[3] - right[3]
    )


def _character_visible(
    master: tuple[int, int, int, int],
    fixed: tuple[int, int, int, int],
    character: tuple[int, int, int, int],
) -> bool:
    if character[3] <= VISIBLE_ALPHA:
        return False
    if fixed[3] <= VISIBLE_ALPHA:
        return True
    return _distance(master, character) + 18 < _distance(master, fixed)


def _source_over(back: bytearray, front: bytes | bytearray) -> None:
    for offset in range(0, len(back), 4):
        front_alpha = front[offset + 3]
        if front_alpha == 0:
            continue
        if front_alpha == 255:
            back[offset : offset + 4] = front[offset : offset + 4]
            continue
        back_alpha = back[offset + 3]
        alpha = front_alpha + (back_alpha * (255 - front_alpha) + 127) // 255
        if alpha == 0:
            continue
        for channel in range(3):
            numerator = front[offset + channel] * front_alpha * 255 + back[
                offset + channel
            ] * back_alpha * (255 - front_alpha)
            back[offset + channel] = (numerator + alpha * 127) // (alpha * 255)
        back[offset + 3] = alpha


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_digest(path: Path) -> str:
    return _digest(path.read_bytes())


def build(repository: Path) -> dict[str, object]:
    source_root = repository / "visual-sources/kindred-default/eat-v2"
    master = source_rgba(source_root / "keys/eat-master.png", size=SIZE)
    fixed_clean = source_rgba(source_root / "layers/plates/fixed-props-clean.png", size=SIZE)
    character_clean = source_rgba(source_root / "layers/plates/character-clean.png", size=SIZE)
    spoon_complete = source_rgba(source_root / "layers/plates/spoon-complete.png", size=SIZE)

    rear = bytearray(fixed_clean)
    character = bytearray(character_clean)
    spoon = bytearray(spoon_complete)
    foreground = bytearray(len(master))
    spoon_mask = bytearray(len(master))
    character_visible_mask = bytearray(len(master))
    grip_overlay = bytearray(len(master))
    support_overlay = bytearray(len(master))
    rear_visible_mask = bytearray(len(master))
    foreground_visible_mask = bytearray(len(master))

    counts = {
        "master_visible": 0,
        "character_authority": 0,
        "fixed_authority": 0,
        "spoon": 0,
        "foreground": 0,
    }

    for index in range(WIDTH * HEIGHT):
        x = index % WIDTH
        y = index // WIDTH
        master_pixel = _pixel(master, index)
        if master_pixel[3] <= VISIBLE_ALPHA:
            continue
        counts["master_visible"] += 1

        original_spoon = _spoon(x, y, master_pixel)
        if spoon_complete[index * 4 + 3] > VISIBLE_ALPHA or original_spoon:
            _put(spoon_mask, index, (255, 255, 255, 255))
            counts["spoon"] += 1
            if original_spoon:
                continue

        fixed_pixel = _pixel(fixed_clean, index)
        character_pixel = _pixel(character_clean, index)
        inside_bowl = _inside_polygon(x + 0.5, y + 0.5, BOWL_FRONT)
        support_hand = (
            inside_bowl
            and _inside_polygon(x + 0.5, y + 0.5, SUPPORT_HAND_REGION)
            and _skin_like(character_pixel)
        )
        if support_hand:
            _put(character_visible_mask, index, (255, 255, 255, 255))
            _put(support_overlay, index, character_pixel)
            counts["character_authority"] += 1
        elif not inside_bowl and _character_visible(master_pixel, fixed_pixel, character_pixel):
            _put(character, index, master_pixel)
            _put(character_visible_mask, index, (255, 255, 255, 255))
            if _inside_polygon(x + 0.5, y + 0.5, GRIP_REGION) and not original_spoon:
                _put(grip_overlay, index, master_pixel)
            counts["character_authority"] += 1
        else:
            counts["fixed_authority"] += 1

    for index in range(WIDTH * HEIGHT):
        x = index % WIDTH
        y = index // WIDTH
        if inside_table_gutter(x + 0.5, y + 0.5):
            _put(rear, index, (0, 0, 0, 0))
            continue
        if not _foreground_occluder(x, y):
            continue
        fixed_pixel = _pixel(rear, index)
        if fixed_pixel[3] <= VISIBLE_ALPHA:
            continue
        _put(foreground, index, fixed_pixel)
        counts["foreground"] += 1

    layer_root = source_root / "layers"
    destinations = {
        "rear_static": layer_root / "rear-static/rear-static.png",
        "character": layer_root / "character/character-surface.png",
        "spoon": layer_root / "spoon/spoon.png",
        "foreground": layer_root / "foreground-occluder/foreground-occluder.png",
        "spoon_mask": layer_root / "validation-masks/spoon-semantic-mask.png",
        "character_visible_mask": layer_root / "validation-masks/character-visible-mask.png",
        "rear_visible_mask": layer_root / "validation-masks/rear-static-visible-mask.png",
        "foreground_visible_mask": layer_root / "validation-masks/foreground-visible-mask.png",
    }
    payloads = {
        "rear_static": bytes(rear),
        "character": bytes(character),
        "spoon": bytes(spoon),
        "foreground": bytes(foreground),
        "spoon_mask": bytes(spoon_mask),
        "character_visible_mask": bytes(character_visible_mask),
    }

    character_render = bytearray(payloads["character"])

    for index in range(WIDTH * HEIGHT):
        offset = index * 4
        foreground_alpha = foreground[offset + 3]
        if foreground_alpha > VISIBLE_ALPHA:
            _put(foreground_visible_mask, index, (255, 255, 255, 255))
        if (
            rear[offset + 3] > VISIBLE_ALPHA
            and character_render[offset + 3] <= VISIBLE_ALPHA
            and spoon[offset + 3] <= VISIBLE_ALPHA
            and support_overlay[offset + 3] <= VISIBLE_ALPHA
            and grip_overlay[offset + 3] <= VISIBLE_ALPHA
            and foreground_alpha <= VISIBLE_ALPHA
        ):
            _put(rear_visible_mask, index, (255, 255, 255, 255))

    payloads["rear_visible_mask"] = bytes(rear_visible_mask)
    payloads["foreground_visible_mask"] = bytes(foreground_visible_mask)
    counts["rear_visible_mask"] = sum(
        rear_visible_mask[offset + 3] > VISIBLE_ALPHA
        for offset in range(0, len(rear_visible_mask), 4)
    )
    counts["foreground_visible_mask"] = sum(
        foreground_visible_mask[offset + 3] > VISIBLE_ALPHA
        for offset in range(0, len(foreground_visible_mask), 4)
    )

    for name, destination in destinations.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_rgba(destination, size=SIZE, pixels=payloads[name])

    composite = bytearray(len(master))
    _source_over(composite, payloads["rear_static"])
    _source_over(composite, character_render)
    _source_over(composite, payloads["spoon"])
    _source_over(composite, payloads["foreground"])
    _source_over(composite, support_overlay)
    _source_over(composite, grip_overlay)
    composite_path = source_root / "previews/eat-master-recomposed.png"
    write_rgba(composite_path, size=SIZE, pixels=bytes(composite))

    changed_pixels = sum(
        composite[offset : offset + 4] != master[offset : offset + 4]
        for offset in range(0, len(master), 4)
    )
    missing_visible_pixels = sum(
        master[offset + 3] > VISIBLE_ALPHA and composite[offset + 3] <= VISIBLE_ALPHA
        for offset in range(0, len(master), 4)
    )
    unexpected_visible_pixels = sum(
        master[offset + 3] <= VISIBLE_ALPHA and composite[offset + 3] > VISIBLE_ALPHA
        for offset in range(0, len(master), 4)
    )
    manifest = {
        "contract": "eat-v2-layers-v1",
        "size": list(SIZE),
        "order": ["rear_static", "character", "spoon", "foreground"],
        "internal_character_replays": ["support_hand", "grip"],
        "layers": {
            name: {
                "file": str(destinations[name].relative_to(source_root)),
                "sha256_file": _file_digest(destinations[name]),
                "sha256_rgba": _digest(payloads[name]),
            }
            for name in (
                "rear_static",
                "character",
                "spoon",
                "foreground",
                "spoon_mask",
                "character_visible_mask",
                "rear_visible_mask",
                "foreground_visible_mask",
            )
        },
        "sources": {
            "master": {
                "file": "keys/eat-master.png",
                "sha256_file": _file_digest(source_root / "keys/eat-master.png"),
            },
            "fixed_props_clean": {
                "file": "layers/plates/fixed-props-clean.png",
                "sha256_file": _file_digest(source_root / "layers/plates/fixed-props-clean.png"),
            },
            "character_clean": {
                "file": "layers/plates/character-clean.png",
                "sha256_file": _file_digest(source_root / "layers/plates/character-clean.png"),
            },
            "spoon_complete": {
                "file": "layers/plates/spoon-complete.png",
                "sha256_file": _file_digest(source_root / "layers/plates/spoon-complete.png"),
            },
            "recomposed_preview": {
                "file": "previews/eat-master-recomposed.png",
                "sha256_file": _file_digest(composite_path),
            },
        },
        "recomposed_changed_pixels": changed_pixels,
        "recomposed_missing_visible_pixels": missing_visible_pixels,
        "recomposed_unexpected_visible_pixels": unexpected_visible_pixels,
        "counts": counts,
    }
    (layer_root / "layers.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    print(json.dumps(build(args.repository_root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
