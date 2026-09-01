#!/usr/bin/env python3
"""Build the reviewed walk loop from the accepted green-screen video take.

This is an offline authoring step. It normalizes the source to 12 FPS, keys the
green background, trims the best matching gait cycle, and writes a centered
transparent PNG character sequence for review. A separate promotion step
losslessly encodes the accepted sequence as the WebP frames consumed at runtime.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance

from tools.visual_pipeline.walk_contract import (
    RUNTIME_SIZE,
    SOURCE_ROOT,
    SOURCE_SIZE,
    VIDEO_ALPHA_CLEAR_CUTOFF,
    VIDEO_ALPHA_SOLID_CUTOFF,
    VIDEO_CHARACTER_FRAME_DIRECTORY,
    VIDEO_CHARACTER_OFFSET,
    VIDEO_CHARACTER_SCALE,
    VIDEO_DESPILL_MIX,
    VIDEO_FPS,
    VIDEO_FRAME_PREFIX,
    VIDEO_KEY_BLEND,
    VIDEO_KEY_COLOR,
    VIDEO_KEY_SIMILARITY,
    VIDEO_LOOP_END_FRAME,
    VIDEO_LOOP_FRAME_COUNT,
    VIDEO_LOOP_START_FRAME,
    VIDEO_SOURCE,
    VIDEO_SOURCE_FPS,
)

PREVIEW_DIRECTORY = Path("previews")
CHARACTER_PREVIEW = "walk-v2-transparent-loop-v3.mp4"
CONTACT_SHEET = "walk-v2-transparent-contact-sheet-v3.png"


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument("--source-video", type=Path)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    return parser.parse_args(argv)


def _executable(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise SystemExit(f"required executable is not available: {name}")
    return resolved


def _probe(ffprobe: str, source: Path) -> None:
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "json",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    stream = payload["streams"][0]
    width = int(stream["width"])
    height = int(stream["height"])
    duration = float(payload["format"]["duration"])
    if width != height or width < 960:
        raise SystemExit(f"walk source must be square and at least 960 px: {width}x{height}")
    required = VIDEO_LOOP_END_FRAME / VIDEO_SOURCE_FPS
    if duration < required:
        raise SystemExit(f"walk source is too short: {duration:.3f}s < {required:.3f}s")


def _clear_frames(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob(f"{VIDEO_FRAME_PREFIX}-*.png"):
        path.unlink()


def _key_filter() -> str:
    slowdown = VIDEO_SOURCE_FPS / VIDEO_FPS
    return (
        f"fps={VIDEO_SOURCE_FPS},"
        f"trim=start_frame={VIDEO_LOOP_START_FRAME}:end_frame={VIDEO_LOOP_END_FRAME},"
        f"setpts=(PTS-STARTPTS)*{slowdown:.12f},"
        f"chromakey={VIDEO_KEY_COLOR}:{VIDEO_KEY_SIMILARITY}:{VIDEO_KEY_BLEND},"
        f"despill=green:mix={VIDEO_DESPILL_MIX},"
        "format=rgba,"
        f"scale={VIDEO_CHARACTER_SCALE[0]}:{VIDEO_CHARACTER_SCALE[1]}:flags=lanczos"
    )


def _cool_hue_mask(image: Image.Image) -> Image.Image:
    hue, saturation, _ = image.convert("RGB").convert("HSV").split()

    def hue_weight(value: int) -> int:
        if value < 95 or value > 238:
            return 0
        if value < 120:
            return round(255 * (value - 95) / 25)
        if value > 215:
            return round(255 * (238 - value) / 23)
        return 255

    def saturation_weight(value: int) -> int:
        if value < 20:
            return 0
        if value > 72:
            return 255
        return round(255 * (value - 20) / 52)

    mask = ImageChops.multiply(hue.point(hue_weight), saturation.point(saturation_weight))
    return ImageChops.multiply(mask, image.getchannel("A"))


def _grade_character_frames(directory: Path) -> None:
    """Restore the reviewed deep teal/violet clothing without tinting skin."""

    for path in sorted(directory.glob(f"{VIDEO_FRAME_PREFIX}-*.png")):
        image = Image.open(path).convert("RGBA")
        rgb = image.convert("RGB")
        graded = ImageEnhance.Brightness(rgb).enhance(0.52)
        graded = ImageEnhance.Color(graded).enhance(1.28)
        output = Image.composite(graded, rgb, _cool_hue_mask(image)).convert("RGBA")
        output.putalpha(image.getchannel("A"))
        output.save(path, compress_level=9)


def normalize_alpha_value(value: int) -> int:
    """Restore solid foreground opacity while retaining a soft silhouette."""

    if value <= VIDEO_ALPHA_CLEAR_CUTOFF:
        return 0
    if value >= VIDEO_ALPHA_SOLID_CUTOFF:
        return 255
    alpha_span = VIDEO_ALPHA_SOLID_CUTOFF - VIDEO_ALPHA_CLEAR_CUTOFF
    return round((value - VIDEO_ALPHA_CLEAR_CUTOFF) * 255 / alpha_span)


def _normalize_character_alpha(directory: Path) -> None:
    alpha_curve = [normalize_alpha_value(value) for value in range(256)]
    for path in sorted(directory.glob(f"{VIDEO_FRAME_PREFIX}-*.png")):
        image = Image.open(path).convert("RGBA")
        image.putalpha(image.getchannel("A").point(alpha_curve))
        image.save(path, compress_level=9)


def _render_character(ffmpeg: str, source: Path, output: Path) -> None:
    source_width, source_height = SOURCE_SIZE
    runtime_width, runtime_height = RUNTIME_SIZE
    offset_x, offset_y = VIDEO_CHARACTER_OFFSET
    scaled_width, scaled_height = VIDEO_CHARACTER_SCALE
    crop_x = max(0, -offset_x)
    crop_y = max(0, -offset_y)
    pad_x = max(0, offset_x)
    pad_y = max(0, offset_y)
    crop_width = min(scaled_width - crop_x, source_width - pad_x)
    crop_height = min(scaled_height - crop_y, source_height - pad_y)
    filter_complex = (
        f"[0:v]{_key_filter()},"
        f"crop={crop_width}:{crop_height}:{crop_x}:{crop_y},"
        f"pad={source_width}:{source_height}:{pad_x}:{pad_y}:color=black@0.0,"
        f"scale={runtime_height}:{runtime_height}:flags=lanczos,"
        f"crop={runtime_width}:{runtime_height}:(iw-{runtime_width})/2:0,"
        "format=rgba[output]"
    )
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-filter_complex",
            filter_complex,
            "-map",
            "[output]",
            "-frames:v",
            str(VIDEO_LOOP_FRAME_COUNT),
            "-start_number",
            "0",
            "-fps_mode",
            "passthrough",
            str(output / f"{VIDEO_FRAME_PREFIX}-%03d.png"),
        ],
        check=True,
    )


def _character_preview(ffmpeg: str, frames: Path, destination: Path) -> None:
    width, height = RUNTIME_SIZE
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x202033:s={width}x{height}:r={VIDEO_FPS}",
            "-framerate",
            str(VIDEO_FPS),
            "-i",
            str(frames / f"{VIDEO_FRAME_PREFIX}-%03d.png"),
            "-filter_complex",
            "[0:v][1:v]overlay=shortest=1:format=auto,format=yuv420p[output]",
            "-map",
            "[output]",
            "-frames:v",
            str(VIDEO_LOOP_FRAME_COUNT),
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "15",
            "-movflags",
            "+faststart",
            str(destination),
        ],
        check=True,
    )


def _contact_sheet(ffmpeg: str, video: Path, destination: Path) -> None:
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            "fps=4,scale=320:480:flags=lanczos,tile=5x2",
            "-frames:v",
            "1",
            str(destination),
        ],
        check=True,
    )


def _validate_character_frames(directory: Path) -> None:
    paths = sorted(directory.glob(f"{VIDEO_FRAME_PREFIX}-*.png"))
    if len(paths) != VIDEO_LOOP_FRAME_COUNT:
        raise SystemExit(
            "walk video build wrote an unexpected frame count: "
            f"character={len(paths)} expected={VIDEO_LOOP_FRAME_COUNT}"
        )
    union: tuple[int, int, int, int] | None = None
    for path in paths:
        image = Image.open(path).convert("RGBA")
        if image.size != RUNTIME_SIZE:
            raise SystemExit(f"walk frame has unexpected size: {path} {image.size}")
        alpha = image.getchannel("A")
        width, height = RUNTIME_SIZE
        corners = ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))
        if any(alpha.getpixel(corner) for corner in corners):
            raise SystemExit(f"walk frame is not transparent at its corners: {path}")
        bounds = alpha.getbbox()
        if bounds is None:
            raise SystemExit(f"walk frame has no visible character: {path}")
        union = (
            bounds
            if union is None
            else (
                min(union[0], bounds[0]),
                min(union[1], bounds[1]),
                max(union[2], bounds[2]),
                max(union[3], bounds[3]),
            )
        )
    assert union is not None
    center_x = (union[0] + union[2]) / 2
    if not 244 <= center_x <= 268:
        raise SystemExit(f"walk character is not centered: bbox={union} center_x={center_x:.1f}")


def build(repository: Path, source_video: Path | None, ffmpeg_name: str, ffprobe_name: str) -> None:
    ffmpeg = _executable(ffmpeg_name)
    ffprobe = _executable(ffprobe_name)
    root = repository / SOURCE_ROOT
    source = source_video.resolve() if source_video else root / VIDEO_SOURCE
    if not source.is_file():
        raise SystemExit(f"walk source video is missing: {source}")
    _probe(ffprobe, source)

    character_frames = root / VIDEO_CHARACTER_FRAME_DIRECTORY
    preview_root = root / PREVIEW_DIRECTORY
    _clear_frames(character_frames)
    preview_root.mkdir(parents=True, exist_ok=True)

    _render_character(ffmpeg, source, character_frames)
    _normalize_character_alpha(character_frames)
    _grade_character_frames(character_frames)
    _validate_character_frames(character_frames)
    character_preview = preview_root / CHARACTER_PREVIEW
    _character_preview(ffmpeg, character_frames, character_preview)
    _contact_sheet(ffmpeg, character_preview, preview_root / CONTACT_SHEET)
    print(
        "WALK_V2_VIDEO "
        f"frames={VIDEO_LOOP_FRAME_COUNT} fps={VIDEO_FPS} "
        f"character={character_frames} centered=true transparent=true"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    build(
        args.repository_root.resolve(),
        args.source_video,
        args.ffmpeg,
        args.ffprobe,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
