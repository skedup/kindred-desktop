from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tools.visual_pipeline import draw_contract, draw_layered_promote, draw_layers_build
from tools.visual_pipeline.draw_layered_contract import timeline
from tools.visual_pipeline.draw_layered_promote import (
    FRAME_COUNT,
    motion_payload,
    ordered_frames_digest,
    require_exact_inventory,
    validate_approval,
)
from tools.visual_pipeline.draw_layered_validate import validate_static_prop_mask
from tools.visual_pipeline.draw_validate import _best_translation
from tools.visual_pipeline.png_rgba import RUNTIME_SIZE, write_rgba


def test_overlapping_repair_regions_keep_original_hidden_plate_authority() -> None:
    point = (600, 600)

    assert draw_layers_build._hidden_region(*point)
    assert draw_layers_build._support_hidden_region(*point)
    assert draw_layers_build.repair_plate_authority(*point) == "hidden"


def test_best_translation_reports_motion_direction() -> None:
    width = draw_contract.RUNTIME_WIDTH
    height = draw_contract.RUNTIME_HEIGHT
    first = bytearray(width * height * 4)
    second = bytearray(width * height * 4)
    points = {(100, 100), (101, 100), (100, 101), (102, 102)}
    for index, (x, y) in enumerate(sorted(points), start=1):
        color = bytes((index * 30, index * 20, index * 10, 255))
        first_offset = (y * width + x) * 4
        second_offset = ((y - 2) * width + x + 6) * 4
        first[first_offset : first_offset + 4] = color
        second[second_offset : second_offset + 4] = color

    delta_x, delta_y, residual = _best_translation(
        bytes(first),
        bytes(second),
        selector=lambda x, y: (x, y) in points,
        x_range=range(-10, 11),
        y_range=range(-8, 9),
    )

    assert (delta_x, delta_y) == (6, -2)
    assert residual == 0.0


def test_character_members_render_only_through_continuous_surface() -> None:
    manifest = draw_layers_build.layer_manifest()
    entries = {entry["name"]: entry for entry in manifest["layers"]}

    assert entries["character_surface"]["render_in_rig"] is True
    assert entries["character_surface"]["partition_member"] is False
    assert all(
        entries[name]["render_in_rig"] is False
        for name in draw_layers_build.CHARACTER_SURFACE_MEMBERS
    )
    assert not {
        "upper_seam_underlay",
        "support_wrist_underlay",
        "draw_wrist_underlay",
    }.intersection(entries)
    assert entries["hidden_underlay"]["render_in_rig"] is False
    assert entries["head_underlay"]["render_in_rig"] is True
    assert entries["canvas_underlay"]["render_in_rig"] is True


def test_palette_polygon_does_not_capture_fixed_canvas_crossbar() -> None:
    payloads, _counts = draw_layers_build.expected_layer_payloads(
        Path(__file__).resolve().parents[3]
    )
    x, y = 734, 653
    offset = (y * draw_contract.SOURCE_WIDTH + x) * 4

    assert payloads["fixed_props"][offset + 3] > 8
    assert payloads["palette"][offset + 3] == 0
    assert payloads["character_surface"][offset + 3] == 0


def test_crown_highlight_follows_head_instead_of_character_surface() -> None:
    payloads, _counts = draw_layers_build.expected_layer_payloads(
        Path(__file__).resolve().parents[3]
    )
    x, y = 344, 104
    offset = (y * draw_contract.SOURCE_WIDTH + x) * 4

    assert payloads["hair_front"][offset + 3] > 8
    assert payloads["body_base"][offset + 3] == 0
    assert payloads["character_surface"][offset + 3] == 0


def test_layered_timeline_has_rest_reach_stroke_return_and_seam() -> None:
    samples = [timeline(frame, FRAME_COUNT, 12) for frame in range(FRAME_COUNT)]

    assert samples[0] == (0.0, 0.0)
    assert samples[-1] == (0.0, 0.0)
    assert max(reach for reach, _stroke in samples) == 1.0
    assert max(stroke for _reach, stroke in samples) > 0.99
    assert all(stroke == 0.0 for _reach, stroke in samples[:29])


