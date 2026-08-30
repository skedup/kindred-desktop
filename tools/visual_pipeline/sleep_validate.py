#!/usr/bin/env python3
"""Validate the approved master and source frames for ``sleep-v2``."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from tools.visual_pipeline.png_rgba import frame_info, rgba_pixels, source_rgba
from tools.visual_pipeline.sleep_contract import (
    FRAME_COUNT,
    FRAME_DIRECTORY,
    FRAME_PREFIX,
    MASTER,
    RUNTIME_SIZE,
    SOURCE_ROOT,
    SOURCE_SIZE,
)


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-root", type=Path)
    return parser.parse_args(argv)


def require_exact_inventory(frame_root: Path) -> list[Path]:
    expected = [frame_root / f"{FRAME_PREFIX}-{frame:03d}.png" for frame in range(FRAME_COUNT)]
    actual = sorted(frame_root.glob(f"{FRAME_PREFIX}-*.png"))
    if actual != expected:
        missing = [path.name for path in expected if path not in actual]
        extra = [path.name for path in actual if path not in expected]
        raise SystemExit(f"sleep_frame_inventory_invalid:missing={missing}:extra={extra}")
    return expected


def validate(source_root: Path) -> None:
    master = source_rgba(source_root / MASTER, size=SOURCE_SIZE)
    master_alpha = master[3::4]
    source_width, source_height = SOURCE_SIZE
    source_corners = (
        master_alpha[0],
        master_alpha[source_width - 1],
        master_alpha[(source_height - 1) * source_width],
        master_alpha[-1],
    )
    if source_corners != (0, 0, 0, 0):
        raise SystemExit(f"sleep_master_corners_not_transparent:{source_corners}")
    if not any(alpha > 8 for alpha in master_alpha):
        raise SystemExit("sleep_master_empty")

    paths = require_exact_inventory(source_root / FRAME_DIRECTORY)
    infos = [frame_info(path) for path in paths]
    if any((info.width, info.height) != RUNTIME_SIZE for info in infos):
        raise SystemExit("sleep_frame_size_invalid")
    bounds = {info.bounds for info in infos}
    if len(bounds) != 1:
        raise SystemExit(f"sleep_canvas_drift:{sorted(bounds)}")

    first = rgba_pixels(paths[0])
    peak = rgba_pixels(paths[FRAME_COUNT // 2])
    last = rgba_pixels(paths[-1])
    if first != last:
        raise SystemExit("sleep_loop_seam_mismatch")
    if first == peak:
        raise SystemExit("sleep_motion_missing")

    print(
        "SLEEP_V2_VALID "
        f"frames={len(paths)} size={RUNTIME_SIZE[0]}x{RUNTIME_SIZE[1]} "
        f"bounds={infos[0].bounds}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    repository = args.repository_root.resolve()
    source_root = args.source_root.resolve() if args.source_root else repository / SOURCE_ROOT
    validate(source_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
