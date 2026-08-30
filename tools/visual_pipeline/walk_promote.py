#!/usr/bin/env python3
"""Promote the accepted transparent ``walk-v2`` loop into the visual pack."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path

from tools.visual_pipeline.png_rgba import source_rgba
from tools.visual_pipeline.walk_contract import (
    RUNTIME_SIZE,
    SOURCE_ROOT,
    VIDEO_CHARACTER_FRAME_DIRECTORY,
    VIDEO_FPS,
    VIDEO_LOOP_FRAME_COUNT,
    VIDEO_RUNTIME_FRAME_SUFFIX,
)
from tools.visual_pipeline.walk_validate import require_exact_inventory, validate
from tools.visual_pipeline.webp_rgba import webp_rgba, write_lossless_webp

RUNTIME_DIRECTORY = Path("visual-packs/kindred-default/assets/body/walk-v2")
MOTION_MANIFEST = Path("visual-packs/kindred-default/motions/walk.json")


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def motion_payload(*, frame_count: int = VIDEO_LOOP_FRAME_COUNT) -> dict[str, object]:
    return {
        "schema_version": 1,
        "fps": VIDEO_FPS,
        "enter": [],
        "loop": [
            f"assets/body/walk-v2/walk-{index:03d}{VIDEO_RUNTIME_FRAME_SUFFIX}"
            for index in range(frame_count)
        ],
    }


def _runtime_paths(directory: Path, *, frame_count: int) -> list[Path]:
    expected = [
        directory / f"walk-{index:03d}{VIDEO_RUNTIME_FRAME_SUFFIX}" for index in range(frame_count)
    ]
    actual = sorted(directory.iterdir()) if directory.exists() else []
    if actual != expected:
        raise SystemExit(
            f"walk_runtime_inventory_invalid:expected={frame_count}:actual={len(actual)}"
        )
    return expected


def promote(repository: Path, *, frame_count: int = VIDEO_LOOP_FRAME_COUNT) -> None:
    source_root = repository / SOURCE_ROOT
    validate(source_root)
    source_paths = require_exact_inventory(
        source_root / VIDEO_CHARACTER_FRAME_DIRECTORY,
        frame_count=frame_count,
    )

    runtime_directory = repository / RUNTIME_DIRECTORY
    motion_manifest = repository / MOTION_MANIFEST
    runtime_directory.parent.mkdir(parents=True, exist_ok=True)
    motion_manifest.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".walk-v2-stage-", dir=runtime_directory.parent
    ) as temporary:
        temporary_root = Path(temporary)
        staged_directory = temporary_root / "walk-v2"
        staged_directory.mkdir()
        for index, source in enumerate(source_paths):
            pixels = source_rgba(source, size=RUNTIME_SIZE)
            destination = staged_directory / f"walk-{index:03d}{VIDEO_RUNTIME_FRAME_SUFFIX}"
            write_lossless_webp(destination, size=RUNTIME_SIZE, pixels=pixels)
            if webp_rgba(destination, size=RUNTIME_SIZE) != pixels:
                raise SystemExit(f"walk_staged_runtime_pixel_mismatch:{index}")

        _runtime_paths(staged_directory, frame_count=frame_count)
        staged_manifest = temporary_root / "walk.json"
        staged_manifest.write_text(
            json.dumps(motion_payload(frame_count=frame_count), indent=2) + "\n",
            encoding="utf-8",
        )

        if runtime_directory.exists():
            shutil.rmtree(runtime_directory)
        os.replace(staged_directory, runtime_directory)
        os.replace(staged_manifest, motion_manifest)

    runtime_paths = _runtime_paths(runtime_directory, frame_count=frame_count)
    for index, (source, runtime) in enumerate(zip(source_paths, runtime_paths, strict=True)):
        if source_rgba(source, size=RUNTIME_SIZE) != webp_rgba(runtime, size=RUNTIME_SIZE):
            raise SystemExit(f"walk_promoted_runtime_pixel_mismatch:{index}")
    if json.loads(motion_manifest.read_text(encoding="utf-8")) != motion_payload(
        frame_count=frame_count
    ):
        raise SystemExit("walk_promoted_runtime_schedule_invalid")

    print(f"WALK_V2_PROMOTED frames={frame_count} fps={VIDEO_FPS} destination={RUNTIME_DIRECTORY}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    promote(args.repository_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
