"""Shared, dependency-free contract for the approved FRAME2E draw loop."""

from __future__ import annotations

import math

FPS = 12
FRAME_COUNT = 84


def timeline(
    frame: int,
    frame_count: int = FRAME_COUNT,
    fps: int = FPS,
) -> tuple[float, float]:
    """Return reach and paint-stroke amplitudes for the seamless loop."""

    seconds = frame / fps
    duration = frame_count / fps
    scale = duration / 7.0
    rest_one = 0.75 * scale
    reach_end = 2.35 * scale
    stroke_end = 4.15 * scale
    return_end = 5.75 * scale

    def smoothstep(edge_zero: float, edge_one: float, value: float) -> float:
        if edge_zero == edge_one:
            return float(value >= edge_one)
        amount = max(0.0, min(1.0, (value - edge_zero) / (edge_one - edge_zero)))
        return amount * amount * (3.0 - 2.0 * amount)

    if seconds < rest_one:
        return 0.0, 0.0
    if seconds < reach_end:
        return smoothstep(rest_one, reach_end, seconds), 0.0
    if seconds < stroke_end:
        phase = (seconds - reach_end) / max(stroke_end - reach_end, 1e-6)
        return 1.0, math.sin(math.pi * phase)
    if seconds < return_end:
        return 1.0 - smoothstep(stroke_end, return_end, seconds), 0.0
    return 0.0, 0.0
