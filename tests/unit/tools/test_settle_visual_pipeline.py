from __future__ import annotations

import pytest

from tools.visual_pipeline import settle_video_build
from tools.visual_pipeline.settle_contract import (
    EVENT_FRAME_COUNT,
    FPS,
    IDLE_FRAME_COUNT,
    IDLE_FRAME_REPEATS,
    MAX_IDLE_TRANSITION_MEAN,
    REPLAY_MAX_MS,
    REPLAY_MIN_MS,
    SOURCE_SIZE,
)
from tools.visual_pipeline.settle_promote import motion_payload
from tools.visual_pipeline.settle_validate import require_exact_inventory


def test_settle_v2_contract_pins_video_and_random_replay_schedule() -> None:
    assert SOURCE_SIZE == (720, 1280)
    assert FPS == 12
    assert EVENT_FRAME_COUNT == 120
    assert IDLE_FRAME_COUNT == 18
    assert IDLE_FRAME_REPEATS == 2
    assert MAX_IDLE_TRANSITION_MEAN == 8.0
    assert (REPLAY_MIN_MS, REPLAY_MAX_MS) == (12_000, 28_000)


def test_settle_v2_alpha_curve_restores_solid_materials_and_preserves_edges() -> None:
    normalize = settle_video_build.normalize_alpha_value

    assert normalize(0) == 0
    assert normalize(8) == 0
    assert 0 < normalize(9) < normalize(96) < normalize(179) < 255
    assert normalize(180) == 255
    assert normalize(255) == 255


def test_settle_v2_inventory_requires_the_exact_numbered_png_sequence(tmp_path) -> None:
    expected = [tmp_path / f"event-{index:03d}.png" for index in range(3)]
    for path in expected:
        path.write_bytes(b"png")

    assert require_exact_inventory(tmp_path, frame_count=3) == expected

    (tmp_path / "event-003.png").write_bytes(b"extra")
    with pytest.raises(SystemExit, match="settle_frame_inventory_invalid"):
        require_exact_inventory(tmp_path, frame_count=3)


def test_settle_v2_motion_payload_combines_event_and_slow_idle() -> None:
    payload = motion_payload(frame_count=3)

    assert payload["schema_version"] == 1
    assert payload["fps"] == 12
    assert payload["enter"] == [
        "assets/body/settle-v2/settle-000.webp",
        "assets/body/settle-v2/settle-001.webp",
        "assets/body/settle-v2/settle-002.webp",
    ]
    assert len(payload["loop"]) == 36
    assert payload["loop"][:4] == [
        "assets/body/frame1/settle/settle-000.png",
        "assets/body/frame1/settle/settle-000.png",
        "assets/body/frame1/settle/settle-001.png",
        "assets/body/frame1/settle/settle-001.png",
    ]
    assert payload["replay_interval"] == {"min_ms": 12_000, "max_ms": 28_000}
