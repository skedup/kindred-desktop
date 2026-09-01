"""Tests for the bundled visual-pack validation gate."""

from __future__ import annotations

import binascii
import importlib.util
import json
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

import pytest


def _load_module() -> Any:
    script = Path(__file__).resolve().parents[3] / "scripts" / "validate_visual_pack.py"
    spec = importlib.util.spec_from_file_location("validate_visual_pack", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_pack(root: Path) -> Path:
    root.mkdir()
    (root / "neutral.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        '<circle cx="16" cy="16" r="8"/></svg>',
        encoding="utf-8",
    )
    (root / "frames.json").write_text(
        json.dumps({"schema_version": 1, "fps": 4, "enter": [], "loop": ["neutral.svg"]}),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "id": "fixture-pack",
        "identity": "fixture-resident",
        "fallback_motion": "neutral",
        "action_motions": {"walk": "walk"},
        "motions": {
            "neutral": {
                "renderer": "static",
                "source": "neutral.svg",
                "reduced_motion": {"renderer": "static", "source": "neutral.svg"},
            },
            "walk": {
                "renderer": "frames",
                "source": "frames.json",
                "fallback_motion": "neutral",
                "reduced_motion": {"renderer": "static", "source": "neutral.svg"},
            },
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _manifest(root: Path) -> dict[str, Any]:
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", checksum)


def _rgba_png(pixel: bytes = b"\x10\x20\x30\x00", *, idat: bytes | None = None) -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    compressed = zlib.compress(b"\x00" + pixel) if idat is None else idat
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )


def test_valid_pack_has_stable_summary(tmp_path: Path) -> None:
    module = _load_module()
    pack = _write_pack(tmp_path / "pack")

    result = module.validate_visual_pack(pack, expected_actions={"walk"})

    assert result["pack_id"] == "fixture-pack"
    assert result["actions"] == 1
    assert result["motions"] == 2
    assert result["files"] == 3


def test_rejects_traversal_unknown_files_and_active_svg(tmp_path: Path) -> None:
    module = _load_module()
    pack = _write_pack(tmp_path / "traversal")
    value = _manifest(pack)
    value["motions"]["neutral"]["source"] = "../neutral.svg"
    (pack / "manifest.json").write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(module.VisualPackError, match="source_not_local"):
        module.validate_visual_pack(pack)

    pack = _write_pack(tmp_path / "unknown")
    (pack / "undeclared.txt").write_text("surprise", encoding="utf-8")
    with pytest.raises(module.VisualPackError, match="undeclared_or_missing"):
        module.validate_visual_pack(pack)

    pack = _write_pack(tmp_path / "svg")
    (pack / "neutral.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><script/></svg>',
        encoding="utf-8",
    )
    with pytest.raises(module.VisualPackError, match="svg_active_content"):
        module.validate_visual_pack(pack)

    pack = _write_pack(tmp_path / "svg-handler")
    (pack / "neutral.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" onclick="run()"/>',
        encoding="utf-8",
    )
    with pytest.raises(module.VisualPackError, match="svg_active_content"):
        module.validate_visual_pack(pack)


def test_rejects_symlinks_cycles_limits_and_bad_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    pack = _write_pack(tmp_path / "symlink")
    (pack / "link.svg").symlink_to(pack / "neutral.svg")
    with pytest.raises(module.VisualPackError, match="symlink_forbidden"):
        module.validate_visual_pack(pack)

    pack = _write_pack(tmp_path / "cycle")
    value = _manifest(pack)
    value["motions"]["neutral"]["fallback_motion"] = "walk"
    (pack / "manifest.json").write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(module.VisualPackError, match="fallback_cycle"):
        module.validate_visual_pack(pack)

    pack = _write_pack(tmp_path / "limit")
    monkeypatch.setattr(module, "MAX_FILES", 2)
    with pytest.raises(module.VisualPackError, match="file_limit_exceeded"):
        module.validate_visual_pack(pack)

    monkeypatch.setattr(module, "MAX_FILES", 2_048)
    pack = _write_pack(tmp_path / "coverage")
    with pytest.raises(module.VisualPackError, match="action_coverage_mismatch"):
        module.validate_visual_pack(pack, expected_actions={"walk", "settle"})


def test_rejects_audio_and_state_derived_identity_keys(tmp_path: Path) -> None:
    module = _load_module()
    for key in ("audio", "identity_from_state"):
        pack = _write_pack(tmp_path / key)
        value = _manifest(pack)
        value[key] = "forbidden"
        (pack / "manifest.json").write_text(json.dumps(value), encoding="utf-8")
        with pytest.raises(module.VisualPackError, match="unsupported_key"):
            module.validate_visual_pack(pack)


def test_requires_complete_fallback_presentation_to_be_static(tmp_path: Path) -> None:
    module = _load_module()
    pack = _write_pack(tmp_path / "fallback-decoration")
    value = _manifest(pack)
    value["motions"]["neutral"]["decoration"] = {
        "renderer": "frames",
        "source": "frames.json",
    }
    (pack / "manifest.json").write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(module.VisualPackError, match="static_fallback_required"):
        module.validate_visual_pack(pack)


def test_accepts_declared_static_backdrops_and_rejects_animated_backdrops(tmp_path: Path) -> None:
    module = _load_module()
    pack = _write_pack(tmp_path / "static-backdrop")
    value = _manifest(pack)
    value["motions"]["walk"]["backdrop"] = {
        "renderer": "static",
        "source": "neutral.svg",
    }
    value["motions"]["walk"]["reduced_motion"]["backdrop"] = {
        "renderer": "static",
        "source": "neutral.svg",
    }
    (pack / "manifest.json").write_text(json.dumps(value), encoding="utf-8")
    assert module.validate_visual_pack(pack)["motions"] == 2

    value["motions"]["walk"]["backdrop"]["renderer"] = "frames"
    value["motions"]["walk"]["backdrop"]["source"] = "frames.json"
    (pack / "manifest.json").write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(module.VisualPackError, match="renderer_invalid"):
        module.validate_visual_pack(pack)


def test_rejects_each_resource_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    pack = _write_pack(tmp_path / "single-size")
    with monkeypatch.context() as scoped:
        scoped.setattr(module, "MAX_FILE_BYTES", 10)
        with pytest.raises(module.VisualPackError, match="single_file_limit_exceeded"):
            module.validate_visual_pack(pack)

    pack = _write_pack(tmp_path / "pack-size")
    with monkeypatch.context() as scoped:
        scoped.setattr(module, "MAX_PACK_BYTES", 10)
        with pytest.raises(module.VisualPackError, match="pack_size_limit_exceeded"):
            module.validate_visual_pack(pack)

    pack = _write_pack(tmp_path / "dimensions")
    (pack / "neutral.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4097 32"/>',
        encoding="utf-8",
    )
    with pytest.raises(module.VisualPackError, match="asset_dimensions_invalid"):
        module.validate_visual_pack(pack)


@pytest.mark.parametrize(
    ("fps", "frames", "reason"),
    [(31, ["neutral.svg"], "frame_header_invalid"), (30, ["neutral.svg"] * 601, "frame_limit")],
)
def test_rejects_frame_rate_and_count_limits(
    tmp_path: Path, fps: int, frames: list[str], reason: str
) -> None:
    module = _load_module()
    pack = _write_pack(tmp_path / f"frames-{fps}-{len(frames)}")
    (pack / "frames.json").write_text(
        json.dumps({"schema_version": 1, "fps": fps, "enter": [], "loop": frames}),
        encoding="utf-8",
    )
    with pytest.raises(module.VisualPackError, match=reason):
        module.validate_visual_pack(pack)


def test_rejects_duplicate_keys_and_encoded_paths(tmp_path: Path) -> None:
    module = _load_module()
    pack = _write_pack(tmp_path / "duplicate")
    (pack / "manifest.json").write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(module.VisualPackError, match="duplicate_key"):
        module.validate_visual_pack(pack)

    pack = _write_pack(tmp_path / "encoded")
    value = _manifest(pack)
    value["motions"]["neutral"]["source"] = "%2e%2e/neutral.svg"
    (pack / "manifest.json").write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(module.VisualPackError, match="source_not_local"):
        module.validate_visual_pack(pack)


def test_png_reader_decodes_complete_rgba_pixels(tmp_path: Path) -> None:
    module = _load_module()
    path = tmp_path / "valid.png"
    pixel = b"\x10\x20\x30\x40"
    path.write_bytes(_rgba_png(pixel))

    assert module._read_png_dimensions(path) == (1, 1)
    assert module._decode_png_rgba8(path) == (1, 1, pixel)


@pytest.mark.parametrize(
    "damage", ["truncated", "bad_crc", "bad_idat", "oversized_idat", "missing_iend"]
)
def test_png_reader_rejects_structural_and_payload_damage(tmp_path: Path, damage: str) -> None:
    module = _load_module()
    value = _rgba_png()
    if damage == "truncated":
        value = value[:-1]
    elif damage == "bad_crc":
        corrupted = bytearray(value)
        corrupted[24] ^= 0x01
        value = bytes(corrupted)
    elif damage == "bad_idat":
        value = _rgba_png(idat=b"not-zlib")
    elif damage == "oversized_idat":
        value = _rgba_png(idat=zlib.compress(b"\x00\x10\x20\x30\x00" + b"overflow" * 1024))
    else:
        value = value[:-12]
    path = tmp_path / f"{damage}.png"
    path.write_bytes(value)

    with pytest.raises(module.VisualPackError, match="png_invalid"):
        module._read_png_dimensions(path)
