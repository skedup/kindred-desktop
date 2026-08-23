#!/usr/bin/env python3
"""Generate standing desktop-spirit motions with Blender's deterministic 2D mesh warp.

Run this script through Blender, not the system Python:

    Blender --background --python tools/visual_pipeline/standing_generate.py -- \
      --repository-root /absolute/path/to/kindred

The source key poses remain outside the shipped visual pack. Runtime frames are
rendered at desktop scale, on a fixed transparent canvas, from a single textured
mesh. The small mesh deformation adds breathing and secondary motion without
asking a generative model to invent any in-between frames.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

import bpy

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.visual_pipeline.blender_canvas import (  # noqa: E402
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    SOURCE_HEIGHT,
    SOURCE_WIDTH,
    bell,
    orthographic_camera,
    rgba_material,
    set_texture_image,
    smoothstep,
    textured_grid,
    transparent_scene,
)

# The closed-eye source was generated as a full image. Only these feathered
# ellipses are allowed to replace pixels in the neutral master; otherwise tiny
# whole-body generation drift becomes a visible flash at blink time.
BLINK_MASK = (
    "max("
    "clip((1-((X-480)*(X-480)/(64*64)+(Y-160)*(Y-160)/(34*34)))*5,0,1),"
    "clip((1-((X-552)*(X-552)/(64*64)+(Y-157)*(Y-157)/(34*34)))*5,0,1)"
    ")"
)


def _arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--fps", type=int, default=6)
    if "--" not in argv:
        parser.error("arguments must follow Blender's -- separator")
    return parser.parse_args(argv[argv.index("--") + 1 :])


def _deformed_vertex(
    base: tuple[float, float, float], *, phase: float, motion: str
) -> tuple[float, float, float]:
    x, y, z = base
    px = (x / CANVAS_WIDTH + 0.5) * SOURCE_WIDTH
    py = (0.5 - y / CANVAS_HEIGHT) * SOURCE_HEIGHT

    cycle = 2.0 * math.pi * phase
    inhale = 0.5 - 0.5 * math.cos(cycle)
    follow = math.sin(cycle - 0.38)
    anchor = 1.0 - smoothstep(820.0, 1450.0, py)
    torso = bell(px, 515.0, 210.0) * bell(py, 520.0, 290.0) * anchor
    head = bell(px, 520.0, 155.0) * bell(py, 205.0, 170.0)
    left_sleeve = bell(px, 323.0, 92.0) * bell(py, 550.0, 250.0)
    right_sleeve = bell(px, 703.0, 92.0) * bell(py, 550.0, 250.0)
    hair = bell(px, 520.0, 185.0) * bell(py, 245.0, 230.0)
    skirt = bell(px, 565.0, 190.0) * bell(py, 735.0, 260.0)

    if motion == "settle":
        breath_y = -3.2
        breath_x = 1.35
        head_y = -0.7
        follow_scale = 1.0
    elif motion == "sleep":
        breath_y = -4.0
        breath_x = 1.05
        head_y = 1.2
        follow_scale = 0.62
    else:
        breath_y = -2.1
        breath_x = 0.75
        head_y = -0.35
        follow_scale = 0.45

    side = -1.0 if px < 515.0 else 1.0
    dx_pixels = side * breath_x * inhale * torso
    dy_pixels = breath_y * inhale * torso + head_y * inhale * head

    dx_pixels += (
        follow_scale
        * follow
        * (-1.15 * left_sleeve + 1.15 * right_sleeve + 0.65 * hair + 0.85 * skirt)
    )
    dy_pixels += follow_scale * follow * (0.55 * left_sleeve - 0.45 * right_sleeve + 0.5 * skirt)

    return (
        x + dx_pixels * CANVAS_WIDTH / SOURCE_WIDTH,
        y - dy_pixels * CANVAS_HEIGHT / SOURCE_HEIGHT,
        z,
    )


def _build_localized_blink(neutral: Path, generated_blink: Path, output: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("FRAME1 localized blink requires ffmpeg on PATH")
    filter_graph = (
        "[0:v]format=rgba[neutral];"
        "[1:v]format=rgba[blink];"
        f"[neutral][blink]blend=all_expr='A*(1-{BLINK_MASK})+B*{BLINK_MASK}',"
        "format=rgba[out]"
    )
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(neutral),
                "-i",
                str(generated_blink),
                "-filter_complex",
                filter_graph,
                "-map",
                "[out]",
                "-frames:v",
                "1",
                str(output),
            ],
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise SystemExit("FRAME1 localized blink compositing failed") from error


def _render_frames(
    *,
    scene: bpy.types.Scene,
    obj: bpy.types.Object,
    base_vertices: Sequence[tuple[float, float, float]],
    texture: bpy.types.ShaderNodeTexImage,
    sources: Sequence[Path],
    motion: str,
    output: Path,
) -> list[str]:
    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob(f"{motion}-*.png"):
        stale.unlink()

    names: list[str] = []
    count = len(sources)
    for index, source in enumerate(sources):
        set_texture_image(texture, source)
        phase = index / count
        for vertex, base in zip(obj.data.vertices, base_vertices, strict=True):
            vertex.co = _deformed_vertex(base, phase=phase, motion=motion)
        obj.data.update()

        name = f"{motion}-{index:03d}.png"
        scene.render.filepath = str((output / name).resolve())
        bpy.ops.render.render(write_still=True)
        names.append(name)
    return names


def _repeated(source: Path, count: int) -> list[Path]:
    return [source for _ in range(count)]


def _settle_sequence(neutral: Path, blink: Path) -> list[Path]:
    sequence = _repeated(neutral, 18)
    sequence[10] = blink
    return sequence


def _eat_sequence(rest: Path, middle: Path, bite: Path) -> list[Path]:
    # Limited animation deliberately holds strong key poses instead of cross-fading
    # entire generated images, which would create double hands and texture ghosts.
    return [rest, rest, rest, middle, middle, bite, bite, bite, middle, middle, rest, rest]


def _write_summary(repository: Path, fps: int, frames: dict[str, Iterable[str]]) -> None:
    summary = repository / "visual-sources/kindred-default/frame1/RENDERED.txt"
    lines = [f"fps={fps}", "size=512x768"]
    for motion, names in frames.items():
        lines.append(f"{motion}={len(list(names))}")
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(sys.argv if argv is None else argv)
    repository = args.repository_root.resolve()
    if (args.width, args.height) != (512, 768):
        raise SystemExit("FRAME1 currently requires the reviewed 512x768 runtime canvas")
    if args.fps != 6:
        raise SystemExit("FRAME1 currently requires the reviewed 6 FPS timing")

    pack = repository / "visual-packs/kindred-default"
    source = repository / "visual-sources/kindred-default/frame1"
    neutral = pack / "assets/body/neutral.png"
    generated_blink = source / "keys/blink.png"
    blink = source / "keys/blink-local.png"
    sleep = source / "keys/sleep.png"
    eat_rest = source / "keys/eat-rest.png"
    eat_mid = source / "keys/eat-mid.png"
    eat_bite = source / "keys/eat-bite.png"
    required = [neutral, generated_blink, sleep, eat_rest, eat_mid, eat_bite]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(f"missing FRAME1 source: {missing[0]}")

    _build_localized_blink(neutral, generated_blink, blink)

    scene = transparent_scene()
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    orthographic_camera(scene, name="FRAME1 Camera")
    obj, base_vertices = textured_grid(
        mesh_name="FRAME1 Mesh",
        object_name="FRAME1 Character",
        uv_name="FRAME1 UV",
    )
    texture = rgba_material(obj, name="FRAME1 Character")

    body_root = pack / "assets/body/frame1"
    rendered = {
        "settle": _render_frames(
            scene=scene,
            obj=obj,
            base_vertices=base_vertices,
            texture=texture,
            sources=_settle_sequence(neutral, blink),
            motion="settle",
            output=body_root / "settle",
        ),
        "sleep": _render_frames(
            scene=scene,
            obj=obj,
            base_vertices=base_vertices,
            texture=texture,
            sources=_repeated(sleep, 24),
            motion="sleep",
            output=body_root / "sleep",
        ),
        "eat": _render_frames(
            scene=scene,
            obj=obj,
            base_vertices=base_vertices,
            texture=texture,
            sources=_eat_sequence(eat_rest, eat_mid, eat_bite),
            motion="eat",
            output=body_root / "eat",
        ),
    }
    bpy.ops.wm.save_as_mainfile(filepath=str((source / "frame1-rig.blend").resolve()))
    _write_summary(repository, args.fps, rendered)
    print(
        "FRAME1_RENDERED "
        + " ".join(f"{motion}={len(names)}" for motion, names in rendered.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
