"""Validate the reviewed FRAME2E source loop and its bundled runtime copy."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from tools.visual_pipeline.draw_layered_promote import (
    motion_payload,
    ordered_frames_digest,
    require_exact_inventory,
    validate_approval,
)
from tools.visual_pipeline.png_rgba import RUNTIME_SIZE, rgba_pixels, source_rgba, write_rgba

FRAME_COUNT = 84
HAND_RECT = (100, 165, 420, 350)
BODY_RECT = (75, 110, 330, 440)
LEGS_RECT = (135, 390, 455, 750)
CHEST_RECT = (150, 180, 210, 250)
INNER_SHOULDER_RECT = (220, 150, 275, 220)
VISIBLE_PROPS_MASK = Path("layers/draw-static-props-visible-mask-v1.png")
PROPS_PLATE = Path("layers/draw-static-props-alpha-v1.png")
MINIMUM_STABLE_PROP_COVERAGE = 0.70


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("visual-sources/kindred-default/frame2e"),
    )
    parser.add_argument(
        "--pack",
        type=Path,
        default=Path("visual-packs/kindred-default"),
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
    """Build the reviewed mask of prop pixels unobscured for the whole loop."""

    if not scenes or any(len(scene) != len(props) for scene in scenes):
        raise ValueError("prop mask inputs must use one shared non-empty canvas")
    mask = bytearray(len(props))
    reference = scenes[0]
    for offset in range(0, len(props), 4):
        if props[offset + 3] <= 8:
            continue
        reference_pixel = reference[offset : offset + 4]
        if all(scene[offset : offset + 4] == reference_pixel for scene in scenes[1:]):
            mask[offset : offset + 4] = b"\xff\xff\xff\xff"
    return bytes(mask)


def write_static_prop_mask(
    props_path: Path,
    scene_paths: Sequence[Path],
    destination: Path,
) -> None:
    props = rgba_pixels(props_path)
    scenes = [rgba_pixels(path) for path in scene_paths]
    mask = build_static_prop_mask(props, scenes)
    write_rgba(destination, size=RUNTIME_SIZE, pixels=mask)


def validate_static_prop_mask(
    props: bytes,
    scenes: Sequence[bytes],
    mask: bytes,
) -> tuple[int, int]:
    """Assert all approved, unobscured prop pixels remain byte-stable."""

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
    width, height = RUNTIME_SIZE
    scene_root = source_root / "frames/scene-warp-v5"
    scene_paths = require_exact_inventory(
        scene_root,
        prefix="motion",
        frame_count=frame_count,
    )
    approval = validate_approval(source_root, scene_paths, frame_count=frame_count)

    scenes = [rgba_pixels(path) for path in scene_paths]
    if scenes[0] != scenes[-1]:
        raise SystemExit("loop_seam_invalid:first_and_last_frames_differ")

    peak = scenes[frame_count // 2]
    motion_results = {}
    for name, rect, minimum in (
        ("hand", HAND_RECT, 5000),
        ("body", BODY_RECT, 5000),
        ("legs", LEGS_RECT, 3000),
    ):
        changed, maximum = _difference(_crop(scenes[0], rect), _crop(peak, rect))
        if changed < minimum or maximum < 24:
            raise SystemExit(
                f"{name}_motion_missing:changed={changed}:maximum={maximum}:minimum={minimum}"
            )
        motion_results[name] = changed

    # The bust must behave like a translated rigid core rather than stretching
    # with the painting hand. Search the small expected lean window and bound
    # the remaining pixel residual after alignment.
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
        for delta_x in range(32, 43)
        for delta_y in range(-5, 2)
    )
    if chest_alignment[0] > 4500:
        raise SystemExit(
            "chest_shape_unstable:"
            f"residual={chest_alignment[0]}:dx={chest_alignment[1]}:dy={chest_alignment[2]}"
        )

    shoulder_alignment = min(
        (
            _translated_residual(
                scenes[0],
                peak,
                INNER_SHOULDER_RECT,
                delta_x=delta_x,
                delta_y=delta_y,
            ),
            delta_x,
            delta_y,
        )
        for delta_x in range(32, 43)
        for delta_y in range(-8, 3)
    )
    if shoulder_alignment[0] > 4500:
        raise SystemExit(
            "inner_shoulder_shape_unstable:"
            f"residual={shoulder_alignment[0]}:dx={shoulder_alignment[1]}:"
            f"dy={shoulder_alignment[2]}"
        )

    # The committed semantic mask covers every prop pixel that remains visible
    # throughout the approved loop, rather than sampling a few edge rectangles.
    # Its pinned digest prevents a replacement loop from weakening the mask.
    props = source_rgba(source_root / PROPS_PLATE, size=RUNTIME_SIZE)
    visible_props_mask = source_rgba(
        source_root / VISIBLE_PROPS_MASK,
        size=RUNTIME_SIZE,
    )
    stable_prop_pixels, prop_pixels = validate_static_prop_mask(
        props,
        scenes,
        visible_props_mask,
    )

    base_hand_alpha = _crop(scenes[0], HAND_RECT)[3::4]
    base_visible = sum(alpha > 8 for alpha in base_hand_alpha)
    for index, frame in enumerate(scenes):
        visible = sum(alpha > 8 for alpha in _crop(frame, HAND_RECT)[3::4])
        if visible < base_visible * 0.85:
            raise SystemExit(f"hand_visibility_collapsed:{index}:{visible}:{base_visible}")

    # The scene composition must preserve transparent canvas corners.  This
    # catches accidental opaque preview backgrounds entering runtime sources.
    corner_offsets = (0, (width - 1) * 4, (height - 1) * width * 4, (width * height - 1) * 4)
    for index, frame in enumerate(scenes):
        if any(frame[offset + 3] != 0 for offset in corner_offsets):
            raise SystemExit(f"scene_corner_not_transparent:{index}")

    if pack is not None:
        runtime_root = pack / "assets/body/frame2/draw"
        runtime_paths = require_exact_inventory(
            runtime_root,
            prefix="draw",
            frame_count=frame_count,
        )
        if ordered_frames_digest(runtime_paths) != approval["runtime_frames_sha256"]:
            raise SystemExit("runtime_frames_digest_mismatch")
        for index, (source_path, runtime_path) in enumerate(
            zip(scene_paths, runtime_paths, strict=True)
        ):
            if source_path.read_bytes() != runtime_path.read_bytes():
                raise SystemExit(f"runtime_frame_differs_from_source:{index}")

        manifest = json.loads((pack / "motions/draw.json").read_text(encoding="utf-8"))
        if manifest != motion_payload(frame_count=frame_count):
            raise SystemExit("runtime_schedule_invalid")

    print(
        "FRAME2E_LAYERED_DRAW_VALID "
        f"frames={frame_count} props=max:0({stable_prop_pixels}/{prop_pixels}) "
        f"hand_changed={motion_results['hand']} "
        f"body_changed={motion_results['body']} legs_changed={motion_results['legs']} "
        f"chest_residual={chest_alignment[0]}@{chest_alignment[1]},{chest_alignment[2]} "
        f"shoulder_residual={shoulder_alignment[0]}@{shoulder_alignment[1]},"
        f"{shoulder_alignment[2]}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    validate(
        args.source_root.resolve(),
        pack=args.pack.resolve(),
        frame_count=args.frame_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
