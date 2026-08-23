#!/usr/bin/env python3
"""Render the experimental layered ``draw`` loop with anchored scene props.

Run through Blender, not the system Python::

    Blender --background --python tools/visual_pipeline/draw_layered_generate.py -- \
      --repository-root /absolute/path/to/kindred

The input contract deliberately separates the scene into two authored plates:

* a byte-stable chair/easel/canvas plate;
* one complete character plate with no limb seams.

Only continuous local deformation is applied to the character.  The seated
contact remains anchored while the torso leans, the painting arm reaches the
canvas, and the crossed legs make a restrained counter-motion.  The chair,
easel, and canvas never move.  This avoids both AI-generated in-between anatomy
failures and per-frame prop scale drift.
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
from tools.visual_pipeline.draw_layered_contract import (  # noqa: E402
    FPS,
    FRAME_COUNT,
    timeline,
)
from tools.visual_pipeline.draw_layered_validate import (  # noqa: E402
    write_static_prop_mask,
)
from tools.visual_pipeline.png_rgba import source_rgba, write_rgba  # noqa: E402

WIDTH = 512
HEIGHT = 768
# Coordinates are runtime pixels: shoulder, elbow, wrist, brush tip. The
# character mesh stays continuous, but each visible arm region receives a
# bounded influence so the solver cannot pull the chest with the hand.
REACH_OFFSETS = (
    (0.0, 0.0),
    (2.0, -0.5),
    (3.0, -1.0),
    (3.0, -1.0),
)
STROKE_OFFSETS = (
    (0.0, 0.0),
    (1.0, -0.5),
    (2.5, -1.5),
    (6.0, -4.0),
)
BRUSH_PIVOT = (270.0, 206.0)
BRUSH_TIP = (322.0, 189.0)
BRUSH_MASK_RADIUS = 10.0
BRUSH_SCALE_X = 1.50


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


def _canvas_point(pixel: tuple[float, float]) -> tuple[float, float]:
    return (
        (pixel[0] / WIDTH - 0.5) * CANVAS_WIDTH,
        (0.5 - pixel[1] / HEIGHT) * CANVAS_HEIGHT,
    )


def _set_pivot(
    obj: bpy.types.Object,
    base_vertices: Sequence[tuple[float, float, float]],
    pivot: tuple[float, float],
) -> tuple[float, float]:
    pivot_x, pivot_y = _canvas_point(pivot)
    for vertex, (x, y, z) in zip(obj.data.vertices, base_vertices, strict=True):
        vertex.co = (x - pivot_x, y - pivot_y, z)
    obj.location.x = pivot_x
    obj.location.y = pivot_y
    obj.data.update()
    return pivot_x, pivot_y


def _control_offsets(reach: float, stroke: float) -> tuple[tuple[float, float], ...]:
    return tuple(
        (
            reach * reach_offset[0] + stroke * stroke_offset[0],
            reach * reach_offset[1] + stroke * stroke_offset[1],
        )
        for reach_offset, stroke_offset in zip(REACH_OFFSETS, STROKE_OFFSETS, strict=True)
    )


def _path_offset(
    px: float,
    py: float,
    offsets: tuple[tuple[float, float], ...],
) -> tuple[float, float]:
    # The source arm has three visually distinct regions: translucent sleeve,
    # dark cuff/forearm, and exposed hand. Region gates follow those silhouettes
    # and stop before the bust. This is deliberately not a radial skeleton warp:
    # a radial field cannot distinguish the foreground arm from the chest under
    # it on a flattened character plate.
    sleeve = _bell_2d(px, py, 150.0, 305.0, 66.0, 82.0)
    sleeve *= smoothstep(220.0, 250.0, py)
    sleeve *= 1.0 - smoothstep(370.0, 410.0, py)
    sleeve *= 1.0 - smoothstep(218.0, 248.0, px)

    cuff = _bell_2d(px, py, 207.0, 278.0, 43.0, 55.0)
    cuff *= smoothstep(235.0, 255.0, py)
    cuff *= 1.0 - smoothstep(330.0, 355.0, py)
    cuff *= smoothstep(165.0, 190.0, px)

    hand = smoothstep(207.0, 228.0, px)
    hand *= 1.0 - smoothstep(278.0, 300.0, px)
    hand *= smoothstep(178.0, 198.0, py)
    hand *= 1.0 - smoothstep(258.0, 280.0, py)
    inner_shoulder_guard = _bell_2d(px, py, 246.0, 177.0, 38.0, 34.0)
    inner_shoulder_guard *= 1.0 - smoothstep(190.0, 215.0, py)
    hand *= 1.0 - 0.98 * inner_shoulder_guard

    forearm_offset = (
        offsets[1][0] * 0.35 + offsets[2][0] * 0.65,
        offsets[1][1] * 0.35 + offsets[2][1] * 0.65,
    )
    regions = (
        (sleeve, offsets[1]),
        (cuff, forearm_offset),
        (hand, offsets[2]),
    )
    total = sum(influence for influence, _ in regions)
    if total <= 1e-6:
        return 0.0, 0.0
    envelope = min(1.0, total)
    dx = sum(influence * offset[0] for influence, offset in regions) / total
    dy = sum(influence * offset[1] for influence, offset in regions) / total

    # A final upper-chest anchor guards the neckline and bust. The x/y gates
    # leave the hand and cuff free after they cross in front of that boundary.
    chest_guard = _bell_2d(px, py, 178.0, 218.0, 58.0, 72.0)
    chest_guard *= 1.0 - smoothstep(214.0, 234.0, px)
    chest_guard *= 1.0 - smoothstep(245.0, 275.0, py)
    envelope *= 1.0 - 0.98 * chest_guard
    return dx * envelope, dy * envelope


def _bell_2d(
    px: float,
    py: float,
    center_x: float,
    center_y: float,
    radius_x: float,
    radius_y: float,
) -> float:
    return math.exp(-(((px - center_x) / radius_x) ** 2 + ((py - center_y) / radius_y) ** 2))


def _body_offset(px: float, py: float, reach: float, stroke: float) -> tuple[float, float]:
    """Create one slow, seated whole-body weight shift without moving props."""

    # The chest is a stable core. A small common translation carries the torso,
    # while the head and hair follow a little farther toward the canvas. This
    # reads as a seated lean without stretching the bust with the painting hand.
    upper_body = 1.0 - smoothstep(320.0, 420.0, py)
    head_follow = _bell_2d(px, py, 196.0, 130.0, 112.0, 125.0)
    head_follow *= 1.0 - smoothstep(175.0, 230.0, py)
    skirt = _bell_2d(px, py, 205.0, 390.0, 150.0, 80.0)
    skirt *= smoothstep(335.0, 375.0, py) * (1.0 - smoothstep(410.0, 460.0, py))

    # The hips remain the visual anchor while the upper body advances modestly.
    dx = reach * (36.0 * upper_body + 1.0 * head_follow + 2.5 * skirt)
    dy = reach * (-2.5 * upper_body - 1.0 * head_follow + 0.75 * skirt)

    # A small breathing release at the paint-contact phase prevents the torso
    # from looking mechanically frozen while the wrist performs the stroke.
    dx += stroke * 0.35 * upper_body
    dy += stroke * -0.2 * upper_body

    # A very small clockwise head inclination makes the face and eye line meet
    # the lower-right brush contact instead of reading as a level forward stare.
    # The compact ellipse excludes the foreground hand and inner shoulder.
    head_distance = ((px - 185.0) / 100.0) ** 2 + ((py - 115.0) / 105.0) ** 2
    head_turn = 1.0 - smoothstep(0.62, 1.0, head_distance)
    angle = math.radians(5.0) * reach * head_turn
    relative_x = px - 190.0
    relative_y = py - 170.0
    rotated_x = math.cos(angle) * relative_x - math.sin(angle) * relative_y
    rotated_y = math.sin(angle) * relative_x + math.cos(angle) * relative_y
    dx += rotated_x - relative_x
    dy += rotated_y - relative_y

    # Crossed-leg counterbalance. Broad overlapping fields keep the source as
    # one continuous surface, so no knee or boot seam can open.
    forward_leg = _bell_2d(px, py, 255.0, 535.0, 90.0, 175.0)
    rear_leg = _bell_2d(px, py, 365.0, 535.0, 85.0, 180.0)
    forward_toe = _bell_2d(px, py, 225.0, 690.0, 70.0, 75.0)
    rear_toe = _bell_2d(px, py, 405.0, 695.0, 70.0, 75.0)
    leg_gate = smoothstep(390.0, 455.0, py)
    dx += (
        reach
        * leg_gate
        * (-9.0 * forward_leg + 9.0 * rear_leg - 8.0 * forward_toe + 10.0 * rear_toe)
    )
    dy += (
        reach * leg_gate * (5.0 * forward_leg - 3.0 * rear_leg + 6.0 * forward_toe + 3.0 * rear_toe)
    )
    return dx, dy


def _deformed_vertex(
    base: tuple[float, float, float],
    offsets: tuple[tuple[float, float], ...],
    reach: float,
    stroke: float,
) -> tuple[float, float, float]:
    px, py = _pixels(base)
    arm_x, arm_y = _path_offset(px, py, offsets)
    body_x, body_y = _body_offset(px, py, reach, stroke)
    dx = arm_x + body_x
    dy = arm_y + body_y
    return (
        base[0] + dx * CANVAS_WIDTH / WIDTH,
        base[1] - dy * CANVAS_HEIGHT / HEIGHT,
        base[2],
    )


def _material(obj: bpy.types.Object, source: Path, *, name: str) -> bpy.types.ShaderNodeTexImage:
    texture = rgba_material(obj, name=name)
    image = set_texture_image(texture, source)
    if tuple(image.size) != (WIDTH, HEIGHT):
        raise SystemExit(f"layer must be {WIDTH}x{HEIGHT}: {source}")
    return texture


def _render_png(scene: bpy.types.Scene, path: Path) -> None:
    scene.render.filepath = str(path.resolve())
    bpy.ops.render.render(write_still=True)
    pixels = source_rgba(path, size=(WIDTH, HEIGHT))
    write_rgba(path, size=(WIDTH, HEIGHT), pixels=pixels)


def _clear_frames(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob("motion-*.png"):
        path.unlink()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _focused_eye(pixels: bytearray) -> None:
    """Bias the visible pupil toward the lower-right canvas contact point."""

    accents = {
        # Release the previous horizontal pupil emphasis back into warm iris.
        (205, 104): (190, 103, 62, 255),
        # Place the pupil lower and farther right along eye -> brush-tip vector.
        (204, 106): (83, 41, 27, 255),
        (205, 106): (55, 25, 19, 255),
        (204, 107): (67, 30, 21, 255),
        (205, 107): (74, 34, 24, 255),
        # Opposing upper-left catchlight gives the tiny eye a readable focus.
        (200, 105): (251, 228, 190, 255),
        (201, 104): (255, 239, 205, 255),
        (202, 105): (246, 216, 170, 255),
    }
    for (x, y), rgba in accents.items():
        offset = (y * WIDTH + x) * 4
        if pixels[offset + 3] > 8:
            pixels[offset : offset + 4] = bytes(rgba)


def _prepare_character_and_brush(
    source: Path,
    generated_root: Path,
) -> tuple[Path, Path]:
    """Extract the rigid brush and deterministic focused character pose."""

    pixels = source_rgba(source, size=(WIDTH, HEIGHT))
    character = bytearray(pixels)
    brush = bytearray(len(pixels))
    vector_x = BRUSH_TIP[0] - BRUSH_PIVOT[0]
    vector_y = BRUSH_TIP[1] - BRUSH_PIVOT[1]
    length_squared = vector_x * vector_x + vector_y * vector_y
    for y in range(175, 225):
        for x in range(260, 330):
            amount = (
                (x - BRUSH_PIVOT[0]) * vector_x + (y - BRUSH_PIVOT[1]) * vector_y
            ) / length_squared
            amount = min(1.0, max(0.0, amount))
            closest_x = BRUSH_PIVOT[0] + amount * vector_x
            closest_y = BRUSH_PIVOT[1] + amount * vector_y
            if (x - closest_x) ** 2 + (y - closest_y) ** 2 > BRUSH_MASK_RADIUS**2:
                continue
            offset = (y * WIDTH + x) * 4
            alpha = pixels[offset + 3]
            # Move the complete anti-aliased capsule, including the few finger
            # pixels that overlap the handle. The rigid layer follows the same
            # hand control, so this removes floating edge remnants without
            # opening a visible gap at the grip.
            if alpha == 0:
                continue
            brush[offset : offset + 4] = pixels[offset : offset + 4]
            character[offset : offset + 4] = bytes((0, 0, 0, 0))

    _focused_eye(character)
    character_path = generated_root / "draw-character-focused-alpha-v2.png"
    brush_path = generated_root / "draw-brush-alpha-v1.png"
    write_rgba(character_path, size=(WIDTH, HEIGHT), pixels=bytes(character))
    write_rgba(brush_path, size=(WIDTH, HEIGHT), pixels=bytes(brush))
    return character_path, brush_path


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(sys.argv if argv is None else argv)
    if args.fps <= 0 or args.frame_count < args.fps * 6:
        raise SystemExit("layered draw requires a positive FPS and at least six seconds")

    repository = args.repository_root.resolve()
    source_root = (
        args.source_root.resolve()
        if args.source_root
        else repository / "visual-sources/kindred-default/frame2e"
    )
    props_source = source_root / "layers/draw-static-props-alpha-v1.png"
    master_character_source = source_root / "keys/stable-alpha/key-00.png"
    for source in (props_source, master_character_source):
        source_rgba(source, size=(WIDTH, HEIGHT))
    character_source, brush_source = _prepare_character_and_brush(
        master_character_source,
        source_root / "layers/generated",
    )

    scene_output = source_root / "frames/scene-warp-v5"
    if args.preview_frame is None:
        _clear_frames(scene_output)
    else:
        (source_root / "previews").mkdir(parents=True, exist_ok=True)

    scene = transparent_scene()
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    orthographic_camera(scene, name="FRAME2E Camera")

    props, _ = textured_grid(
        mesh_name="FRAME2E Static Props Mesh",
        object_name="FRAME2E Static Props",
        uv_name="FRAME2E Static Props UV",
    )
    _material(props, props_source, name="FRAME2E Static Props Material")
    props.location.z = 0.0

    character, base_vertices = textured_grid(
        mesh_name="FRAME2E Character Mesh",
        object_name="FRAME2E Character",
        uv_name="FRAME2E Character UV",
    )
    _material(character, character_source, name="FRAME2E Character Material")
    character.location.z = 0.01

    brush, brush_vertices = textured_grid(
        mesh_name="FRAME2E Brush Mesh",
        object_name="FRAME2E Brush",
        uv_name="FRAME2E Brush UV",
    )
    _material(brush, brush_source, name="FRAME2E Brush Material")
    brush_origin = _set_pivot(brush, brush_vertices, BRUSH_PIVOT)
    brush.scale.x = BRUSH_SCALE_X
    brush.location.z = 0.02

    props["layer_role"] = "anchored_scene_props"
    props["source_sha256"] = _digest(props_source)
    character["layer_role"] = "continuous_character_surface"
    character["source_sha256"] = _digest(character_source)
    character["master_source_sha256"] = _digest(master_character_source)
    character["seated_contact"] = "anchored"
    brush["layer_role"] = "rigid_brush"
    brush["source_sha256"] = _digest(brush_source)

    if args.preview_frame is not None:
        if not 0 <= args.preview_frame < args.frame_count:
            raise SystemExit("preview frame must be inside the loop")
        frames = (args.preview_frame,)
    else:
        frames = tuple(range(args.frame_count))

    for frame in frames:
        reach, stroke = timeline(frame, args.frame_count, args.fps)
        offsets = _control_offsets(reach, stroke)
        for vertex, base in zip(character.data.vertices, base_vertices, strict=True):
            vertex.co = _deformed_vertex(base, offsets, reach, stroke)
        character.data.update()

        brush_body_x, brush_body_y = _body_offset(*BRUSH_PIVOT, reach, stroke)
        brush_dx = offsets[2][0] + brush_body_x
        brush_dy = offsets[2][1] + brush_body_y
        brush.location.x = brush_origin[0] + brush_dx * CANVAS_WIDTH / WIDTH
        brush.location.y = brush_origin[1] - brush_dy * CANVAS_HEIGHT / HEIGHT

        if args.preview_frame is None:
            scene_path = scene_output / f"motion-{frame:03d}.png"
        else:
            scene_path = source_root / "previews" / f"draw-layered-warp-v5-{frame:03d}.png"
        _render_png(scene, scene_path)

    if args.preview_frame is None:
        scene_paths = [
            scene_output / f"motion-{frame:03d}.png" for frame in range(args.frame_count)
        ]
        write_static_prop_mask(
            props_source,
            scene_paths,
            source_root / "layers/draw-static-props-visible-mask-v1.png",
        )

    for vertex, base in zip(character.data.vertices, base_vertices, strict=True):
        vertex.co = base
    character.data.update()
    blend_path = source_root / "frame2e-layered-draw-rig.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path.resolve()))
    print(
        "FRAME2E_LAYERED_DRAW_RENDERED "
        f"frames={len(frames)} fps={args.fps} props_sha256={_digest(props_source)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
