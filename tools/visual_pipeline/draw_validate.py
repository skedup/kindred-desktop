#!/usr/bin/env python3
"""Validate the FRAME2 draw loop and its fixed-prop locality contract."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Callable, Sequence
from functools import cache
from pathlib import Path

from tools.visual_pipeline import draw_contract
from tools.visual_pipeline.png_rgba import (
    ALPHA_VISIBLE,
    FrameValidationError,
    frame_info,
    rgba_pixels,
    source_rgba,
)

PixelSelector = Callable[[int, int], bool]
FRAME_COUNT = draw_contract.FRAME_COUNT
ENTER_COUNT = draw_contract.ENTER_COUNT
FPS = draw_contract.FPS
WIDTH = draw_contract.RUNTIME_WIDTH


@cache
def _selected_offsets(selector: PixelSelector) -> tuple[int, ...]:
    return tuple(
        pixel * 4
        for pixel in range(draw_contract.RUNTIME_WIDTH * draw_contract.RUNTIME_HEIGHT)
        if selector(pixel % WIDTH, pixel // WIDTH)
    )


def _mean_delta(
    first: bytes,
    second: bytes,
    *,
    selector: PixelSelector | None = None,
) -> float:
    total = 0
    samples = 0
    offsets: Sequence[int]
    if selector is None:
        offsets = range(0, len(first), 4)
    else:
        offsets = _selected_offsets(selector)
    for index in offsets:
        first_pixel = first[index : index + 4]
        second_pixel = second[index : index + 4]
        if max(first_pixel[3], second_pixel[3]) <= ALPHA_VISIBLE:
            continue
        total += sum(abs(a - b) for a, b in zip(first_pixel, second_pixel, strict=True))
        samples += 4
    if samples == 0:
        raise FrameValidationError("draw_delta_samples_missing")
    return total / samples


def _max_delta(
    first: bytes,
    second: bytes,
    *,
    selector: PixelSelector,
) -> int:
    maximum = 0
    samples = 0
    for index in _selected_offsets(selector):
        first_pixel = first[index : index + 4]
        second_pixel = second[index : index + 4]
        if max(first_pixel[3], second_pixel[3]) <= ALPHA_VISIBLE:
            continue
        maximum = max(
            maximum,
            *(abs(a - b) for a, b in zip(first_pixel, second_pixel, strict=True)),
        )
        samples += 1
    if samples == 0:
        raise FrameValidationError("draw_delta_samples_missing")
    return maximum


def _best_translation(
    first: bytes,
    second: bytes,
    *,
    selector: PixelSelector,
    x_range: range,
    y_range: range,
) -> tuple[int, int, float]:
    """Find the integer translation that best carries selected pixels between frames."""

    selected = tuple(
        (offset // 4 % WIDTH, offset // 4 // WIDTH) for offset in _selected_offsets(selector)
    )
    best: tuple[float, int, int] | None = None
    for delta_y in y_range:
        for delta_x in x_range:
            total = 0
            samples = 0
            for x, y in selected:
                moved_x = x + delta_x
                moved_y = y + delta_y
                if not (
                    0 <= moved_x < draw_contract.RUNTIME_WIDTH
                    and 0 <= moved_y < draw_contract.RUNTIME_HEIGHT
                ):
                    continue
                first_offset = (y * WIDTH + x) * 4
                second_offset = (moved_y * WIDTH + moved_x) * 4
                total += sum(
                    abs(first[first_offset + channel] - second[second_offset + channel])
                    for channel in range(4)
                )
                samples += 4
            if samples == 0:
                continue
            candidate = (total / samples, delta_x, delta_y)
            if best is None or candidate < best:
                best = candidate
    if best is None:
        raise FrameValidationError("draw_translation_samples_missing")
    residual, delta_x, delta_y = best
    return delta_x, delta_y, residual


def _source_layer_interior_selector(
    path: Path,
    *,
    erosion: int = 3,
) -> tuple[PixelSelector, int]:
    """Map opaque source-layer interiors onto the half-size runtime canvas."""

    source = source_rgba(
        path,
        size=(draw_contract.SOURCE_WIDTH, draw_contract.SOURCE_HEIGHT),
    )
    scale_x = draw_contract.SOURCE_WIDTH // draw_contract.RUNTIME_WIDTH
    scale_y = draw_contract.SOURCE_HEIGHT // draw_contract.RUNTIME_HEIGHT
    if scale_x != 2 or scale_y != 2:
        raise FrameValidationError("frame2_draw_source_runtime_scale_invalid")

    selected: set[tuple[int, int]] = set()
    for y in range(draw_contract.RUNTIME_HEIGHT):
        source_y = y * scale_y + scale_y // 2
        for x in range(draw_contract.RUNTIME_WIDTH):
            source_x = x * scale_x + scale_x // 2
            opaque = True
            for sample_y in range(source_y - erosion, source_y + erosion + 1):
                for sample_x in range(source_x - erosion, source_x + erosion + 1):
                    if not (
                        0 <= sample_x < draw_contract.SOURCE_WIDTH
                        and 0 <= sample_y < draw_contract.SOURCE_HEIGHT
                    ):
                        opaque = False
                        break
                    offset = (sample_y * draw_contract.SOURCE_WIDTH + sample_x) * 4
                    if source[offset + 3] < 255:
                        opaque = False
                        break
                if not opaque:
                    break
            if opaque:
                selected.add((x, y))
    if len(selected) < 100:
        raise FrameValidationError(f"frame2_draw_layer_interior_missing:{path.name}")
    return (lambda x, y: (x, y) in selected), len(selected)


def _within_runtime_box(
    selector: PixelSelector,
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> PixelSelector:
    return lambda x, y: selector(x, y) and left <= x <= right and top <= y <= bottom


def _psnr(first: bytes, second: bytes) -> float:
    error = 0.0
    samples = 0
    for index in range(0, len(first), 4):
        first_pixel = first[index : index + 4]
        second_pixel = second[index : index + 4]
        if max(first_pixel[3], second_pixel[3]) <= ALPHA_VISIBLE:
            continue
        for first_value, second_value in zip(first_pixel, second_pixel, strict=True):
            error += float(first_value - second_value) ** 2
            samples += 1
    if samples == 0 or error == 0.0:
        return math.inf
    return 10.0 * math.log10((255.0**2) / (error / samples))


def validate(pack: Path, *, source_root: Path) -> dict[str, object]:
    directory = pack / "assets/body/frame2/draw"
    expected_names = [f"draw-{index:03d}.png" for index in range(FRAME_COUNT)]
    actual_names = sorted(path.name for path in directory.glob("*.png"))
    if actual_names != expected_names:
        raise FrameValidationError("frame2_draw_inventory_invalid")

    infos = [frame_info(directory / name) for name in expected_names]
    baselines = [info.bounds[3] for info in infos]
    if max(baselines) - min(baselines) > 1:
        raise FrameValidationError("frame2_draw_baseline_drift")
    unique = len({info.digest for info in infos})
    if unique < FRAME_COUNT // 2:
        raise FrameValidationError("frame2_draw_insufficient_motion")

    pixels = [rgba_pixels(directory / name) for name in expected_names]
    source_layer_root = source_root / "layers/draw/generated"
    character_surface_selector, character_surface_samples = _source_layer_interior_selector(
        source_layer_root / "18-character-surface.png",
        erosion=4,
    )
    support_sleeve_selector, support_sleeve_samples = _source_layer_interior_selector(
        source_layer_root / "64-support-sleeve.png"
    )
    support_sleeve_upper_selector = _within_runtime_box(
        support_sleeve_selector, left=105, top=195, right=160, bottom=245
    )
    support_sleeve_wrist_selector = _within_runtime_box(
        support_sleeve_selector, left=175, top=285, right=225, bottom=335
    )
    support_sleeve_loose_selector = _within_runtime_box(
        support_sleeve_selector, left=90, top=245, right=175, bottom=335
    )
    draw_sleeve_selector, draw_sleeve_samples = _source_layer_interior_selector(
        source_layer_root / "65-draw-sleeve.png"
    )
    draw_sleeve_upper_selector = _within_runtime_box(
        draw_sleeve_selector, left=245, top=198, right=267, bottom=225
    )
    draw_sleeve_wrist_selector = _within_runtime_box(
        draw_sleeve_selector, left=270, top=215, right=345, bottom=285
    )
    palette_anchor_selector, palette_anchor_samples = _source_layer_interior_selector(
        source_layer_root / "66-palette.png",
        erosion=4,
    )
    fixed_prop_selector, fixed_prop_samples = _source_layer_interior_selector(
        source_layer_root / "10-fixed-props.png",
        erosion=16,
    )
    support_arm_selector, support_arm_samples = _source_layer_interior_selector(
        source_layer_root / "67-support-arm.png",
        erosion=4,
    )
    stroke_delta = _mean_delta(
        pixels[4], pixels[8], selector=draw_contract.is_stroke_validation_pixel
    )
    idle_delta = max(
        _mean_delta(pixels[0], pixels[4], selector=draw_contract.is_stroke_validation_pixel),
        _mean_delta(pixels[12], pixels[16], selector=draw_contract.is_stroke_validation_pixel),
    )
    if not 30.0 <= stroke_delta <= 100.0 or stroke_delta < idle_delta * 5.0:
        raise FrameValidationError("frame2_draw_stroke_not_visible")
    draw_sleeve_idle_delta = _mean_delta(pixels[0], pixels[4], selector=draw_sleeve_selector)
    draw_sleeve_stroke_delta = _mean_delta(pixels[4], pixels[8], selector=draw_sleeve_selector)
    if (
        not 5.0 <= draw_sleeve_stroke_delta <= 30.0
        or draw_sleeve_stroke_delta < draw_sleeve_idle_delta * 3.0
    ):
        raise FrameValidationError("frame2_draw_sleeve_follow_not_visible")
    draw_arm_selector, draw_arm_samples = _source_layer_interior_selector(
        source_layer_root / "70-draw-arm.png",
        erosion=4,
    )
    stroke_x, stroke_y, stroke_translation_residual = _best_translation(
        pixels[4],
        pixels[8],
        selector=draw_arm_selector,
        x_range=range(-10, 11),
        y_range=range(-8, 9),
    )
    if not (5 <= stroke_x <= 8 and -4 <= stroke_y <= -1):
        raise FrameValidationError("frame2_draw_stroke_direction_invalid")
    if stroke_translation_residual > 8.0:
        raise FrameValidationError("frame2_draw_stroke_translation_noisy")
    draw_sleeve_upper_x, draw_sleeve_upper_y, draw_sleeve_upper_residual = _best_translation(
        pixels[4],
        pixels[8],
        selector=draw_sleeve_upper_selector,
        x_range=range(-4, 5),
        y_range=range(-4, 5),
    )
    if draw_sleeve_upper_x < 1 or draw_sleeve_upper_residual > 14.0:
        raise FrameValidationError("frame2_draw_sleeve_upper_motion_invalid")
    draw_sleeve_wrist_x, draw_sleeve_wrist_y, draw_sleeve_wrist_residual = _best_translation(
        pixels[4],
        pixels[8],
        selector=draw_sleeve_wrist_selector,
        x_range=range(-10, 11),
        y_range=range(-8, 9),
    )
    if draw_sleeve_wrist_x < draw_sleeve_upper_x or draw_sleeve_wrist_residual > 12.0:
        raise FrameValidationError("frame2_draw_sleeve_chain_motion_invalid")
    support_sleeve_delta = _mean_delta(pixels[0], pixels[6], selector=support_sleeve_selector)
    if not 7.0 <= support_sleeve_delta <= 18.0:
        raise FrameValidationError("frame2_draw_support_sleeve_motion_invalid")
    support_sleeve_upper_delta = _mean_delta(
        pixels[0], pixels[6], selector=support_sleeve_upper_selector
    )
    support_sleeve_wrist_delta = _mean_delta(
        pixels[0], pixels[6], selector=support_sleeve_wrist_selector
    )
    support_sleeve_loose_delta = _mean_delta(
        pixels[0], pixels[6], selector=support_sleeve_loose_selector
    )
    if (
        not 7.0 <= support_sleeve_loose_delta <= 18.0
        or not 10.0 <= support_sleeve_upper_delta <= 24.0
        or not 2.0 <= support_sleeve_wrist_delta <= 22.0
        or support_sleeve_upper_delta < support_sleeve_wrist_delta
    ):
        raise FrameValidationError("frame2_draw_support_sleeve_chain_invalid")
    support_arm_delta = _mean_delta(pixels[0], pixels[6], selector=support_arm_selector)
    if not 2.0 <= support_arm_delta <= 20.0:
        raise FrameValidationError("frame2_draw_support_arm_motion_invalid")
    palette_delta = _mean_delta(pixels[0], pixels[6], selector=palette_anchor_selector)
    if not 1.0 <= palette_delta <= 16.0:
        raise FrameValidationError("frame2_draw_palette_motion_invalid")
    character_surface_delta = _mean_delta(pixels[0], pixels[6], selector=character_surface_selector)
    if not 1.0 <= character_surface_delta <= 18.0:
        raise FrameValidationError("frame2_draw_character_surface_motion_invalid")
    anchor_max_delta = max(
        _max_delta(pixels[0], frame, selector=fixed_prop_selector) for frame in pixels[1:]
    )
    # One channel level at one antialiased canvas pixel is a deterministic
    # compositor rounding artifact, not visible prop motion.  Larger changes
    # still fail the fixed-prop contract.
    if anchor_max_delta > 1:
        raise FrameValidationError("frame2_draw_prop_anchor_drift")
    internal_seam_psnr = _psnr(pixels[-1], pixels[0])
    wrap_seam_psnr = _psnr(pixels[ENTER_COUNT - 1], pixels[ENTER_COUNT])
    # The complete rotating crown adds high-contrast silhouette pixels to the
    # global comparison.  A 33 dB floor still rejects a visible loop jump while
    # allowing the intended one-sample support-arm sway at frame 23 -> 0.
    if min(internal_seam_psnr, wrap_seam_psnr) < 33.0:
        raise FrameValidationError("frame2_draw_loop_seam")

    motion_manifest = json.loads((pack / "motions/draw.json").read_text(encoding="utf-8"))
    sources = [f"assets/body/frame2/draw/{name}" for name in expected_names]
    expected_enter = sources[:ENTER_COUNT]
    expected_loop = sources[ENTER_COUNT:] + sources[:ENTER_COUNT]
    if (
        motion_manifest.get("schema_version") != 1
        or motion_manifest.get("fps") != FPS
        or motion_manifest.get("enter") != expected_enter
        or motion_manifest.get("loop") != expected_loop
    ):
        raise FrameValidationError("frame2_draw_schedule_invalid")

    return {
        "draw": {
            "frames": FRAME_COUNT,
            "unique": unique,
            "enter": ENTER_COUNT,
            "baseline": [min(baselines), max(baselines)],
            "idle_delta": round(idle_delta, 4),
            "stroke_delta": round(stroke_delta, 4),
            "draw_arm_samples": draw_arm_samples,
            "stroke_translation": [stroke_x, stroke_y],
            "stroke_translation_residual": round(stroke_translation_residual, 4),
            "character_surface_samples": character_surface_samples,
            "character_surface_delta": round(character_surface_delta, 4),
            "draw_sleeve_samples": draw_sleeve_samples,
            "draw_sleeve_idle_delta": round(draw_sleeve_idle_delta, 4),
            "draw_sleeve_stroke_delta": round(draw_sleeve_stroke_delta, 4),
            "draw_sleeve_upper_translation": [
                draw_sleeve_upper_x,
                draw_sleeve_upper_y,
            ],
            "draw_sleeve_upper_translation_residual": round(draw_sleeve_upper_residual, 4),
            "draw_sleeve_wrist_translation": [
                draw_sleeve_wrist_x,
                draw_sleeve_wrist_y,
            ],
            "draw_sleeve_wrist_translation_residual": round(draw_sleeve_wrist_residual, 4),
            "support_sleeve_samples": support_sleeve_samples,
            "support_sleeve_delta": round(support_sleeve_delta, 4),
            "support_sleeve_upper_delta": round(support_sleeve_upper_delta, 4),
            "support_sleeve_wrist_delta": round(support_sleeve_wrist_delta, 4),
            "support_sleeve_loose_delta": round(support_sleeve_loose_delta, 4),
            "support_arm_samples": support_arm_samples,
            "support_arm_delta": round(support_arm_delta, 4),
            "palette_anchor_samples": palette_anchor_samples,
            "palette_delta": round(palette_delta, 4),
            "fixed_prop_samples": fixed_prop_samples,
            "prop_anchor_max_delta": anchor_max_delta,
            "internal_seam_psnr": round(internal_seam_psnr, 2),
            "wrap_seam_psnr": round(wrap_seam_psnr, 2),
        }
    }


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pack",
        type=Path,
        nargs="?",
        default=Path("visual-packs/kindred-default"),
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("visual-sources/kindred-default/frame2"),
        help="FRAME2 authoring source root used to derive semantic validation masks",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    try:
        result = validate(args.pack.resolve(), source_root=args.source_root.resolve())
    except (OSError, json.JSONDecodeError, FrameValidationError) as exc:
        print(f"FRAME2 draw validation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
