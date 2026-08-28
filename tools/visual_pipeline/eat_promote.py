#!/usr/bin/env python3
"""Promote the approved ``eat-v2`` source loop into the bundled visual pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path

from tools.visual_pipeline.eat_contract import (
    CHARACTER_LAYER,
    FOREGROUND_LAYER,
    FPS,
    FRAME_COUNT,
    FRAME_DIRECTORY,
    FRAME_PREFIX,
    REAR_LAYER,
    RUNTIME_FRAME_SUFFIX,
    RUNTIME_SIZE,
    SOURCE_FRAME_SUFFIX,
    SOURCE_ROOT,
    SPOON_LAYER,
)
from tools.visual_pipeline.png_rgba import source_rgba
from tools.visual_pipeline.webp_rgba import webp_rgba, write_lossless_webp

RUNTIME_DIRECTORY = Path("visual-packs/kindred-default/assets/body/eat-v2")
LEGACY_RUNTIME_DIRECTORY = Path("visual-packs/kindred-default/assets/body/frame1/eat")
MOTION_MANIFEST = Path("visual-packs/kindred-default/motions/eat.json")
RENDER_SUMMARY = SOURCE_ROOT / "RENDERED.txt"
STATIC_PROPS_PLATE = Path("layers/generated/eat-static-props-alpha-v1.png")
VISIBLE_PROPS_MASK = Path("layers/generated/eat-static-props-visible-mask-v1.png")
LOOP_PREVIEW = Path("previews/eat-v2-loop-v1.mp4")
CONTACT_SHEET = Path("previews/eat-v2-contact-sheet-v1.png")

APPROVAL_KEYS = (
    "contract",
    "fps",
    "size",
    "eat",
    "runtime_enter",
    "runtime_loop",
    "source",
    "master_sha256",
    "layers_sha256",
    "rear_sha256",
    "character_sha256",
    "spoon_sha256",
    "foreground_sha256",
    "static_props_sha256",
    "visible_props_mask_sha256",
    "loop_preview_sha256",
    "contact_sheet_sha256",
    "source_frames_sha256",
    "runtime_frames_sha256",
)


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def expected_frame_paths(
    directory: Path,
    *,
    prefix: str,
    frame_count: int = FRAME_COUNT,
    suffix: str = SOURCE_FRAME_SUFFIX,
) -> list[Path]:
    return [directory / f"{prefix}-{index:03d}{suffix}" for index in range(frame_count)]


def require_exact_inventory(
    directory: Path,
    *,
    prefix: str,
    frame_count: int = FRAME_COUNT,
    suffix: str = SOURCE_FRAME_SUFFIX,
) -> list[Path]:
    expected = expected_frame_paths(
        directory,
        prefix=prefix,
        frame_count=frame_count,
        suffix=suffix,
    )
    actual = sorted(directory.iterdir()) if directory.exists() else []
    if actual != expected:
        raise SystemExit(f"{prefix}_inventory_invalid:expected={frame_count}:actual={len(actual)}")
    return expected


def ordered_frames_digest(
    paths: Sequence[Path],
    *,
    names: Sequence[str] | None = None,
    loader: Callable[[Path], bytes] | None = None,
) -> str:
    """Hash ordered frame payloads, including each reviewed filename."""

    if names is not None and len(paths) != len(names):
        raise ValueError("ordered frame names must match the path count")
    digest = hashlib.sha256()
    for index, path in enumerate(paths):
        payload = path.read_bytes() if loader is None else loader(path)
        name = path.name if names is None else names[index]
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_approval(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line:
            continue
        key, separator, value = raw_line.partition("=")
        if not separator or not key or not value or key in values:
            raise SystemExit(f"render_approval_invalid:{line_number}")
        values[key] = value
    if tuple(values) != APPROVAL_KEYS:
        raise SystemExit("render_approval_schema_invalid")
    return values


def validate_approval(
    source_root: Path,
    source_paths: Sequence[Path],
    *,
    frame_count: int = FRAME_COUNT,
) -> dict[str, str]:
    approval = read_approval(source_root / "RENDERED.txt")
    expected_values = {
        "contract": "eat-v2-layered-loop-v1",
        "fps": str(FPS),
        "size": "512x768",
        "eat": str(frame_count),
        "runtime_enter": "0",
        "runtime_loop": str(frame_count),
        "source": str(FRAME_DIRECTORY),
        "master_sha256": _file_digest(source_root / "keys/eat-master.png"),
        "layers_sha256": _file_digest(source_root / "layers/layers.json"),
        "rear_sha256": _file_digest(source_root / REAR_LAYER),
        "character_sha256": _file_digest(source_root / CHARACTER_LAYER),
        "spoon_sha256": _file_digest(source_root / SPOON_LAYER),
        "foreground_sha256": _file_digest(source_root / FOREGROUND_LAYER),
        "static_props_sha256": _file_digest(source_root / STATIC_PROPS_PLATE),
        "visible_props_mask_sha256": _file_digest(source_root / VISIBLE_PROPS_MASK),
        "loop_preview_sha256": _file_digest(source_root / LOOP_PREVIEW),
        "contact_sheet_sha256": _file_digest(source_root / CONTACT_SHEET),
        "source_frames_sha256": ordered_frames_digest(source_paths),
        "runtime_frames_sha256": ordered_frames_digest(
            source_paths,
            names=[f"eat-{index:03d}{RUNTIME_FRAME_SUFFIX}" for index in range(frame_count)],
            loader=lambda path: source_rgba(path, size=RUNTIME_SIZE),
        ),
    }
    for key, expected in expected_values.items():
        if approval[key] != expected:
            raise SystemExit(
                f"render_approval_mismatch:{key}:expected={approval[key]}:actual={expected}"
            )
    return approval


def motion_payload(*, frame_count: int = FRAME_COUNT) -> dict[str, object]:
    return {
        "schema_version": 1,
        "fps": FPS,
        "enter": [],
        "loop": [
            f"assets/body/eat-v2/eat-{index:03d}{RUNTIME_FRAME_SUFFIX}"
            for index in range(frame_count)
        ],
    }


def _write_staged_manifest(path: Path, *, frame_count: int) -> None:
    path.write_text(
        json.dumps(motion_payload(frame_count=frame_count), indent=2) + "\n",
        encoding="utf-8",
    )


def promote(repository: Path, *, frame_count: int = FRAME_COUNT) -> None:
    source_root = repository / SOURCE_ROOT
    source_directory = source_root / FRAME_DIRECTORY
    runtime_directory = repository / RUNTIME_DIRECTORY
    legacy_directory = repository / LEGACY_RUNTIME_DIRECTORY
    motion_manifest = repository / MOTION_MANIFEST

    expected_sources = require_exact_inventory(
        source_directory,
        prefix=FRAME_PREFIX,
        frame_count=frame_count,
    )
    for source in expected_sources:
        source_rgba(source, size=RUNTIME_SIZE)
    approval = validate_approval(source_root, expected_sources, frame_count=frame_count)

    runtime_directory.parent.mkdir(parents=True, exist_ok=True)
    motion_manifest.parent.mkdir(parents=True, exist_ok=True)
    if runtime_directory.exists():
        unexpected = sorted(
            path.name
            for path in runtime_directory.iterdir()
            if not path.is_file() or not path.name.startswith("eat-")
        )
        if unexpected:
            raise SystemExit(f"runtime_directory_contains_unexpected_file:{unexpected[0]}")

    transaction_id = uuid.uuid4().hex
    staged_directory = Path(
        tempfile.mkdtemp(prefix=f".eat-stage-{transaction_id}-", dir=runtime_directory.parent)
    )
    backup_directory = runtime_directory.parent / f".eat-backup-{transaction_id}"
    staged_manifest = motion_manifest.parent / f".eat-{transaction_id}.json"
    previous_manifest = motion_manifest.read_bytes() if motion_manifest.exists() else None
    runtime_move_started = False
    staged_runtime_install_started = False
    promotion_succeeded = False
    try:
        for index, source in enumerate(expected_sources):
            destination = staged_directory / f"eat-{index:03d}{RUNTIME_FRAME_SUFFIX}"
            source_pixels = source_rgba(source, size=RUNTIME_SIZE)
            write_lossless_webp(destination, size=RUNTIME_SIZE, pixels=source_pixels)
            if webp_rgba(destination, size=RUNTIME_SIZE) != source_pixels:
                raise SystemExit(f"staged_runtime_pixel_mismatch:{index}")
        staged_paths = require_exact_inventory(
            staged_directory,
            prefix="eat",
            frame_count=frame_count,
            suffix=RUNTIME_FRAME_SUFFIX,
        )
        if (
            ordered_frames_digest(staged_paths, loader=webp_rgba)
            != approval["runtime_frames_sha256"]
        ):
            raise SystemExit("staged_runtime_digest_mismatch")
        _write_staged_manifest(staged_manifest, frame_count=frame_count)

        if runtime_directory.exists():
            runtime_move_started = True
            os.replace(runtime_directory, backup_directory)
        staged_runtime_install_started = True
        os.replace(staged_directory, runtime_directory)
        os.replace(staged_manifest, motion_manifest)

        runtime_paths = require_exact_inventory(
            runtime_directory,
            prefix="eat",
            frame_count=frame_count,
            suffix=RUNTIME_FRAME_SUFFIX,
        )
        if any(
            source_rgba(source, size=RUNTIME_SIZE) != webp_rgba(runtime, size=RUNTIME_SIZE)
            for source, runtime in zip(expected_sources, runtime_paths, strict=True)
        ):
            raise SystemExit("promoted_runtime_pixels_differ_from_source")
        if json.loads(motion_manifest.read_text(encoding="utf-8")) != motion_payload(
            frame_count=frame_count
        ):
            raise SystemExit("promoted_runtime_schedule_invalid")
        promotion_succeeded = True
    except BaseException:
        rollback_errors: list[str] = []
        if staged_runtime_install_started and runtime_directory.exists():
            try:
                shutil.rmtree(runtime_directory)
            except Exception as rollback_error:
                rollback_errors.append(f"runtime_cleanup:{rollback_error}")
        if runtime_move_started and backup_directory.exists() and not runtime_directory.exists():
            try:
                os.replace(backup_directory, runtime_directory)
            except Exception as rollback_error:
                rollback_errors.append(f"runtime_restore:{rollback_error}")
        try:
            if previous_manifest is None:
                motion_manifest.unlink(missing_ok=True)
            else:
                motion_manifest.write_bytes(previous_manifest)
        except Exception as rollback_error:
            rollback_errors.append(f"manifest_restore:{rollback_error}")
        if rollback_errors:
            recovery = (
                f"backup preserved at {backup_directory}"
                if backup_directory.exists()
                else "no runtime backup is available"
            )
            print(
                f"promotion rollback incomplete; {recovery}; errors={';'.join(rollback_errors)}",
                file=sys.stderr,
            )
        raise
    finally:
        if staged_directory.exists():
            shutil.rmtree(staged_directory)
        if promotion_succeeded and backup_directory.exists():
            shutil.rmtree(backup_directory)
        staged_manifest.unlink(missing_ok=True)

    if legacy_directory.exists():
        shutil.rmtree(legacy_directory)

    print(
        "EAT_V2_PROMOTED "
        f"frames={frame_count} fps={FPS} digest={approval['source_frames_sha256']} "
        f"destination={RUNTIME_DIRECTORY}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    promote(args.repository_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