def test_layered_source_inventory_requires_exact_ordered_names(tmp_path: Path) -> None:
    for index in range(3):
        (tmp_path / f"motion-{index:03d}.png").write_bytes(b"frame")

    assert require_exact_inventory(
        tmp_path,
        prefix="motion",
        frame_count=3,
    ) == [tmp_path / f"motion-{index:03d}.png" for index in range(3)]

    (tmp_path / "motion-extra.png").write_bytes(b"unexpected")
    with pytest.raises(SystemExit, match="motion_inventory_invalid"):
        require_exact_inventory(tmp_path, prefix="motion", frame_count=3)


def test_layered_motion_payload_lists_the_exact_runtime_loop() -> None:
    assert motion_payload(frame_count=3) == {
        "schema_version": 1,
        "fps": 12,
        "enter": [],
        "loop": [
            "assets/body/frame2/draw/draw-000.png",
            "assets/body/frame2/draw/draw-001.png",
            "assets/body/frame2/draw/draw-002.png",
        ],
    }


def test_layered_static_prop_mask_rejects_an_interior_mutation() -> None:
    props = bytes((20, 30, 40, 255) * 10)
    reference = bytes((50, 60, 70, 255) * 10)
    mask = bytes((255, 255, 255, 255) * 10)
    changed = bytearray(reference)
    changed[4 * 5] = 51

    with pytest.raises(SystemExit, match="static_prop_mask_changed"):
        validate_static_prop_mask(props, [reference, bytes(changed)], mask)


def test_layered_ordered_digest_pins_content_and_runtime_names(tmp_path: Path) -> None:
    paths = [tmp_path / "motion-000.png", tmp_path / "motion-001.png"]
    paths[0].write_bytes(b"first")
    paths[1].write_bytes(b"second")
    source_digest = ordered_frames_digest(paths)
    runtime_digest = ordered_frames_digest(
        paths,
        names=["draw-000.png", "draw-001.png"],
    )

    assert source_digest != runtime_digest
    paths[1].write_bytes(b"changed")
    assert ordered_frames_digest(paths) != source_digest


def test_frame2e_approval_matches_all_reviewed_inputs() -> None:
    repository = Path(__file__).resolve().parents[3]
    source_root = repository / "visual-sources/kindred-default/frame2e"
    source_paths = require_exact_inventory(
        source_root / "frames/scene-warp-v5",
        prefix="motion",
    )

    approval = validate_approval(source_root, source_paths)

    assert approval["contract"] == "frame2e-layered-draw-v1"
    assert approval["source_frames_sha256"] == ordered_frames_digest(source_paths)


