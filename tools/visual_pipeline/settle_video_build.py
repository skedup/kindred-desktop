#!/usr/bin/env python3
"""Build the reviewed transparent ``settle-v2`` butterfly event from video."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from PIL import Image

from tools.visual_pipeline.settle_contract import (
    EVENT_FRAME_COUNT,
    EVENT_FRAME_DIRECTORY,
    EVENT_FRAME_PREFIX,
    FPS,
    RUNTIME_SIZE,
    SOURCE_ROOT,
    SOURCE_SIZE,
    VIDEO_ALPHA_CLEAR_CUTOFF,
    VIDEO_ALPHA_SOLID_CUTOFF,
    VIDEO_CROP_Y,
    VIDEO_DESPILL_MIX,
    VIDEO_KEY_BLEND,
    VIDEO_KEY_COLOR,
    VIDEO_KEY_SIMILARITY,
    VIDEO_PAD_X,
    VIDEO_SCALED_SIZE,
    VIDEO_SOURCE,
)

PREVIEW_DIRECTORY = Path("previews")
EVENT_PREVIEW = "settle-v2-butterfly-event-v1.mp4"
CONTACT_SHEET = "settle-v2-butterfly-contact-sheet-v1.png"


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
    size = (int(stream["width"]), int(stream["height"]))
    duration = float(payload["format"]["duration"])
    if size != SOURCE_SIZE:
        raise SystemExit(f"settle source must be {SOURCE_SIZE[0]}x{SOURCE_SIZE[1]}: {size}")
    if duration < 10.0:
        raise SystemExit(f"settle source is too short: {duration:.3f}s")


def normalize_alpha_value(value: int) -> int:
    """Restore solid materials while preserving antialiasing and sheer sleeves."""

    if value <= VIDEO_ALPHA_CLEAR_CUTOFF:
        return 0
    if value >= VIDEO_ALPHA_SOLID_CUTOFF:
        return 255
    span = VIDEO_ALPHA_SOLID_CUTOFF - VIDEO_ALPHA_CLEAR_CUTOFF
    return round((value - VIDEO_ALPHA_CLEAR_CUTOFF) * 255 / span)


def _clear_frames(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob(f"{EVENT_FRAME_PREFIX}-*.png"):
        path.unlink()


def _render_event(ffmpeg: str, source: Path, destination: Path) -> None:
    scaled_width, scaled_height = VIDEO_SCALED_SIZE
    runtime_width, runtime_height = RUNTIME_SIZE
    filters = (
        f"fps={FPS},"
        f"chromakey={VIDEO_KEY_COLOR}:{VIDEO_KEY_SIMILARITY}:{VIDEO_KEY_BLEND},"
        f"despill=green:mix={VIDEO_DESPILL_MIX},"
        "format=rgba,"
        f"scale={scaled_width}:{scaled_height}:flags=lanczos,"
        f"pad={runtime_width}:{scaled_height}:{VIDEO_PAD_X}:0:color=black@0,"
        f"crop={runtime_width}:{runtime_height}:0:{VIDEO_CROP_Y},"
        "format=rgba"
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
            "-vf",
            filters,
            "-frames:v",
            str(EVENT_FRAME_COUNT),
            "-start_number",
            "0",
            "-fps_mode",
            "passthrough",
            str(destination / f"{EVENT_FRAME_PREFIX}-%03d.png"),
        ],
        check=True,
    )


def _normalize_alpha(directory: Path) -> None:
    curve = [normalize_alpha_value(value) for value in range(256)]
    for path in sorted(directory.glob(f"{EVENT_FRAME_PREFIX}-*.png")):
        with Image.open(path) as source:
            image = source.convert("RGBA")
        image.putalpha(image.getchannel("A").point(curve))
        image.save(path, compress_level=9)
        image.close()


def _preview(ffmpeg: str, frames: Path, destination: Path) -> None:
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
            f"color=c=0x202033:s={width}x{height}:r={FPS}",
            "-framerate",
            str(FPS),
            "-i",
            str(frames / f"{EVENT_FRAME_PREFIX}-%03d.png"),
            "-filter_complex",
            "[0:v][1:v]overlay=shortest=1:format=auto,format=yuv420p[output]",
            "-map",
            "[output]",
            "-frames:v",
            str(EVENT_FRAME_COUNT),
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
            "fps=1,scale=256:384:flags=lanczos,tile=5x2",
            "-frames:v",
            "1",
            str(destination),
        ],
        check=True,
    )


def build(repository: Path, source_video: Path | None, ffmpeg_name: str, ffprobe_name: str) -> None:
    ffmpeg = _executable(ffmpeg_name)
    ffprobe = _executable(ffprobe_name)
    root = repository / SOURCE_ROOT
    source = source_video.resolve() if source_video else root / VIDEO_SOURCE
    if not source.is_file():
        raise SystemExit(f"settle source video is missing: {source}")
    _probe(ffprobe, source)

    frames = root / EVENT_FRAME_DIRECTORY
    previews = root / PREVIEW_DIRECTORY
    previews.mkdir(parents=True, exist_ok=True)
    _clear_frames(frames)
    _render_event(ffmpeg, source, frames)
    _normalize_alpha(frames)
    preview = previews / EVENT_PREVIEW
    _preview(ffmpeg, frames, preview)
    _contact_sheet(ffmpeg, preview, previews / CONTACT_SHEET)
    print(f"SETTLE_V2_BUILT frames={EVENT_FRAME_COUNT} fps={FPS} source={source} preview={preview}")


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
