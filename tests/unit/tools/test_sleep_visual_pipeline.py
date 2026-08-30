import pytest

from tools.visual_pipeline.sleep_contract import FPS, FRAME_COUNT, SleepPose, timeline
from tools.visual_pipeline.sleep_promote import motion_payload


def test_sleep_timeline_has_two_breaths_one_leg_settle_and_exact_seam() -> None:
    samples = [timeline(frame) for frame in range(FRAME_COUNT)]

    assert samples[0] == SleepPose(0.0, 0.0, 0.0)
    assert samples[-1] == SleepPose(0.0, 0.0, 0.0)
    assert max(pose.breath for pose in samples) > 0.99
    assert max(pose.hug for pose in samples) > 0.99
    assert max(pose.leg_settle for pose in samples) > 0.99

    breath_peaks = sum(
        samples[index - 1].breath < samples[index].breath > samples[index + 1].breath
        for index in range(1, FRAME_COUNT - 1)
    )
    assert breath_peaks == 2


def test_sleep_timeline_scales_to_another_six_second_rate() -> None:
    samples = [timeline(frame, frame_count=36, fps=6) for frame in range(36)]

    assert samples[0] == SleepPose(0.0, 0.0, 0.0)
    assert samples[-1] == SleepPose(0.0, 0.0, 0.0)
    assert max(pose.leg_settle for pose in samples) > 0.99


@pytest.mark.parametrize("frame", (-1, FRAME_COUNT))
def test_sleep_timeline_rejects_frames_outside_loop(frame: int) -> None:
    with pytest.raises(ValueError, match="frame outside loop"):
        timeline(frame)


def test_sleep_timeline_rejects_too_short_loop() -> None:
    with pytest.raises(ValueError, match="at least four seconds"):
        timeline(0, frame_count=FPS * 3, fps=FPS)


def test_sleep_motion_payload_lists_the_exact_runtime_loop() -> None:
    assert motion_payload(frame_count=3) == {
        "schema_version": 1,
        "fps": 12,
        "enter": [],
        "loop": [
            "assets/body/sleep-v2/sleep-000.webp",
            "assets/body/sleep-v2/sleep-001.webp",
            "assets/body/sleep-v2/sleep-002.webp",
        ],
    }
