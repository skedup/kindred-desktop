from __future__ import annotations

import pytest

from tools.visual_pipeline import walk_video_build
from tools.visual_pipeline.walk_contract import (
    SOURCE_SIZE,
    VIDEO_FPS,
    VIDEO_LOOP_END_FRAME,
    VIDEO_LOOP_FRAME_COUNT,
    VIDEO_LOOP_START_FRAME,
    VIDEO_SOURCE_FPS,
)
from tools.visual_pipeline.walk_promote import motion_payload
from tools.visual_pipeline.walk_validate import require_exact_inventory


def test_walk_v2_video_take_uses_one_closed_gait_cycle() -> None:
    assert SOURCE_SIZE == (1254, 1254)
    assert walk_video_build.SOURCE_SIZE == SOURCE_SIZE
    assert VIDEO_SOURCE_FPS == 16
    assert VIDEO_FPS == 12
    assert VIDEO_LOOP_START_FRAME == 20
    assert VIDEO_LOOP_END_FRAME == 58
    assert VIDEO_LOOP_FRAME_COUNT == 38


def test_walk_v2_inventory_requires_the_exact_numbered_png_sequence(tmp_path) -> None:
    expected = [tmp_path / f"motion-{index:03d}.png" for index in range(3)]
    for path in expected:
        path.write_bytes(b"png")

    assert require_exact_inventory(tmp_path, frame_count=3) == expected

    (tmp_path / "motion-003.png").write_bytes(b"extra")
    with pytest.raises(SystemExit, match="walk_frame_inventory_invalid"):
        require_exact_inventory(tmp_path, frame_count=3)


def test_walk_v2_motion_payload_lists_the_exact_runtime_loop() -> None:
    assert motion_payload(frame_count=3) == {
        "schema_version": 1,
        "fps": 12,
        "enter": [],
        "loop": [
            "assets/body/walk-v2/walk-000.webp",
            "assets/body/walk-v2/walk-001.webp",
            "assets/body/walk-v2/walk-002.webp",
        ],
    }
