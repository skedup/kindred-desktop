"""Shared source, timing, and geometry contract for the accepted ``walk-v2`` loop."""

from __future__ import annotations

from pathlib import Path

SOURCE_SIZE = (1254, 1254)
RUNTIME_SIZE = (512, 768)
SOURCE_ROOT = Path("visual-sources/kindred-default/walk-v2")

# The accepted image-to-video take is sampled at 16 FPS before trimming. Frame
# 20 (zero based) and the frame immediately after frame 57 describe the same
# gait phase, so frames [20, 58) form one closed 38-frame walking cycle. Those
# authored frames play at 12 FPS to produce a calmer walk without synthetic
# optical-flow interpolation.
VIDEO_SOURCE = Path("video-source/walk-character-green-v1.mp4")
VIDEO_CHARACTER_FRAME_DIRECTORY = Path("frames/video-character-v1")
VIDEO_FRAME_PREFIX = "motion"
VIDEO_SOURCE_FRAME_SUFFIX = ".png"
VIDEO_RUNTIME_FRAME_SUFFIX = ".webp"
VIDEO_SOURCE_FPS = 16
VIDEO_FPS = 12
VIDEO_LOOP_START_FRAME = 20
VIDEO_LOOP_END_FRAME = 58
VIDEO_LOOP_FRAME_COUNT = VIDEO_LOOP_END_FRAME - VIDEO_LOOP_START_FRAME
VIDEO_KEY_COLOR = "0x00e52f"
VIDEO_KEY_SIMILARITY = 0.24
VIDEO_KEY_BLEND = 0.10
VIDEO_DESPILL_MIX = 0.35
# Chroma-key blending is useful at the silhouette, but the accepted take also
# carried that soft alpha into solid skin, hair, and dress pixels.  Normalize
# the matte after scaling: discard key noise at/below the visibility threshold,
# preserve a graduated antialiased/translucent edge, and make confident
# foreground pixels fully opaque.
VIDEO_ALPHA_CLEAR_CUTOFF = 8
VIDEO_ALPHA_SOLID_CUTOFF = 180
VIDEO_MIN_OPAQUE_VISIBLE_RATIO = 0.80
VIDEO_MIN_VISIBLE_ALPHA_MEAN = 240.0
VIDEO_CHARACTER_SCALE = (1188, 1188)
VIDEO_CHARACTER_OFFSET = (292, 9)
