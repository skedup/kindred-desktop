#!/usr/bin/env python3
"""Validate a bundled desktop visual pack without loading untrusted assets."""

from __future__ import annotations

import argparse
import binascii
import json
import math
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

MAX_FILES = 2_048
MAX_PACK_BYTES = 256 * 1024 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_RASTER_EDGE = 4_096
MAX_FRAMES = 600
MAX_FPS = 30

_IDENTIFIER = re.compile(r"[a-z][a-z0-9-]{0,63}")
_ACTION_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,63}")
_STATIC_SUFFIXES = frozenset({".png", ".webp", ".svg"})
_SAFE_SOURCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
_PACK_KEYS = frozenset(
    {"schema_version", "id", "identity", "fallback_motion", "action_motions", "motions"}
)
_MOTION_KEYS = frozenset(
    {"renderer", "source", "fallback_motion", "backdrop", "decoration", "reduced_motion"}
)
_REDUCED_KEYS = frozenset({"renderer", "source", "backdrop", "decoration"})
_ASSET_KEYS = frozenset({"renderer", "source"})
_FRAME_KEYS = frozenset({"schema_version", "fps", "enter", "loop", "replay_interval"})
_REPLAY_INTERVAL_KEYS = frozenset({"min_ms", "max_ms"})
_FORBIDDEN_SVG_ELEMENTS = frozenset(
    {"script", "style", "foreignObject", "animate", "animateMotion", "animateTransform", "set"}
)
_ALLOWED_SVG_ELEMENTS = frozenset(
    {"svg", "g", "path", "circle", "ellipse", "rect", "line", "polyline", "polygon"}
)
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_PNG_DEPTHS = {
    0: frozenset({1, 2, 4, 8, 16}),
    2: frozenset({8, 16}),
    3: frozenset({1, 2, 4, 8}),
    4: frozenset({8, 16}),
    6: frozenset({8, 16}),
}
_PNG_ADAM7 = (
    (0, 0, 8, 8),
    (4, 0, 8, 8),
    (0, 4, 4, 8),
    (2, 0, 4, 4),
    (0, 2, 2, 4),
    (1, 0, 2, 2),
    (0, 1, 1, 2),
)


