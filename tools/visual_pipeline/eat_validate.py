"""Validate the approved ``eat-v2`` source loop and bundled runtime copy."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from tools.visual_pipeline.eat_contract import (
    FRAME_COUNT,
    FRAME_DIRECTORY,
    FRAME_PREFIX,
    RUNTIME_FRAME_SUFFIX,
    RUNTIME_SIZE,
    RUNTIME_TABLE_HORIZONTAL_INSET,
    SOURCE_ROOT,
    runtime_inside_table_gutter,
)
from tools.visual_pipeline.eat_promote import (
    RUNTIME_DIRECTORY,
    STATIC_PROPS_PLATE,
    VISIBLE_PROPS_MASK,
    motion_payload,
    ordered_frames_digest,
    require_exact_inventory,
    validate_approval,
)
from tools.visual_pipeline.png_rgba import rgba_pixels, source_rgba, write_rgba
from tools.visual_pipeline.webp_rgba import webp_rgba

ACTIVE_ARM_RECT = (45, 300, 225, 575)
BODY_RECT = (145, 100, 390, 560)
SUPPORT_HAND_RECT = (215, 500, 370, 660)
CHEST_RECT = (205, 345, 285, 485)
ACTIVE_SHOULDER_RECT = (145, 315, 220, 410)
SPOON_PATH_RECT = (75, 250, 290, 560)
# The character permanently occludes the center of the chair and table plate;
# more than half of the authored prop pixels remain visible for every frame.
# Pin that large common region instead of treating covered pixels as props.
MINIMUM_STABLE_PROP_COVERAGE = 0.50


def runtime_directory(pack: Path) -> Path:
    """Resolve the eat runtime directory inside the explicitly selected pack."""

    return pack / RUNTIME_DIRECTORY.relative_to("visual-packs/kindred-default")


def _table_gutter_offsets() -> list[int]:
    runtime_width, runtime_height = RUNTIME_SIZE
    return [
        (y * runtime_width + x) * 4
        for y in range(runtime_height)
        for x in range(runtime_width)
        if runtime_inside_table_gutter(x, y)
    ]


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--pack", type=Path, default=Path("visual-packs/kindred-default"))
    parser.add_argument(
        "--source-only",
        action="store_true",
        help="validate reviewed source assets before runtime promotion",
    )
    parser.add_argument("--frame-count", type=int, default=FRAME_COUNT)
    return parser.parse_args(argv)


def _crop(pixels: bytes, rect: tuple[int, int, int, int]) -> bytes:
    width, _ = RUNTIME_SIZE
    left, top, right, bottom = rect
    rows = []
    for y in range(top, bottom):
        start = (y * width + left) * 4
        rows.append(pixels[start : start + (right - left) * 4])
    return b"".join(rows)


def _difference(first: bytes, second: bytes) -> tuple[int, int]:
    changed = 0
    maximum = 0
    for before, after in zip(first, second, strict=True):
        delta = abs(before - after)
        if delta:
            changed += 1
            maximum = max(maximum, delta)
    return changed, maximum


def _translated_residual(
    first: bytes,
    second: bytes,
    rect: tuple[int, int, int, int],
    *,
    delta_x: int,
    delta_y: int,
    threshold: int = 12,
) -> int:
    width, _ = RUNTIME_SIZE
    left, top, right, bottom = rect
    changed = 0
    for y in range(top, bottom):
        for x in range(left, right):
            before = (y * width + x) * 4
            after = ((y + delta_y) * width + x + delta_x) * 4
            changed += sum(
                abs(first[before + channel] - second[after + channel]) > threshold
                for channel in range(4)
            )
    return changed


def build_static_prop_mask(props: bytes, scenes: Sequence[bytes]) -> bytes:
    """Build the mask of fixed-prop pixels unobscured for the entire loop."""

    if not scenes or any(len(scene) != len(props) for scene in scenes):
        raise ValueError("prop mask inputs must use one shared non-empty canvas")
    mask = bytearray(len(props))
    reference = scenes[0]
    for offset in range(0, len(props), 4):
        if props[offset + 3] <= 8:
            continue
        reference_pixel = reference[offset : offset + 4]
        if reference_pixel == props[offset : offset + 4] and all(
            scene[offset : offset + 4] == reference_pixel for scene in scenes[1:]
        ):
            mask[offset : offset + 4] = b"\xff\xff\xff\xff"
    return bytes(mask)


def write_static_prop_mask(
    props_path: Path,
    scene_paths: Sequence[Path],
    destination: Path,
) -> None:
    props = rgba_pixels(props_path)
    scenes = [rgba_pixels(path) for path in scene_paths]
    write_rgba(
        destination,
        size=RUNTIME_SIZE,
        pixels=build_static_prop_mask(props, scenes),
    )


def validate_static_prop_mask(
    props: bytes,
    scenes: Sequence[bytes],
    mask: bytes,
) -> tuple[int, int]:
    """Assert every approved unobscured prop pixel remains byte-stable."""

    if not scenes or any(len(scene) != len(props) for scene in scenes) or len(mask) != len(props):
        raise SystemExit("static_prop_mask_geometry_invalid")
    prop_pixels = sum(props[offset + 3] > 8 for offset in range(0, len(props), 4))
    mask_offsets = [offset for offset in range(0, len(mask), 4) if mask[offset + 3] > 8]
    if any(mask[offset + 3] not in (0, 255) for offset in range(0, len(mask), 4)):
        raise SystemExit("static_prop_mask_not_binary")
    if len(mask_offsets) < prop_pixels * MINIMUM_STABLE_PROP_COVERAGE:
        raise SystemExit(
            f"static_prop_mask_coverage_invalid:stable={len(mask_offsets)}:props={prop_pixels}"
        )

    reference = scenes[0]
    for frame_index, scene in enumerate(scenes[1:], 1):
        for offset in mask_offsets:
            if scene[offset : offset + 4] != reference[offset : offset + 4]:
                pixel_index = offset // 4
                x = pixel_index % RUNTIME_SIZE[0]
                y = pixel_index // RUNTIME_SIZE[0]
                raise SystemExit(f"static_prop_mask_changed:frame={frame_index}:x={x}:y={y}")
    return len(mask_offsets), prop_pixels


def validate(
    source_root: Path,
    *,
    pack: Path | None = None,
    frame_count: int = FRAME_COUNT,
) -> None:
    width, _ = RUNTIME_SIZE
    scene_paths = require_exact_inventory(
        source_root / FRAME_DIRECTORY,
        prefix=FRAME_PREFIX,
        frame_count=frame_count,
    )
    approval = validate_approval(source_root, scene_paths, frame_count=frame_count)
    scenes = [rgba_pixels(path) for path in scene_paths]
    if scenes[0] != scenes[-1]:
        raise SystemExit("loop_seam_invalid:first_and_last_frames_differ")

    peak = scenes[frame_count // 2]
    motion_results: dict[str, int] = {}
    for name, rect, minimum in (
        ("active_arm", ACTIVE_ARM_RECT, 9000),
        ("body", BODY_RECT, 7000),
        ("support_hand", SUPPORT_HAND_RECT, 400),
        ("spoon_path", SPOON_PATH_RECT, 12000),
    ):
        changed, maximum = _difference(_crop(scenes[0], rect), _crop(peak, rect))
        if changed < minimum or maximum < 24:
            raise SystemExit(
                f"{name}_motion_missing:changed={changed}:maximum={maximum}:minimum={minimum}"
            )
        motion_results[name] = changed

    chest_alignment = min(
        (
            _translated_residual(
                scenes[0],
                peak,
                CHEST_RECT,
                delta_x=delta_x,
                delta_y=delta_y,
            ),
            delta_x,
            delta_y,
        )
        for delta_x in range(-6, 2)
        for delta_y in range(1, 10)
    )
    if chest_alignment[0] > 5000:
        raise SystemExit(
            "chest_shape_unstable:"
            f"residual={chest_alignment[0]}:dx={chest_alignment[1]}:dy={chest_alignment[2]}"
        )

    # At full lift the foreground hand necessarily occludes the active
    # shoulder. Probe the approach apex instead: the sleeve has moved toward
    # the bowl while the shoulder and metal arm band remain visible.
    shoulder_probe = scenes[frame_count * 3 // 14]
    shoulder_alignment = min(
        (
            _translated_residual(
                scenes[0],
                shoulder_probe,
                ACTIVE_SHOULDER_RECT,
                delta_x=delta_x,
                delta_y=delta_y,
            ),
            delta_x,
            delta_y,
        )
        for delta_x in range(-6, 2)
        for delta_y in range(0, 10)
    )
    if shoulder_alignment[0] > 2500:
        raise SystemExit(
            "active_shoulder_shape_unstable:"
            f"residual={shoulder_alignment[0]}:dx={shoulder_alignment[1]}:"
            f"dy={shoulder_alignment[2]}"
        )

    props = source_rgba(source_root / STATIC_PROPS_PLATE, size=RUNTIME_SIZE)
    visible_props_mask = source_rgba(source_root / VISIBLE_PROPS_MASK, size=RUNTIME_SIZE)
    stable_prop_pixels, prop_pixels = validate_static_prop_mask(
        props,
        scenes,
        visible_props_mask,
    )

    table_gutter_offsets = _table_gutter_offsets()
    for index, scene in enumerate(scenes):
        top_offsets = (0, (width // 2) * 4, (width - 1) * 4)
        if any(scene[offset + 3] != 0 for offset in top_offsets):
            raise SystemExit(f"scene_top_not_transparent:{index}")
        if any(scene[offset + 3] != 0 for offset in table_gutter_offsets):
            raise SystemExit(f"scene_table_gutter_not_transparent:{index}")

    if pack is not None:
        runtime_paths = require_exact_inventory(
            runtime_directory(pack),
            prefix="eat",
            frame_count=frame_count,
            suffix=RUNTIME_FRAME_SUFFIX,
        )
        if (
            ordered_frames_digest(runtime_paths, loader=webp_rgba)
            != approval["runtime_frames_sha256"]
        ):
            raise SystemExit("runtime_frames_digest_mismatch")
        for index, (source_path, runtime_path) in enumerate(
            zip(scene_paths, runtime_paths, strict=True)
        ):
            if source_rgba(source_path, size=RUNTIME_SIZE) != webp_rgba(
                runtime_path,
                size=RUNTIME_SIZE,
            ):
                raise SystemExit(f"runtime_frame_pixels_differ_from_source:{index}")

        runtime_manifest = json.loads((pack / "motions/eat.json").read_text(encoding="utf-8"))
        if runtime_manifest != motion_payload(frame_count=frame_count):
            raise SystemExit("runtime_schedule_invalid")
        pack_manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
        reduced = pack_manifest["motions"]["eat"]["reduced_motion"]
        if reduced["source"] != "assets/body/eat-v2/eat-000.webp":
            raise SystemExit("runtime_reduced_motion_invalid")

    print(
        "EAT_V2_VALID "
        f"frames={frame_count} props=max:0({stable_prop_pixels}/{prop_pixels}) "
        f"active_arm_changed={motion_results['active_arm']} "
        f"body_changed={motion_results['body']} "
        f"support_changed={motion_results['support_hand']} "
        f"spoon_path_changed={motion_results['spoon_path']} "
        f"chest_residual={chest_alignment[0]}@{chest_alignment[1]},{chest_alignment[2]} "
        f"shoulder_residual={shoulder_alignment[0]}@{shoulder_alignment[1]},"
        f"{shoulder_alignment[2]} table_gutter={RUNTIME_TABLE_HORIZONTAL_INSET}px"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    validate(
        args.source_root.resolve(),
        pack=None if args.source_only else args.pack.resolve(),
        frame_count=args.frame_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
