#!/usr/bin/env python3
"""Validate the approved transparent ``settle-v2`` butterfly event."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from tools.visual_pipeline.png_rgba import source_rgba
from tools.visual_pipeline.settle_contract import (
    EVENT_FRAME_COUNT,
    EVENT_FRAME_DIRECTORY,
    EVENT_FRAME_PREFIX,
    IDLE_REFERENCE,
    MAX_IDLE_TRANSITION_MEAN,
    RUNTIME_SIZE,
    SOURCE_FRAME_SUFFIX,
    SOURCE_ROOT,
    VIDEO_MIN_OPAQUE_VISIBLE_RATIO,
    VIDEO_MIN_VISIBLE_ALPHA_MEAN,
)


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-root", type=Path)
    return parser.parse_args(argv)


def expected_frame_paths(directory: Path, *, frame_count: int = EVENT_FRAME_COUNT) -> list[Path]:
    return [
        directory / f"{EVENT_FRAME_PREFIX}-{index:03d}{SOURCE_FRAME_SUFFIX}"
        for index in range(frame_count)
    ]


def require_exact_inventory(
    directory: Path,
    *,
    frame_count: int = EVENT_FRAME_COUNT,
) -> list[Path]:
    expected = expected_frame_paths(directory, frame_count=frame_count)
    actual = sorted(directory.glob(f"{EVENT_FRAME_PREFIX}-*{SOURCE_FRAME_SUFFIX}"))
    if actual != expected:
        missing = [path.name for path in expected if path not in actual]
        extra = [path.name for path in actual if path not in expected]
        raise SystemExit(f"settle_frame_inventory_invalid:missing={missing}:extra={extra}")
    return expected


def _grounded_bounds(pixels: bytes) -> tuple[int, int, int, int]:
    width, height = RUNTIME_SIZE
    column_counts = [0] * width
    row_counts = [0] * height
    for index, alpha in enumerate(pixels[3::4]):
        if alpha <= 8:
            continue
        x = index % width
        y = index // width
        if y >= 600:
            column_counts[x] += 1
        row_counts[y] += 1
    # The butterfly and raised arm intentionally travel across the upper half.
    # Use the lower-leg/foot region as the stable horizontal character anchor.
    xs = [index for index, count in enumerate(column_counts) if count >= 8]
    ys = [index for index, count in enumerate(row_counts) if count >= 24]
    if not xs or not ys:
        raise SystemExit("settle_frame_body_missing")
    return min(xs), min(ys), max(xs), max(ys)


def _mean_rgba_difference(left: bytes, right: bytes) -> float:
    return sum(abs(a - b) for a, b in zip(left, right, strict=True)) / len(left)


def validate(source_root: Path, *, idle_reference: Path | None = None) -> None:
    paths = require_exact_inventory(source_root / EVENT_FRAME_DIRECTORY)
    frames = [source_rgba(path, size=RUNTIME_SIZE) for path in paths]
    width, height = RUNTIME_SIZE
    corner_indexes = (3, (width - 1) * 4 + 3, (height - 1) * width * 4 + 3, -1)
    opaque_ratios: list[float] = []
    visible_alpha_means: list[float] = []
    for path, pixels in zip(paths, frames, strict=True):
        if any(pixels[index] for index in corner_indexes):
            raise SystemExit(f"settle_frame_corners_not_transparent:{path.name}")
        visible_alpha = [alpha for alpha in pixels[3::4] if alpha > 8]
        if not visible_alpha:
            raise SystemExit(f"settle_frame_empty:{path.name}")
        opaque_ratio = sum(alpha == 255 for alpha in visible_alpha) / len(visible_alpha)
        visible_alpha_mean = sum(visible_alpha) / len(visible_alpha)
        if opaque_ratio < VIDEO_MIN_OPAQUE_VISIBLE_RATIO:
            raise SystemExit(
                f"settle_character_too_translucent:{path.name}:opaque_ratio={opaque_ratio:.3f}"
            )
        if visible_alpha_mean < VIDEO_MIN_VISIBLE_ALPHA_MEAN:
            raise SystemExit(
                "settle_character_alpha_too_low:"
                f"{path.name}:visible_alpha_mean={visible_alpha_mean:.1f}"
            )
        opaque_ratios.append(opaque_ratio)
        visible_alpha_means.append(visible_alpha_mean)

    bounds = [_grounded_bounds(frame) for frame in frames]
    centers = [(left + right) / 2 for left, _, right, _ in bounds]
    bottoms = [bottom for _, _, _, bottom in bounds]
    if any(not 244 <= center <= 256 for center in centers):
        raise SystemExit(f"settle_character_horizontal_drift:{bounds}")
    average_bottom = round(sum(bottoms) / len(bottoms))
    if max(bottoms) - min(bottoms) > 8 or not 740 <= average_bottom <= 752:
        raise SystemExit(f"settle_character_grounding_invalid:{bounds}")
    if len(set(frames)) < EVENT_FRAME_COUNT // 2:
        raise SystemExit("settle_motion_missing")

    seam_mean = _mean_rgba_difference(frames[0], frames[-1])
    if seam_mean > 5.0:
        raise SystemExit(f"settle_event_seam_too_large:{seam_mean:.3f}")

    idle_transition_mean: float | None = None
    if idle_reference is not None:
        idle = source_rgba(idle_reference, size=RUNTIME_SIZE)
        idle_transition_mean = _mean_rgba_difference(frames[-1], idle)
        if idle_transition_mean > MAX_IDLE_TRANSITION_MEAN:
            raise SystemExit(f"settle_idle_transition_too_large:{idle_transition_mean:.3f}")

    idle_summary = (
        "" if idle_transition_mean is None else f"idle_transition_mean={idle_transition_mean:.3f} "
    )
    print(
        "SETTLE_V2_VALID "
        f"frames={len(paths)} size={width}x{height} "
        f"center=[{min(centers):.1f},{max(centers):.1f}] "
        f"bottom=[{min(bottoms)},{max(bottoms)}] seam_mean={seam_mean:.3f} "
        f"{idle_summary}"
        f"opaque_ratio_min={min(opaque_ratios):.3f} "
        f"visible_alpha_mean_min={min(visible_alpha_means):.1f}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    repository = args.repository_root.resolve()
    source_root = args.source_root.resolve() if args.source_root else repository / SOURCE_ROOT
    validate(source_root, idle_reference=repository / IDLE_REFERENCE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
