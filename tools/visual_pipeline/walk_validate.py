#!/usr/bin/env python3
"""Validate the accepted centered, transparent ``walk-v2`` frame loop."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from tools.visual_pipeline.png_rgba import source_rgba
from tools.visual_pipeline.walk_contract import (
    RUNTIME_SIZE,
    SOURCE_ROOT,
    VIDEO_CHARACTER_FRAME_DIRECTORY,
    VIDEO_FRAME_PREFIX,
    VIDEO_LOOP_FRAME_COUNT,
    VIDEO_MIN_OPAQUE_VISIBLE_RATIO,
    VIDEO_MIN_VISIBLE_ALPHA_MEAN,
    VIDEO_SOURCE_FRAME_SUFFIX,
)


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-root", type=Path)
    return parser.parse_args(argv)


def expected_frame_paths(
    directory: Path,
    *,
    frame_count: int = VIDEO_LOOP_FRAME_COUNT,
) -> list[Path]:
    return [
        directory / f"{VIDEO_FRAME_PREFIX}-{index:03d}{VIDEO_SOURCE_FRAME_SUFFIX}"
        for index in range(frame_count)
    ]


def require_exact_inventory(
    directory: Path,
    *,
    frame_count: int = VIDEO_LOOP_FRAME_COUNT,
) -> list[Path]:
    expected = expected_frame_paths(directory, frame_count=frame_count)
    actual = sorted(directory.glob(f"{VIDEO_FRAME_PREFIX}-*{VIDEO_SOURCE_FRAME_SUFFIX}"))
    if actual != expected:
        missing = [path.name for path in expected if path not in actual]
        extra = [path.name for path in actual if path not in expected]
        raise SystemExit(f"walk_frame_inventory_invalid:missing={missing}:extra={extra}")
    return expected


def _alpha_bounds(pixels: bytes) -> tuple[int, int, int, int]:
    width, height = RUNTIME_SIZE
    visible = [
        (index % width, index // width) for index, alpha in enumerate(pixels[3::4]) if alpha > 8
    ]
    if not visible:
        raise SystemExit("walk_frame_empty")
    xs, ys = zip(*visible, strict=True)
    return min(xs), min(ys), max(xs), max(ys)


def validate(source_root: Path) -> None:
    paths = require_exact_inventory(source_root / VIDEO_CHARACTER_FRAME_DIRECTORY)
    frames = [source_rgba(path, size=RUNTIME_SIZE) for path in paths]
    width, height = RUNTIME_SIZE
    corner_indexes = (3, (width - 1) * 4 + 3, (height - 1) * width * 4 + 3, -1)
    opaque_ratios: list[float] = []
    visible_alpha_means: list[float] = []
    for path, pixels in zip(paths, frames, strict=True):
        if any(pixels[index] for index in corner_indexes):
            raise SystemExit(f"walk_frame_corners_not_transparent:{path.name}")
        visible_alpha = [alpha for alpha in pixels[3::4] if alpha > 8]
        if not visible_alpha:
            raise SystemExit(f"walk_frame_empty:{path.name}")
        opaque_ratio = sum(alpha == 255 for alpha in visible_alpha) / len(visible_alpha)
        visible_alpha_mean = sum(visible_alpha) / len(visible_alpha)
        if opaque_ratio < VIDEO_MIN_OPAQUE_VISIBLE_RATIO:
            raise SystemExit(
                "walk_character_too_translucent:"
                f"{path.name}:opaque_ratio={opaque_ratio:.3f}"
            )
        if visible_alpha_mean < VIDEO_MIN_VISIBLE_ALPHA_MEAN:
            raise SystemExit(
                "walk_character_alpha_too_low:"
                f"{path.name}:visible_alpha_mean={visible_alpha_mean:.1f}"
            )
        opaque_ratios.append(opaque_ratio)
        visible_alpha_means.append(visible_alpha_mean)

    bounds = [_alpha_bounds(frame) for frame in frames]
    union = (
        min(bound[0] for bound in bounds),
        min(bound[1] for bound in bounds),
        max(bound[2] for bound in bounds),
        max(bound[3] for bound in bounds),
    )
    center_x = (union[0] + union[2]) / 2
    if not 244 <= center_x <= 268:
        raise SystemExit(f"walk_character_not_centered:bbox={union}:center_x={center_x:.1f}")
    if not 720 <= union[3] <= 750:
        raise SystemExit(f"walk_grounding_invalid:bbox={union}")
    if max(bound[1] for bound in bounds) - min(bound[1] for bound in bounds) > 20:
        raise SystemExit(f"walk_vertical_drift:{bounds}")
    if any(not 232 <= (bound[0] + bound[2]) / 2 <= 280 for bound in bounds):
        raise SystemExit(f"walk_horizontal_drift:{bounds}")
    if len(set(frames)) < VIDEO_LOOP_FRAME_COUNT // 2:
        raise SystemExit("walk_motion_missing")

    seam_mean = sum(abs(left - right) for left, right in zip(frames[0], frames[-1], strict=True))
    seam_mean /= len(frames[0])
    if seam_mean > 5.0:
        raise SystemExit(f"walk_loop_seam_too_large:{seam_mean:.3f}")

    print(
        "WALK_V2_VALID "
        f"frames={len(paths)} size={width}x{height} bbox={union} "
        f"center_x={center_x:.1f} seam_mean={seam_mean:.3f} "
        f"opaque_ratio_min={min(opaque_ratios):.3f} "
        f"visible_alpha_mean_min={min(visible_alpha_means):.1f}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    repository = args.repository_root.resolve()
    source_root = args.source_root.resolve() if args.source_root else repository / SOURCE_ROOT
    validate(source_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