def _prepare_layered_promotion_repository(
    tmp_path: Path,
) -> tuple[Path, Path, Path, bytes]:
    frame_count = 2
    source_root = tmp_path / "visual-sources/kindred-default/frame2e"
    source_directory = source_root / "frames/scene-warp-v5"
    runtime_directory = tmp_path / "visual-packs/kindred-default/assets/body/frame2/draw"
    motion_manifest = tmp_path / "visual-packs/kindred-default/motions/draw.json"
    source_directory.mkdir(parents=True)
    runtime_directory.mkdir(parents=True)
    motion_manifest.parent.mkdir(parents=True)

    pixels = bytearray(RUNTIME_SIZE[0] * RUNTIME_SIZE[1] * 4)
    center = ((RUNTIME_SIZE[1] // 2) * RUNTIME_SIZE[0] + RUNTIME_SIZE[0] // 2) * 4
    pixels[center : center + 4] = b"\x10\x20\x30\xff"
    for index in range(frame_count):
        write_rgba(
            source_directory / f"motion-{index:03d}.png",
            size=RUNTIME_SIZE,
            pixels=bytes(pixels),
        )

    inputs = {
        "props_sha256": source_root / "layers/draw-static-props-alpha-v1.png",
        "master_character_sha256": source_root / "keys/stable-alpha/key-00.png",
        "focused_character_sha256": (
            source_root / "layers/generated/draw-character-focused-alpha-v2.png"
        ),
        "brush_sha256": source_root / "layers/generated/draw-brush-alpha-v1.png",
        "visible_props_mask_sha256": (source_root / "layers/draw-static-props-visible-mask-v1.png"),
    }
    for index, path in enumerate(inputs.values()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"input-{index}".encode())

    source_paths = require_exact_inventory(
        source_directory,
        prefix="motion",
        frame_count=frame_count,
    )
    approval = {
        "contract": "frame2e-layered-draw-v1",
        "fps": "12",
        "size": "512x768",
        "draw": str(frame_count),
        "runtime_enter": "0",
        "runtime_loop": str(frame_count),
        "source": "frames/scene-warp-v5",
        **{key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in inputs.items()},
        "source_frames_sha256": ordered_frames_digest(source_paths),
        "runtime_frames_sha256": ordered_frames_digest(
            source_paths,
            names=[f"draw-{index:03d}.png" for index in range(frame_count)],
        ),
    }
    (source_root / "RENDERED.txt").write_text(
        "".join(f"{key}={value}\n" for key, value in approval.items()),
        encoding="utf-8",
    )

    previous_frame = runtime_directory / "draw-000.png"
    previous_frame.write_bytes(b"previous-runtime")
    previous_manifest = {"previous": True}
    motion_manifest.write_text(json.dumps(previous_manifest), encoding="utf-8")
    return runtime_directory, motion_manifest, previous_frame, motion_manifest.read_bytes()


def test_layered_promotion_preserves_runtime_when_staging_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame_count = 2
    runtime_directory, motion_manifest, previous_frame, previous_manifest = (
        _prepare_layered_promotion_repository(tmp_path)
    )
    real_copyfile = draw_layered_promote.shutil.copyfile

    def fail_second_staged_copy(source: str | Path, destination: str | Path) -> str:
        if Path(destination).name == "draw-001.png":
            raise OSError("simulated staging copy failure")
        return real_copyfile(source, destination)

    monkeypatch.setattr(draw_layered_promote.shutil, "copyfile", fail_second_staged_copy)

    with pytest.raises(OSError, match="simulated staging copy failure"):
        draw_layered_promote.promote(tmp_path, frame_count=frame_count)

    assert previous_frame.read_bytes() == b"previous-runtime"
    assert motion_manifest.read_bytes() == previous_manifest
    assert not list(runtime_directory.parent.glob(".draw-stage-*"))
    assert not list(runtime_directory.parent.glob(".draw-backup-*"))


def test_layered_promotion_rolls_back_when_manifest_swap_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame_count = 2
    runtime_directory, motion_manifest, previous_frame, previous_manifest = (
        _prepare_layered_promotion_repository(tmp_path)
    )

    real_replace = os.replace

    def fail_manifest_swap(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == motion_manifest:
            raise OSError("simulated manifest swap failure")
        real_replace(source, destination)

    monkeypatch.setattr(draw_layered_promote.os, "replace", fail_manifest_swap)

    with pytest.raises(OSError, match="simulated manifest swap failure"):
        draw_layered_promote.promote(tmp_path, frame_count=frame_count)

    assert previous_frame.read_bytes() == b"previous-runtime"
    assert motion_manifest.read_bytes() == previous_manifest
    assert not list(runtime_directory.parent.glob(".draw-stage-*"))
    assert not list(runtime_directory.parent.glob(".draw-backup-*"))


def test_layered_promotion_preserves_backup_when_runtime_restore_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frame_count = 2
    runtime_directory, motion_manifest, _previous_frame, previous_manifest = (
        _prepare_layered_promotion_repository(tmp_path)
    )
    real_replace = os.replace

    def fail_manifest_and_runtime_restore(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        if destination_path == motion_manifest:
            raise OSError("simulated manifest swap failure")
        if source_path.name.startswith(".draw-backup-") and destination_path == runtime_directory:
            raise OSError("simulated runtime restore failure")
        real_replace(source, destination)

    monkeypatch.setattr(
        draw_layered_promote.os,
        "replace",
        fail_manifest_and_runtime_restore,
    )

    with pytest.raises(OSError, match="simulated manifest swap failure"):
        draw_layered_promote.promote(tmp_path, frame_count=frame_count)

    backups = list(runtime_directory.parent.glob(".draw-backup-*"))
    assert not runtime_directory.exists()
    assert len(backups) == 1
    assert (backups[0] / "draw-000.png").read_bytes() == b"previous-runtime"
    assert motion_manifest.read_bytes() == previous_manifest
    assert capsys.readouterr().err == (
        "promotion rollback incomplete; "
        f"backup preserved at {backups[0]}; "
        "errors=runtime_restore:simulated runtime restore failure\n"
    )
    assert not list(runtime_directory.parent.glob(".draw-stage-*"))
