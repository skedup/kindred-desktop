#!/usr/bin/env python3
"""Render the continuous-surface ``sleep-v2`` preview loop.

Run through Blender, not the system Python::

    Blender --background --python tools/visual_pipeline/sleep_generate.py -- \
      --repository-root /absolute/path/to/kindred-desktop

The approved person, pillow, nightgown, robe, and legs remain one textured
surface. Broad smooth deformation fields create breathing, a gentle embrace,
and a readable crossed-leg adjustment without independently cut joints.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
from collections.abc import Sequence
from pathlib import Path

import bpy

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.visual_pipeline.blender_canvas import (  # noqa: E402
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    orthographic_camera,
    rgba_material,
    set_texture_image,
    smoothstep,
    textured_grid,
    transparent_scene,
)
from tools.visual_pipeline.png_rgba import source_rgba  # noqa: E402
from tools.visual_pipeline.sleep_contract import (  # noqa: E402
    FPS,
    FRAME_COUNT,
    FRAME_DIRECTORY,
    FRAME_PREFIX,
    MASTER,
    RUNTIME_SIZE,
    SOURCE_ROOT,
    SOURCE_SIZE,
    SleepPose,
    timeline,
)

WIDTH, HEIGHT = RUNTIME_SIZE


def _arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--frame-count", type=int, default=FRAME_COUNT)
    parser.add_argument("--fps", type=int, default=FPS)
    parser.add_argument("--preview-frame", type=int)
    if "--" not in argv:
        parser.error("arguments must follow Blender's -- separator")
    return parser.parse_args(argv[argv.index("--") + 1 :])


def _pixels(base: tuple[float, float, float]) -> tuple[float, float]:
    x, y, _ = base
    return (
        (x / CANVAS_WIDTH + 0.5) * WIDTH,
        (0.5 - y / CANVAS_HEIGHT) * HEIGHT,
    )


def _bell_2d(
    px: float,
    py: float,
    center_x: float,
    center_y: float,
    radius_x: float,
    radius_y: float,
) -> float:
    return math.exp(-(((px - center_x) / radius_x) ** 2 + ((py - center_y) / radius_y) ** 2))


def _rotation_offset(
    px: float,
    py: float,
    *,
    pivot_x: float,
    pivot_y: float,
    angle: float,
) -> tuple[float, float]:
    relative_x = px - pivot_x
    relative_y = py - pivot_y
    rotated_x = math.cos(angle) * relative_x - math.sin(angle) * relative_y
    rotated_y = math.sin(angle) * relative_x + math.cos(angle) * relative_y
    return rotated_x - relative_x, rotated_y - relative_y


def _upper_offset(px: float, py: float, pose: SleepPose) -> tuple[float, float]:
    """Let the torso breathe while the outer pillow silhouette stays calm."""

    torso = _bell_2d(px, py, 274.0, 253.0, 122.0, 134.0)
    torso *= 1.0 - smoothstep(405.0, 470.0, py)
    head_and_pillow = _bell_2d(px, py, 144.0, 139.0, 135.0, 128.0)
    head_and_pillow *= 1.0 - smoothstep(278.0, 342.0, py)

    dx = pose.breath * (0.78 * torso + 0.20 * head_and_pillow)
    dy = pose.breath * (-3.5 * torso - 0.65 * head_and_pillow)
    return dx, dy


def _embrace_offset(px: float, py: float, pose: SleepPose) -> tuple[float, float]:
    """Move both hugging sides inward with broad, seam-free influence fields."""

    outer_hand = _bell_2d(px, py, 54.0, 174.0, 50.0, 57.0)
    outer_hand *= 1.0 - smoothstep(242.0, 302.0, py)
    inner_hand = _bell_2d(px, py, 144.0, 244.0, 67.0, 62.0)
    inner_hand *= smoothstep(175.0, 212.0, py)
    inner_hand *= 1.0 - smoothstep(310.0, 355.0, py)

    dx = pose.hug * (3.4 * outer_hand - 3.8 * inner_hand)
    dy = pose.hug * (-1.2 * outer_hand - 2.7 * inner_hand)
    return dx, dy


def _leg_offset(px: float, py: float, pose: SleepPose) -> tuple[float, float]:
    """Curl the visible upper leg slightly over the lower sleeping leg."""

    thigh = _bell_2d(px, py, 263.0, 414.0, 118.0, 72.0)
    calf = _bell_2d(px, py, 304.0, 518.0, 132.0, 73.0)
    foot = _bell_2d(px, py, 413.0, 610.0, 59.0, 79.0)
    front_leg = min(1.0, thigh + calf + foot)
    front_leg *= smoothstep(344.0, 390.0, py)

    rotate_x, rotate_y = _rotation_offset(
        px,
        py,
        pivot_x=344.0,
        pivot_y=392.0,
        angle=math.radians(3.65) * pose.leg_settle,
    )
    knee = _bell_2d(px, py, 184.0, 449.0, 74.0, 57.0)
    dx = front_leg * rotate_x - 2.2 * pose.leg_settle * knee
    dy = front_leg * rotate_y - 1.5 * pose.leg_settle * knee

    # The lower leg remains a visual anchor but yields a fraction under the
    # moving ankle, making the crossed silhouette read as soft contact.
    lower_leg = _bell_2d(px, py, 337.0, 641.0, 125.0, 142.0)
    lower_leg *= smoothstep(523.0, 585.0, py)
    lower_leg *= 1.0 - 0.72 * front_leg
    dx += 1.8 * pose.leg_settle * lower_leg
    dy += -1.0 * pose.leg_settle * lower_leg
    return dx, dy


def _deformed_vertex(
    base: tuple[float, float, float],
    pose: SleepPose,
) -> tuple[float, float, float]:
    px, py = _pixels(base)
    upper_x, upper_y = _upper_offset(px, py, pose)
    embrace_x, embrace_y = _embrace_offset(px, py, pose)
    leg_x, leg_y = _leg_offset(px, py, pose)
    dx = upper_x + embrace_x + leg_x
    dy = upper_y + embrace_y + leg_y
    return (
        base[0] + dx * CANVAS_WIDTH / WIDTH,
        base[1] - dy * CANVAS_HEIGHT / HEIGHT,
        base[2],
    )


def _clear_frames(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob(f"{FRAME_PREFIX}-*.png"):
        path.unlink()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(sys.argv if argv is None else argv)
    if args.fps <= 0 or args.frame_count < args.fps * 4:
        raise SystemExit("sleep-v2 requires a positive FPS and at least four seconds")

    repository = args.repository_root.resolve()
    source_root = args.source_root.resolve() if args.source_root else repository / SOURCE_ROOT
    master = source_root / MASTER
    source_rgba(master, size=SOURCE_SIZE)

    frame_root = source_root / FRAME_DIRECTORY
    preview_root = source_root / "previews"
    if args.preview_frame is None:
        _clear_frames(frame_root)
    else:
        preview_root.mkdir(parents=True, exist_ok=True)

    scene = transparent_scene()
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.render.image_settings.compression = 15
    orthographic_camera(scene, name="Sleep V2 Camera")

    character, base_vertices = textured_grid(
        mesh_name="Sleep V2 Continuous Surface Mesh",
        object_name="Sleep V2 Continuous Surface",
        uv_name="Sleep V2 Continuous Surface UV",
    )
    texture = rgba_material(character, name="Sleep V2 Continuous Surface Material")
    texture.extension = "CLIP"
    image = set_texture_image(texture, master)
    if tuple(image.size) != SOURCE_SIZE:
        raise SystemExit(f"sleep master must be {SOURCE_SIZE[0]}x{SOURCE_SIZE[1]}: {master}")
    character["surface"] = "continuous"
    character["source_sha256"] = _digest(master)

    if args.preview_frame is not None:
        if not 0 <= args.preview_frame < args.frame_count:
            raise SystemExit("preview frame must be inside the loop")
        frames = (args.preview_frame,)
    else:
        frames = tuple(range(args.frame_count))

    for frame in frames:
        pose = timeline(frame, args.frame_count, args.fps)
        for vertex, base in zip(character.data.vertices, base_vertices, strict=True):
            vertex.co = _deformed_vertex(base, pose)
        character.data.update()

        if args.preview_frame is None:
            destination = frame_root / f"{FRAME_PREFIX}-{frame:03d}.png"
        else:
            destination = preview_root / f"sleep-v2-warp-v1-{frame:03d}.png"
        scene.render.filepath = str(destination.resolve())
        bpy.ops.render.render(write_still=True)

    if args.preview_frame is None:
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str((source_root / "sleep-v2-rig.blend").resolve()))

    print(f"SLEEP_V2_RENDERED frames={len(frames)} fps={args.fps} master_sha256={_digest(master)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
