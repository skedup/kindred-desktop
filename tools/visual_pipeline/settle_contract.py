"""Shared source, timing, and geometry contract for the approved ``settle-v2`` event."""

from __future__ import annotations

from pathlib import Path

SOURCE_SIZE = (720, 1280)
RUNTIME_SIZE = (512, 768)
FPS = 12
EVENT_FRAME_COUNT = 120

SOURCE_ROOT = Path("visual-sources/kindred-default/settle-v2")
VIDEO_SOURCE = Path("video-source/settle-butterfly-green-v1.mp4")
EVENT_FRAME_DIRECTORY = Path("frames/video-event-v1")
EVENT_FRAME_PREFIX = "event"
SOURCE_FRAME_SUFFIX = ".png"
RUNTIME_FRAME_SUFFIX = ".webp"
IDLE_REFERENCE = Path("visual-packs/kindred-default/assets/body/frame1/settle/settle-000.png")

# The generated 9:16 source is fitted inside the 2:3 desktop canvas, padded with
# transparent pixels, then cropped vertically. Keeping a small margin around the
# character prevents the head and shoes from touching the runtime boundary.
VIDEO_SCALED_SIZE = (492, 874)
VIDEO_PAD_X = 10
VIDEO_CROP_Y = 62
VIDEO_KEY_COLOR = "0x00ff00"
VIDEO_KEY_SIMILARITY = 0.20
VIDEO_KEY_BLEND = 0.035
VIDEO_DESPILL_MIX = 0.35
VIDEO_ALPHA_CLEAR_CUTOFF = 8
VIDEO_ALPHA_SOLID_CUTOFF = 180
VIDEO_MIN_OPAQUE_VISIBLE_RATIO = 0.78
VIDEO_MIN_VISIBLE_ALPHA_MEAN = 238.0
MAX_IDLE_TRANSITION_MEAN = 8.0

IDLE_FRAME_COUNT = 18
IDLE_FRAME_REPEATS = 2
REPLAY_MIN_MS = 12_000
REPLAY_MAX_MS = 28_000
