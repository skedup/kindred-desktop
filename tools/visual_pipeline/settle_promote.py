#!/usr/bin/env python3
"""Promote the approved ``settle-v2`` event and idle schedule into the visual pack."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path

from tools.visual_pipeline.png_rgba import source_rgba
from tools.visual_pipeline.settle_contract import (
    EVENT_FRAME_COUNT,
    EVENT_FRAME_DIRECTORY,
    FPS,
    IDLE_FRAME_COUNT,
    IDLE_FRAME_REPEATS,
    IDLE_REFERENCE,
    REPLAY_MAX_MS,
    REPLAY_MIN_MS,
    RUNTIME_FRAME_SUFFIX,
    RUNTIME_SIZE,
    SOURCE_ROOT,
)
from tools.visual_pipeline.settle_validate import require_exact_inventory, validate
from tools.visual_pipeline.webp_rgba import webp_rgba, write_lossless_webp

RUNTIME_DIRECTORY = Path("visual-packs/kindred-default/assets/body/settle-v2")
IDLE_RUNTIME_DIRECTORY = Path("visual-packs/kindred-default/assets/body/frame1/settle")
MOTION_MANIFEST = Path("visual-packs/kindred-default/motions/settle.json")


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def motion_payload(*, frame_count: int = EVENT_FRAME_COUNT) -> dict[str, object]:
    idle = [
        f"assets/body/frame1/settle/settle-{index:03d}.png"
        for index in range(IDLE_FRAME_COUNT)
        for _ in range(IDLE_FRAME_REPEATS)
    ]
    return {
        "schema_version": 1,
        "fps": FPS,
        "enter": [
            f"assets/body/settle-v2/settle-{index:03d}{RUNTIME_FRAME_SUFFIX}"
            for index in range(frame_count)
        ],
        "loop": idle,
        "replay_interval": {"min_ms": REPLAY_MIN_MS, "max_ms": REPLAY_MAX_MS},
    }


def _runtime_paths(directory: Path, *, frame_count: int) -> list[Path]:
    expected = [
        directory / f"settle-{index:03d}{RUNTIME_FRAME_SUFFIX}" for index in range(frame_count)
    ]
    actual = sorted(directory.iterdir()) if directory.exists() else []
    if actual != expected:
        raise SystemExit(
            f"settle_runtime_inventory_invalid:expected={frame_count}:actual={len(actual)}"
        )
    return expected


def _require_idle_frames(repository: Path) -> None:
    directory = repository / IDLE_RUNTIME_DIRECTORY
    expected = [directory / f"settle-{index:03d}.png" for index in range(IDLE_FRAME_COUNT)]
    actual = sorted(directory.glob("settle-*.png"))
    if actual != expected:
        raise SystemExit("settle_idle_inventory_invalid")


def promote(repository: Path, *, frame_count: int = EVENT_FRAME_COUNT) -> None:
    source_root = repository / SOURCE_ROOT
    validate(source_root, idle_reference=repository / IDLE_REFERENCE)
    source_paths = require_exact_inventory(
        source_root / EVENT_FRAME_DIRECTORY,
        frame_count=frame_count,
    )
    _require_idle_frames(repository)

    runtime_directory = repository / RUNTIME_DIRECTORY
    motion_manifest = repository / MOTION_MANIFEST
    runtime_directory.parent.mkdir(parents=True, exist_ok=True)
    motion_manifest.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".settle-v2-stage-", dir=runtime_directory.parent
    ) as temporary:
        temporary_root = Path(temporary)
        staged_directory = temporary_root / "settle-v2"
        staged_directory.mkdir()
        for index, source in enumerate(source_paths):
            pixels = source_rgba(source, size=RUNTIME_SIZE)
            destination = staged_directory / f"settle-{index:03d}{RUNTIME_FRAME_SUFFIX}"
            write_lossless_webp(destination, size=RUNTIME_SIZE, pixels=pixels)
            if webp_rgba(destination, size=RUNTIME_SIZE) != pixels:
                raise SystemExit(f"settle_staged_runtime_pixel_mismatch:{index}")

        _runtime_paths(staged_directory, frame_count=frame_count)
        staged_manifest = temporary_root / "settle.json"
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
            raise SystemExit(f"settle_promoted_runtime_pixel_mismatch:{index}")
    if json.loads(motion_manifest.read_text(encoding="utf-8")) != motion_payload(
        frame_count=frame_count
    ):
        raise SystemExit("settle_promoted_runtime_schedule_invalid")

    print(
        f"SETTLE_V2_PROMOTED frames={frame_count} fps={FPS} "
        f"replay={REPLAY_MIN_MS}-{REPLAY_MAX_MS}ms destination={RUNTIME_DIRECTORY}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    promote(args.repository_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
