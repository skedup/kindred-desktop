#!/usr/bin/env python3
"""Validate standing-motion PNG geometry without image-library or Blender dependencies."""

from __future__ import annotations

import argparse
import json
import struct
import sys
import zlib
from collections.abc import Sequence
from pathlib import Path

from tools.visual_pipeline.png_rgba import (
    ALPHA_VISIBLE,
    RUNTIME_SIZE,
    FrameValidationError,
    frame_info,
    rgba_pixels,
)

EXPECTED_FRAMES = {"settle": 18, "sleep": 24, "eat": 12}
EXPECTED_ENTER = {"settle": 3, "sleep": 4, "eat": 3}
SETTLE_EYE_GUARD = (200, 52, 316, 110)


def _outside_eye_delta(first: Path, second: Path) -> float:
    first_pixels = rgba_pixels(first)
    second_pixels = rgba_pixels(second)
    left, top, right, bottom = SETTLE_EYE_GUARD
    total = 0
    samples = 0
    width, _ = RUNTIME_SIZE
    for index in range(0, len(first_pixels), 4):
        pixel = index // 4
        x, y = pixel % width, pixel // width
        if left <= x < right and top <= y < bottom:
            continue
        first_pixel = first_pixels[index : index + 4]
        second_pixel = second_pixels[index : index + 4]
        if max(first_pixel[3], second_pixel[3]) <= ALPHA_VISIBLE:
            continue
        total += sum(abs(a - b) for a, b in zip(first_pixel, second_pixel, strict=True))
        samples += 4
    if samples == 0:
        raise FrameValidationError("settle_blink_samples_missing")
    return total / samples


def validate(pack: Path) -> dict[str, object]:
    root = pack / "assets/body/frame1"
    result: dict[str, object] = {}
    for motion, count in EXPECTED_FRAMES.items():
        directory = root / motion
        expected_names = [f"{motion}-{index:03d}.png" for index in range(count)]
        actual_names = sorted(path.name for path in directory.glob("*.png"))
        if actual_names != expected_names:
            raise FrameValidationError(f"frame_inventory_invalid:{motion}")
        infos = [frame_info(directory / name) for name in expected_names]
        baselines = [info.bounds[3] for info in infos]
        if max(baselines) - min(baselines) > 1:
            raise FrameValidationError(f"baseline_drift:{motion}")
        unique = len({info.digest for info in infos})
        if unique < max(3, count // 2):
            raise FrameValidationError(f"insufficient_motion:{motion}")
        motion_manifest = json.loads((pack / f"motions/{motion}.json").read_text(encoding="utf-8"))
        enter_count = EXPECTED_ENTER[motion]
        sources = [f"assets/body/frame1/{motion}/{name}" for name in expected_names]
        expected_enter = sources[:enter_count]
        expected_loop = sources[enter_count:] + sources[:enter_count]
        if (
            motion_manifest.get("schema_version") != 1
            or motion_manifest.get("fps") != 6
            or motion_manifest.get("enter") != expected_enter
            or motion_manifest.get("loop") != expected_loop
        ):
            raise FrameValidationError(f"frame_schedule_invalid:{motion}")
        if motion == "settle":
            normal_delta = _outside_eye_delta(
                directory / expected_names[8], directory / expected_names[9]
            )
            blink_delta = _outside_eye_delta(
                directory / expected_names[9], directory / expected_names[10]
            )
            if blink_delta > max(1.0, normal_delta * 3.0):
                raise FrameValidationError("settle_blink_global_flash")
        result[motion] = {
            "frames": count,
            "unique": unique,
            "enter": enter_count,
            "baseline": [min(baselines), max(baselines)],
            **({"blink_outside_eye_delta": round(blink_delta, 4)} if motion == "settle" else {}),
        }
    return result


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pack",
        type=Path,
        nargs="?",
        default=Path("visual-packs/kindred-default"),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    try:
        result = validate(args.pack.resolve())
    except (OSError, json.JSONDecodeError, struct.error, zlib.error, FrameValidationError) as exc:
        print(f"FRAME1 validation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
