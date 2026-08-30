"""Shared, dependency-free contract for the approved ``sleep-v2`` loop."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

SOURCE_SIZE = (1024, 1536)
RUNTIME_SIZE = (512, 768)
FPS = 12
FRAME_COUNT = 72
DURATION_SECONDS = FRAME_COUNT / FPS

SOURCE_ROOT = Path("visual-sources/kindred-default/sleep-v2")
MASTER = Path("keys/sleep-master.png")
FRAME_DIRECTORY = Path("frames/scene-warp-v1")
FRAME_PREFIX = "motion"
SOURCE_FRAME_SUFFIX = ".png"
RUNTIME_FRAME_SUFFIX = ".webp"


@dataclass(frozen=True)
class SleepPose:
    """Normalized authored controls for one frame of the sleep loop."""

    breath: float
    hug: float
    leg_settle: float


def timeline(
    frame: int,
    frame_count: int = FRAME_COUNT,
    fps: int = FPS,
) -> SleepPose:
    """Return two breaths and one slow crossed-leg adjustment over six seconds."""

    if not 0 <= frame < frame_count:
        raise ValueError(f"frame outside loop: {frame}")
    if frame_count < fps * 4 or fps <= 0:
        raise ValueError("sleep timeline requires a positive FPS and at least four seconds")

    phase = frame / (frame_count - 1)
    breath = 0.5 - 0.5 * math.cos(4.0 * math.pi * phase)
    leg_settle = 0.5 - 0.5 * math.cos(2.0 * math.pi * phase)
    # The embrace follows the slower whole-loop settle, with a restrained
    # easing that keeps hands at rest longer near the loop seam.
    hug = leg_settle * leg_settle * (3.0 - 2.0 * leg_settle)

    def normalized(value: float) -> float:
        return 0.0 if abs(value) < 1e-12 else value

    return SleepPose(
        breath=normalized(breath),
        hug=normalized(hug),
        leg_settle=normalized(leg_settle),
    )
