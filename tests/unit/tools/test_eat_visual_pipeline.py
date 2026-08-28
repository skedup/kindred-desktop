from pathlib import Path

import pytest

from tools.visual_pipeline.eat_contract import (
    FPS,
    FRAME_COUNT,
    RUNTIME_SIZE,
    RUNTIME_TABLE_HORIZONTAL_INSET,
    EatPose,
    inside_table_gutter,
    runtime_inside_table_gutter,
    table_boundary_y,
    timeline,
)
from tools.visual_pipeline.eat_promote import (
    motion_payload,
    ordered_frames_digest,
    require_exact_inventory,
    validate_approval,
)
from tools.visual_pipeline.eat_validate import (
    build_static_prop_mask,
    runtime_directory,
    validate_static_prop_mask,
)
from tools.visual_pipeline.webp_rgba import webp_rgba, write_lossless_webp


def test_eat_timeline_has_rest_scoop_lift_sip_return_and_exact_seam() -> None:
    samples = [timeline(frame) for frame in range(FRAME_COUNT)]

    assert samples[0] == EatPose(0.0, 0.0, 0.0, 0.0)
    assert samples[-1] == EatPose(0.0, 0.0, 0.0, 0.0)
    assert max(pose.approach for pose in samples) > 0.99
    assert max(pose.lift for pose in samples) == 1.0
    assert max(pose.sip for pose in samples) > 0.99
    assert all(pose.lift == 0.0 for pose in samples[: FPS * 2])
    assert all(pose.lift == 0.0 for pose in samples[FPS * 6 :])


def test_eat_timeline_scales_with_frame_count_and_fps() -> None:
    samples = [timeline(frame, frame_count=42, fps=6) for frame in range(42)]

    assert samples[0] == EatPose(0.0, 0.0, 0.0, 0.0)
    assert samples[-1] == EatPose(0.0, 0.0, 0.0, 0.0)
    assert max(pose.lift for pose in samples) == 1.0


def test_eat_table_gutters_map_to_seventeen_runtime_pixels() -> None:
    assert RUNTIME_TABLE_HORIZONTAL_INSET == 17
    assert inside_table_gutter(33.0, table_boundary_y(33.0))
    assert not inside_table_gutter(35.0, table_boundary_y(35.0))
    assert not inside_table_gutter(989.0, table_boundary_y(989.0))
    assert inside_table_gutter(991.0, table_boundary_y(991.0))
    assert runtime_inside_table_gutter(16, 767)
    assert not runtime_inside_table_gutter(17, 767)
    assert not runtime_inside_table_gutter(494, 767)
    assert runtime_inside_table_gutter(495, 767)


@pytest.mark.parametrize("frame", (-1, FRAME_COUNT))
def test_eat_timeline_rejects_frames_outside_loop(frame: int) -> None:
    with pytest.raises(ValueError, match="frame outside loop"):
        timeline(frame)


def test_eat_motion_payload_lists_the_exact_runtime_loop() -> None:
    assert motion_payload(frame_count=3) == {
        "schema_version": 1,
        "fps": 12,
        "enter": [],
        "loop": [
            "assets/body/eat-v2/eat-000.webp",
            "assets/body/eat-v2/eat-001.webp",
            "assets/body/eat-v2/eat-002.webp",
        ],
    }


def test_eat_ordered_digest_pins_content_and_runtime_names(tmp_path: Path) -> None:
    paths = [tmp_path / "motion-000.png", tmp_path / "motion-001.png"]
    paths[0].write_bytes(b"first")
    paths[1].write_bytes(b"second")
    source_digest = ordered_frames_digest(paths)

    assert source_digest != ordered_frames_digest(
        paths,
        names=["eat-000.png", "eat-001.png"],
    )
    paths[1].write_bytes(b"changed")
    assert ordered_frames_digest(paths) != source_digest


def test_eat_lossless_webp_round_trip_preserves_exact_rgba(tmp_path: Path) -> None:
    width, height = RUNTIME_SIZE
    pixels = bytes((index * 17) % 256 for index in range(width * height * 4))
    destination = tmp_path / "frame.webp"

    write_lossless_webp(destination, size=RUNTIME_SIZE, pixels=pixels)

    assert webp_rgba(destination, size=RUNTIME_SIZE) == pixels


def test_eat_runtime_directory_is_resolved_inside_selected_pack(tmp_path: Path) -> None:
    pack = tmp_path / "custom-pack"

    assert runtime_directory(pack) == pack / "assets/body/eat-v2"


def test_eat_static_prop_mask_excludes_occlusion_and_rejects_mutation() -> None:
    props = bytes((20, 30, 40, 255) * 3)
    reference = bytes((20, 30, 40, 255) + (50, 60, 70, 255) + (20, 30, 40, 255))
    stable = bytes(reference)
    mask = build_static_prop_mask(props, [reference, stable])
    assert [mask[index + 3] for index in range(0, len(mask), 4)] == [255, 0, 255]

    changed = bytearray(stable)
    changed[2 * 4] = 21
    with pytest.raises(SystemExit, match="static_prop_mask_changed"):
        validate_static_prop_mask(props, [reference, bytes(changed)], mask)


def test_eat_v2_approval_matches_all_reviewed_inputs() -> None:
    repository = Path(__file__).resolve().parents[3]
    source_root = repository / "visual-sources/kindred-default/eat-v2"
    source_paths = require_exact_inventory(
        source_root / "frames/scene-warp-v1",
        prefix="motion",
    )

    approval = validate_approval(source_root, source_paths)

    assert approval["contract"] == "eat-v2-layered-loop-v1"
    assert approval["source_frames_sha256"] == ordered_frames_digest(source_paths)
