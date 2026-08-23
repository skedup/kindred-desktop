#!/usr/bin/env python3
"""Validate the FRAME2-B2a-R1 continuous-surface ``draw`` source contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from tools.visual_pipeline.draw_contract import SOURCE_HEIGHT, SOURCE_WIDTH
from tools.visual_pipeline.draw_layers_build import (
    CHARACTER_SURFACE_MEMBERS,
    expected_layer_payloads,
    layer_manifest,
    repair_plate_authority,
)
from tools.visual_pipeline.png_rgba import FrameValidationError, source_rgba

SIZE = (SOURCE_WIDTH, SOURCE_HEIGHT)
MINIMUM_VISIBLE = {
    "hidden_underlay": 50_000,
    "fixed_props": 80_000,
    "canvas_underlay": 100,
    "character_surface": 250_000,
    "body_base": 200_000,
    "hair_back": 2_000,
    "head_underlay": 5_000,
    "head_face": 15_000,
    "eyes_closed": 2_000,
    "eyes_open": 2_000,
    "hair_front": 20_000,
    "support_sleeve": 10_000,
    "draw_sleeve": 8_000,
    "palette": 5_000,
    "support_arm": 4_000,
    "draw_arm": 3_000,
    "brush": 1_000,
}
ELBOW_CONTINUITY_PROBES = {
    # These source-authoritative pixels sit just outside the conservative
    # hand-authored sleeve polygons.  Leaving them in ``body_base`` makes the
    # upper/lower sleeve boundary pull apart when the sleeve deforms.
    "support_sleeve": ((326, 491),),
    "draw_sleeve": ((511, 500),),
}
HEAD_CROWN_FOLLOW_PROBES = ((344, 104), (473, 76), (539, 184))


def _visible_pixels(pixels: bytes) -> int:
    return sum(alpha > 8 for alpha in pixels[3::4])


def _over(back: bytearray, front: bytes) -> None:
    for offset in range(0, len(front), 4):
        front_alpha = front[offset + 3]
        if front_alpha == 0:
            continue
        if front_alpha == 255:
            back[offset : offset + 4] = front[offset : offset + 4]
            continue
        back_alpha = back[offset + 3]
        alpha = front_alpha + (back_alpha * (255 - front_alpha) + 127) // 255
        if alpha == 0:
            continue
        for channel in range(3):
            numerator = front[offset + channel] * front_alpha * 255 + back[
                offset + channel
            ] * back_alpha * (255 - front_alpha)
            back[offset + channel] = (numerator + alpha * 127) // (alpha * 255)
        back[offset + 3] = alpha


def validate(repository: Path) -> dict[str, object]:
    source_root = repository / "visual-sources/kindred-default/frame2"
    layer_root = source_root / "layers/draw"
    manifest_path = layer_root / "layers.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_manifest = layer_manifest()
    if manifest != expected_manifest:
        raise FrameValidationError("frame2_draw_layer_manifest_invalid")

    entries = manifest["layers"]
    expected_files = sorted(str(entry["file"]).split("/")[-1] for entry in entries)
    generated = layer_root / "generated"
    actual_files = sorted(path.name for path in generated.glob("*.png"))
    if actual_files != expected_files:
        raise FrameValidationError("frame2_draw_layer_inventory_invalid")
    if tuple(layer_root.glob("plates/*-chroma.png")):
        raise FrameValidationError("frame2_draw_raw_chroma_plate_committed")

    key = source_rgba(source_root / "keys/draw-key.png", size=SIZE)
    repair_plates = {
        "hidden": source_rgba(layer_root / "plates/hidden-clean.png", size=SIZE),
        "support": source_rgba(layer_root / "plates/support-clean.png", size=SIZE),
    }
    expected_payloads, _expected_counts = expected_layer_payloads(repository)
    layers: dict[str, bytes] = {}
    counts: dict[str, int] = {}
    digests: set[str] = set()
    for entry in entries:
        name = str(entry["name"])
        path = layer_root / str(entry["file"])
        pixels = source_rgba(path, size=SIZE)
        if pixels != expected_payloads[name]:
            raise FrameValidationError(f"frame2_draw_layer_source_mismatch:{name}")
        corner_alpha = (
            3,
            SOURCE_WIDTH * 4 - 1,
            (SOURCE_HEIGHT - 1) * SOURCE_WIDTH * 4 + 3,
            len(pixels) - 1,
        )
        if any(pixels[index] != 0 for index in corner_alpha):
            raise FrameValidationError(f"frame2_draw_layer_corner_opaque:{name}")
        visible = _visible_pixels(pixels)
        if visible < MINIMUM_VISIBLE[name]:
            raise FrameValidationError(f"frame2_draw_layer_too_small:{name}:{visible}")
        digest = hashlib.sha256(pixels).hexdigest()
        if digest in digests:
            raise FrameValidationError(f"frame2_draw_duplicate_layer:{name}")
        digests.add(digest)
        layers[name] = pixels
        counts[name] = visible

    for name, probes in ELBOW_CONTINUITY_PROBES.items():
        for x, y in probes:
            offset = (y * SOURCE_WIDTH + x) * 4
            if layers[name][offset + 3] <= 8 or layers["body_base"][offset + 3] != 0:
                raise FrameValidationError(
                    f"frame2_draw_elbow_fragment_misclassified:{name}:{x}:{y}"
                )
    for x, y in HEAD_CROWN_FOLLOW_PROBES:
        offset = (y * SOURCE_WIDTH + x) * 4
        if layers["hair_front"][offset + 3] <= 8 or layers["body_base"][offset + 3] != 0:
            raise FrameValidationError(f"frame2_draw_head_crown_fragment_misclassified:{x}:{y}")

    rendered_character_sources = {
        str(entry["name"])
        for entry in entries
        if str(entry["name"]) in CHARACTER_SURFACE_MEMBERS and entry["render_in_rig"]
    }
    if rendered_character_sources:
        raise FrameValidationError("frame2_draw_split_character_surface_rendered")
    character_entry = next(entry for entry in entries if entry["name"] == "character_surface")
    if character_entry["partition_member"] or not character_entry["render_in_rig"]:
        raise FrameValidationError("frame2_draw_character_surface_role_invalid")
    hidden_entry = next(entry for entry in entries if entry["name"] == "hidden_underlay")
    if hidden_entry["render_in_rig"] or hidden_entry["visible_in_neutral"]:
        raise FrameValidationError("frame2_draw_broad_repair_source_rendered")
    if any(
        entry["name"]
        in {
            "upper_seam_underlay",
            "support_wrist_underlay",
            "draw_wrist_underlay",
        }
        for entry in entries
    ):
        raise FrameValidationError("frame2_draw_legacy_seam_underlay_present")

    rebuilt_character = bytearray(len(key))
    for name in CHARACTER_SURFACE_MEMBERS:
        source = layers[name]
        for offset in range(0, len(source), 4):
            if source[offset + 3] > 0:
                rebuilt_character[offset : offset + 4] = source[offset : offset + 4]
    if bytes(rebuilt_character) != layers["character_surface"]:
        raise FrameValidationError("frame2_draw_character_surface_not_lossless")

    partition = bytearray(len(key))
    occupancy = bytearray(SOURCE_WIDTH * SOURCE_HEIGHT)
    for entry in entries:
        if not entry["partition_member"]:
            continue
        pixels = layers[str(entry["name"])]
        for index, alpha in enumerate(pixels[3::4]):
            if alpha == 0:
                continue
            if occupancy[index]:
                raise FrameValidationError("frame2_draw_layer_partition_overlap")
            occupancy[index] = 1
            offset = index * 4
            partition[offset : offset + 4] = pixels[offset : offset + 4]
    for offset in range(0, len(key), 4):
        original = key[offset : offset + 4]
        rebuilt = partition[offset : offset + 4]
        if original[3] > 0:
            if rebuilt != original:
                raise FrameValidationError("frame2_draw_layer_partition_not_lossless")
        elif rebuilt[3] != 0:
            raise FrameValidationError("frame2_draw_layer_partition_leaks_background")

    open_eye = layers["eyes_open"]
    closed_eye = layers["eyes_closed"]
    eye_delta = sum(abs(a - b) for a, b in zip(open_eye, closed_eye, strict=True))
    if eye_delta < 150_000:
        raise FrameValidationError("frame2_draw_closed_eye_not_distinct")

    underlay = layers["hidden_underlay"]
    repair_authority_counts = {"hidden": 0, "support": 0}
    for index in range(SOURCE_WIDTH * SOURCE_HEIGHT):
        authority = repair_plate_authority(index % SOURCE_WIDTH, index // SOURCE_WIDTH)
        if authority is None:
            continue
        offset = index * 4
        repair_pixel = repair_plates[authority][offset : offset + 4]
        expected_pixel = repair_pixel if repair_pixel[3] > 0 else b"\x00\x00\x00\x00"
        if underlay[offset : offset + 4] != expected_pixel:
            raise FrameValidationError("frame2_draw_repair_authority_invalid")
        repair_authority_counts[authority] += 1
    movable = bytearray(len(key))
    for name in (
        "hair_back",
        "head_face",
        "eyes_open",
        "hair_front",
        "character_surface",
        "brush",
    ):
        _over(movable, layers[name])
    overlap = sum(
        underlay[index * 4 + 3] > 8 and movable[index * 4 + 3] > 8
        for index in range(SOURCE_WIDTH * SOURCE_HEIGHT)
    )
    if overlap < 40_000:
        raise FrameValidationError("frame2_draw_hidden_overlap_insufficient")

    head_repair_overlap = sum(
        layers["head_underlay"][index * 4 + 3] > 8 and layers["hair_front"][index * 4 + 3] > 8
        for index in range(SOURCE_WIDTH * SOURCE_HEIGHT)
    )
    if head_repair_overlap < 5_000:
        raise FrameValidationError("frame2_draw_head_repair_overlap_insufficient")
    canvas_repair_overlap = sum(
        layers["canvas_underlay"][index * 4 + 3] > 8 and layers["brush"][index * 4 + 3] > 8
        for index in range(SOURCE_WIDTH * SOURCE_HEIGHT)
    )
    if canvas_repair_overlap < 100:
        raise FrameValidationError("frame2_draw_canvas_repair_overlap_insufficient")

    neutral = bytearray(len(key))
    for entry in entries:
        if entry["visible_in_neutral"]:
            _over(neutral, layers[str(entry["name"])])
    total_delta = 0
    samples = 0
    for offset in range(0, len(key), 4):
        if max(key[offset + 3], neutral[offset + 3]) <= 8:
            continue
        total_delta += sum(
            abs(a - b)
            for a, b in zip(key[offset : offset + 4], neutral[offset : offset + 4], strict=True)
        )
        samples += 4
    mean_delta = total_delta / samples
    if mean_delta > 1.0:
        raise FrameValidationError(f"frame2_draw_neutral_delta:{mean_delta:.4f}")

    return {
        "contract": manifest["contract"],
        "layers": len(entries),
        "counts": counts,
        "repair_authority": repair_authority_counts,
        "hidden_overlap": overlap,
        "head_repair_overlap": head_repair_overlap,
        "canvas_repair_overlap": canvas_repair_overlap,
        "eye_delta": eye_delta,
        "continuous_surface_members": list(CHARACTER_SURFACE_MEMBERS),
        "elbow_continuity_probes": sum(len(probes) for probes in ELBOW_CONTINUITY_PROBES.values()),
        "neutral_mean_delta": round(mean_delta, 4),
    }


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    try:
        result = validate(args.repository_root.resolve())
    except (OSError, json.JSONDecodeError, FrameValidationError) as exc:
        print(f"FRAME2 draw layer validation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