class VisualPackError(ValueError):
    """Raised when a visual pack violates the v1 safety contract."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VisualPackError(f"duplicate_key:{key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VisualPackError(f"json_invalid:{path.name}") from exc
    if not isinstance(value, dict):
        raise VisualPackError(f"json_object_required:{path.name}")
    return value


def _exact_keys(value: Mapping[str, Any], allowed: frozenset[str], label: str) -> None:
    extra = sorted(set(value) - allowed)
    if extra:
        raise VisualPackError(f"unsupported_key:{label}:{extra[0]}")


def _identifier(value: object, label: str, *, action: bool = False) -> str:
    pattern = _ACTION_IDENTIFIER if action else _IDENTIFIER
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise VisualPackError(f"identifier_invalid:{label}")
    return value


def _local_source(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise VisualPackError(f"source_invalid:{label}")
    if (
        value.startswith("/")
        or _SAFE_SOURCE.fullmatch(value) is None
        or "\\" in value
        or "?" in value
        or "#" in value
        or "://" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise VisualPackError(f"source_not_local:{label}")
    return value


def _asset(value: object, label: str, *, static_only: bool = False) -> tuple[str, str]:
    if not isinstance(value, dict):
        raise VisualPackError(f"asset_invalid:{label}")
    _exact_keys(value, _ASSET_KEYS, label)
    renderer = value.get("renderer")
    if renderer not in {"static", "frames"} or (static_only and renderer != "static"):
        raise VisualPackError(f"renderer_invalid:{label}")
    source = _local_source(value.get("source"), label)
    suffix = Path(source).suffix.lower()
    if renderer == "frames" and suffix != ".json":
        raise VisualPackError(f"frame_manifest_required:{label}")
    if renderer == "static" and suffix not in _STATIC_SUFFIXES:
        raise VisualPackError(f"static_asset_required:{label}")
    return renderer, source


def _png_layout(
    width: int, height: int, bits_per_pixel: int, interlace: int
) -> tuple[int, tuple[int, ...]]:
    passes = ((0, 0, 1, 1),) if interlace == 0 else _PNG_ADAM7
    size = 0
    row_offsets: list[int] = []
    for x_start, y_start, x_step, y_step in passes:
        pass_width = max(0, (width - x_start + x_step - 1) // x_step)
        pass_height = max(0, (height - y_start + y_step - 1) // y_step)
        if pass_width == 0 or pass_height == 0:
            continue
        row_bytes = (pass_width * bits_per_pixel + 7) // 8
        for _ in range(pass_height):
            row_offsets.append(size)
            size += 1 + row_bytes
    return size, tuple(row_offsets)


def _read_png(path: Path) -> tuple[int, int, int, int, int, bytes]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise VisualPackError(f"png_invalid:{path.name}") from exc
    if not data.startswith(_PNG_SIGNATURE):
        raise VisualPackError(f"png_invalid:{path.name}")

    offset = len(_PNG_SIGNATURE)
    header: tuple[int, int, int, int, int] | None = None
    idat: list[bytes] = []
    seen_palette = False
    seen_idat = False
    idat_ended = False
    seen_end = False
    chunk_index = 0
    while offset < len(data):
        if offset + 12 > len(data):
            raise VisualPackError(f"png_invalid:{path.name}")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data) or len(chunk_type) != 4:
            raise VisualPackError(f"png_invalid:{path.name}")
        if any(not (65 <= value <= 90 or 97 <= value <= 122) for value in chunk_type):
            raise VisualPackError(f"png_invalid:{path.name}")
        payload = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length : chunk_end])[0]
        actual_crc = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise VisualPackError(f"png_invalid:{path.name}")
        if chunk_index == 0 and chunk_type != b"IHDR":
            raise VisualPackError(f"png_invalid:{path.name}")
        if chunk_type[0] <= 90 and chunk_type not in {b"IHDR", b"PLTE", b"IDAT", b"IEND"}:
            raise VisualPackError(f"png_invalid:{path.name}")

        if chunk_type == b"IHDR":
            if header is not None or length != 13:
                raise VisualPackError(f"png_invalid:{path.name}")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if (
                width < 1
                or height < 1
                or width > MAX_RASTER_EDGE
                or height > MAX_RASTER_EDGE
                or color_type not in _PNG_DEPTHS
                or bit_depth not in _PNG_DEPTHS[color_type]
                or compression != 0
                or filtering != 0
                or interlace not in {0, 1}
            ):
                raise VisualPackError(f"png_invalid:{path.name}")
            header = (width, height, bit_depth, color_type, interlace)
        elif chunk_type == b"PLTE":
            if seen_palette or seen_idat or length == 0 or length % 3 or length > 768:
                raise VisualPackError(f"png_invalid:{path.name}")
            seen_palette = True
        elif chunk_type == b"IDAT":
            if header is None or idat_ended:
                raise VisualPackError(f"png_invalid:{path.name}")
            seen_idat = True
            idat.append(payload)
        elif chunk_type == b"IEND":
            if length != 0 or not seen_idat or chunk_end != len(data):
                raise VisualPackError(f"png_invalid:{path.name}")
            seen_end = True
            offset = chunk_end
            break
        elif seen_idat:
            idat_ended = True

        offset = chunk_end
        chunk_index += 1

    if header is None or not seen_end:
        raise VisualPackError(f"png_invalid:{path.name}")
    width, height, bit_depth, color_type, interlace = header
    if color_type == 3 and not seen_palette:
        raise VisualPackError(f"png_invalid:{path.name}")
    bits_per_pixel = _PNG_CHANNELS[color_type] * bit_depth
    expected_size, row_offsets = _png_layout(width, height, bits_per_pixel, interlace)
    inflater = zlib.decompressobj()
    try:
        decoded = inflater.decompress(b"".join(idat), expected_size + 1)
    except zlib.error as exc:
        raise VisualPackError(f"png_invalid:{path.name}") from exc
    if (
        len(decoded) != expected_size
        or not inflater.eof
        or inflater.unconsumed_tail
        or inflater.unused_data
        or any(decoded[row_offset] > 4 for row_offset in row_offsets)
    ):
        raise VisualPackError(f"png_invalid:{path.name}")
    return width, height, bit_depth, color_type, interlace, decoded


def _read_png_dimensions(path: Path) -> tuple[int, int]:
    width, height, _, _, _, _ = _read_png(path)
    return width, height


def _decode_png_rgba8(path: Path) -> tuple[int, int, bytes]:
    width, height, bit_depth, color_type, interlace, decoded = _read_png(path)
    if bit_depth != 8 or color_type != 6 or interlace != 0:
        raise VisualPackError(f"png_rgba8_required:{path.name}")

    stride = width * 4
    offset = 0
    previous = bytearray(stride)
    pixels = bytearray()

    def paeth(left: int, above: int, upper_left: int) -> int:
        estimate = left + above - upper_left
        left_distance = abs(estimate - left)
        above_distance = abs(estimate - above)
        upper_left_distance = abs(estimate - upper_left)
        if left_distance <= above_distance and left_distance <= upper_left_distance:
            return left
        if above_distance <= upper_left_distance:
            return above
        return upper_left

    for _ in range(height):
        filter_type = decoded[offset]
        row = bytearray(decoded[offset + 1 : offset + 1 + stride])
        for index, value in enumerate(row):
            left = row[index - 4] if index >= 4 else 0
            above = previous[index]
            upper_left = previous[index - 4] if index >= 4 else 0
            if filter_type == 1:
                row[index] = (value + left) & 0xFF
            elif filter_type == 2:
                row[index] = (value + above) & 0xFF
            elif filter_type == 3:
                row[index] = (value + ((left + above) // 2)) & 0xFF
            elif filter_type == 4:
                row[index] = (value + paeth(left, above, upper_left)) & 0xFF
        pixels.extend(row)
        previous = row
        offset += stride + 1
    return width, height, bytes(pixels)


def _read_webp_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise VisualPackError(f"webp_invalid:{path.name}")
    chunk = data[12:16]
    if chunk == b"VP8X":
        return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
    if chunk == b"VP8L" and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
        return int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(
            data[28:30], "little"
        ) & 0x3FFF
    raise VisualPackError(f"webp_invalid:{path.name}")


def _number(value: str) -> float:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)(?:px)?\s*", value)
    if match is None:
        raise VisualPackError("svg_dimension_invalid")
    return float(match.group(1))


def _validate_svg(path: Path) -> tuple[float, float]:
    try:
        source = path.read_text(encoding="utf-8")
        if "<!DOCTYPE" in source.upper() or "<!ENTITY" in source.upper():
            raise VisualPackError(f"svg_doctype_forbidden:{path.name}")
        root = ET.fromstring(source)
    except (OSError, UnicodeError, ET.ParseError) as exc:
        raise VisualPackError(f"svg_invalid:{path.name}") from exc
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise VisualPackError(f"svg_root_invalid:{path.name}")
    if "viewBox" in root.attrib:
        values = root.attrib["viewBox"].replace(",", " ").split()
        if len(values) != 4:
            raise VisualPackError(f"svg_dimension_invalid:{path.name}")
        try:
            width, height = float(values[2]), float(values[3])
        except ValueError as exc:
            raise VisualPackError(f"svg_dimension_invalid:{path.name}") from exc
    elif "width" in root.attrib and "height" in root.attrib:
        width, height = _number(root.attrib["width"]), _number(root.attrib["height"])
    else:
        raise VisualPackError(f"svg_dimension_missing:{path.name}")
    if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
        raise VisualPackError(f"svg_dimension_invalid:{path.name}")
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        if name in _FORBIDDEN_SVG_ELEMENTS:
            raise VisualPackError(f"svg_active_content:{path.name}")
        if name not in _ALLOWED_SVG_ELEMENTS:
            raise VisualPackError(f"svg_element_unsupported:{path.name}")
        for key, value in element.attrib.items():
            local_key = key.rsplit("}", 1)[-1]
            lowered = value.lower()
            if local_key == "href" or local_key == "style" or local_key.lower().startswith("on"):
                raise VisualPackError(f"svg_active_content:{path.name}")
            if any(
                marker in lowered for marker in ("url(", "@import", "http://", "https://", "data:")
            ):
                raise VisualPackError(f"svg_external_content:{path.name}")
    return width, height


def _validate_static(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".png":
        width, height = _read_png_dimensions(path)
    elif suffix == ".webp":
        width, height = _read_webp_dimensions(path)
    elif suffix == ".svg":
        width, height = _validate_svg(path)
    else:
        raise VisualPackError(f"asset_type_invalid:{path.name}")
    if width < 1 or height < 1 or width > MAX_RASTER_EDGE or height > MAX_RASTER_EDGE:
        raise VisualPackError(f"asset_dimensions_invalid:{path.name}")


def _validate_frame_manifest(path: Path) -> set[str]:
    value = _load_json(path)
    _exact_keys(value, _FRAME_KEYS, path.name)
    fps = value.get("fps")
    if value.get("schema_version") != 1 or type(fps) is not int or not 1 <= fps <= MAX_FPS:
        raise VisualPackError(f"frame_header_invalid:{path.name}")
    enter = value.get("enter")
    loop = value.get("loop")
    if not isinstance(enter, list) or not isinstance(loop, list) or not loop:
        raise VisualPackError(f"frame_sequence_invalid:{path.name}")
    if len(enter) + len(loop) > MAX_FRAMES:
        raise VisualPackError(f"frame_limit_exceeded:{path.name}")
    replay = value.get("replay_interval")
    if replay is not None:
        if not isinstance(replay, dict):
            raise VisualPackError(f"replay_interval_invalid:{path.name}")
        _exact_keys(replay, _REPLAY_INTERVAL_KEYS, f"{path.name}:replay_interval")
        minimum = replay.get("min_ms")
        maximum = replay.get("max_ms")
        if (
            type(minimum) is not int
            or type(maximum) is not int
            or not 1_000 <= minimum <= maximum <= 300_000
            or not enter
        ):
            raise VisualPackError(f"replay_interval_invalid:{path.name}")
    return {_local_source(source, f"{path.name}:frame") for source in [*enter, *loop]}


def _require_file(root: Path, source: str) -> Path:
    path = root / source
    try:
        path.resolve(strict=False).relative_to(root.resolve())
    except ValueError as exc:
        raise VisualPackError(f"source_escape:{source}") from exc
    if not path.is_file() or path.is_symlink():
        raise VisualPackError(f"source_missing:{source}")
    return path


def _scan_pack(root: Path) -> list[Path]:
    if not root.is_dir() or root.is_symlink():
        raise VisualPackError("pack_root_invalid")
    entries = sorted(root.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise VisualPackError("symlink_forbidden")
    files = [path for path in entries if path.is_file()]
    if len(files) > MAX_FILES:
        raise VisualPackError("file_limit_exceeded")
    sizes = [path.stat().st_size for path in files]
    if any(size > MAX_FILE_BYTES for size in sizes):
        raise VisualPackError("single_file_limit_exceeded")
    if sum(sizes) > MAX_PACK_BYTES:
        raise VisualPackError("pack_size_limit_exceeded")
    return files


def validate_visual_pack(
    root: Path, *, expected_actions: Iterable[str] | None = None
) -> dict[str, int | str]:
    """Validate one visual-pack root and return a stable summary."""
    root = root.absolute()
    files = _scan_pack(root)
    root = root.resolve()
    manifest = _load_json(root / "manifest.json")
    _exact_keys(manifest, _PACK_KEYS, "manifest")
    if manifest.get("schema_version") != 1:
        raise VisualPackError("schema_version_unsupported")
    pack_id = _identifier(manifest.get("id"), "pack_id")
    _identifier(manifest.get("identity"), "identity")
    fallback = _identifier(manifest.get("fallback_motion"), "fallback_motion")
    action_motions = manifest.get("action_motions")
    motions = manifest.get("motions")
    if not isinstance(action_motions, dict) or not action_motions or not isinstance(motions, dict):
        raise VisualPackError("manifest_mapping_invalid")

    action_map: dict[str, str] = {}
    for action, motion_key in action_motions.items():
        action_map[_identifier(action, "action", action=True)] = _identifier(
            motion_key, "action_motion"
        )
    if expected_actions is not None and set(action_map) != set(expected_actions):
        raise VisualPackError("action_coverage_mismatch")

    declared: set[str] = {"manifest.json"}
    descriptors: set[tuple[str, str]] = set()
    definitions: dict[str, dict[str, Any]] = {}
    for motion_key, raw in motions.items():
        key = _identifier(motion_key, "motion_key")
        if not isinstance(raw, dict):
            raise VisualPackError(f"motion_invalid:{key}")
        _exact_keys(raw, _MOTION_KEYS, key)
        renderer, source = _asset(
            {"renderer": raw.get("renderer"), "source": raw.get("source")}, key
        )
        reduced = raw.get("reduced_motion")
        if not isinstance(reduced, dict):
            raise VisualPackError(f"reduced_motion_invalid:{key}")
        _exact_keys(reduced, _REDUCED_KEYS, f"{key}:reduced")
        reduced_renderer, reduced_source = _asset(
            {"renderer": reduced.get("renderer"), "source": reduced.get("source")},
            f"{key}:reduced",
            static_only=True,
        )
        definition = dict(raw)
        definition["renderer"] = renderer
        definition["source"] = source
        definition["reduced_renderer"] = reduced_renderer
        definition["reduced_source"] = reduced_source
        if "fallback_motion" in raw:
            definition["fallback_motion"] = _identifier(raw["fallback_motion"], f"{key}:fallback")
        for container, label in ((raw, key), (reduced, f"{key}:reduced")):
            backdrop = container.get("backdrop")
            if backdrop is not None:
                backdrop_renderer, backdrop_source = _asset(
                    backdrop, f"{label}:backdrop", static_only=True
                )
                if container is raw:
                    definition["backdrop_renderer"] = backdrop_renderer
                declared.add(backdrop_source)
                descriptors.add((backdrop_renderer, backdrop_source))
            decoration = container.get("decoration")
            if decoration is not None:
                decoration_renderer, decoration_source = _asset(
                    decoration, f"{label}:decoration", static_only=container is reduced
                )
                if container is raw:
                    definition["decoration_renderer"] = decoration_renderer
                declared.add(decoration_source)
                descriptors.add((decoration_renderer, decoration_source))
        declared.update((source, reduced_source))
        descriptors.update(((renderer, source), (reduced_renderer, reduced_source)))
        definitions[key] = definition

    if (
        fallback not in definitions
        or definitions[fallback]["renderer"] != "static"
        or definitions[fallback].get("backdrop_renderer", "static") != "static"
        or definitions[fallback].get("decoration_renderer", "static") != "static"
    ):
        raise VisualPackError("static_fallback_required")
    if any(motion_key not in definitions for motion_key in action_map.values()):
        raise VisualPackError("action_motion_undefined")

    states: dict[str, str] = {}

    def visit(key: str) -> None:
        if states.get(key) == "visiting":
            raise VisualPackError("fallback_cycle")
        if states.get(key) == "visited":
            return
        if key not in definitions:
            raise VisualPackError("fallback_undefined")
        states[key] = "visiting"
        next_key = definitions[key].get("fallback_motion")
        if next_key is None and key != fallback:
            next_key = fallback
        if isinstance(next_key, str):
            visit(next_key)
        states[key] = "visited"

    for key in definitions:
        visit(key)

    frame_sources: set[str] = set()
    for renderer, source in descriptors:
        source_path = _require_file(root, source)
        if renderer == "frames":
            frame_sources.update(_validate_frame_manifest(source_path))
        else:
            _validate_static(source_path)
    declared.update(frame_sources)
    for source in declared:
        path = _require_file(root, source)
        if path.suffix.lower() in _STATIC_SUFFIXES:
            _validate_static(path)

    metadata = {"provenance.json"} if (root / "provenance.json").is_file() else set()
    actual = {path.relative_to(root).as_posix() for path in files}
    if actual != declared | metadata:
        raise VisualPackError("undeclared_or_missing_file")
    return {
        "pack_id": pack_id,
        "actions": len(action_map),
        "motions": len(definitions),
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
    }


def _repository_actions(root: Path) -> set[str]:
    actions_root = root / "src/kindred/life_assets/actions"
    if not actions_root.is_dir():
        raise VisualPackError("repository_actions_missing")
    return {path.name for path in actions_root.iterdir() if path.is_dir()} | {"settle"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument(
        "--repository-root",
        type=Path,
        help="also require exact coverage of repository actions plus settle",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        expected = _repository_actions(args.repository_root) if args.repository_root else None
        summary = validate_visual_pack(args.pack, expected_actions=expected)
    except VisualPackError as exc:
        print(f"visual-pack invalid: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
