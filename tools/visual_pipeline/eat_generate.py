#!/usr/bin/env python3
"""Render the layered ``eat-v2`` loop with fixed breakfast props.

Run through Blender, not the system Python::

    Blender --background --python tools/visual_pipeline/eat_generate.py -- \
      --repository-root /absolute/path/to/kindred-desktop

The chair, table, bowl, and bread remain static. One continuous character mesh
drives the torso, active arm, support hand, and the two character-surface
replays used for depth ordering. The spoon is an independent rigid object whose
pivot follows the same deformed grip point.
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
from tools.visual_pipeline.eat_contract import (  # noqa: E402
    CHARACTER_LAYER,
    CHARACTER_VISIBLE_MASK,
    FOREGROUND_LAYER,
    FPS,
    FRAME_COUNT,
    FRAME_DIRECTORY,
    FRAME_PREFIX,
    GRIP_REGION,
    REAR_LAYER,
    RUNTIME_SIZE,
    SOURCE_ROOT,
    SOURCE_SIZE,
    SPOON_LAYER,
    SUPPORT_HAND_REGION,
    EatPose,
    runtime_inside_table_gutter,
    timeline,
)
from tools.visual_pipeline.eat_promote import (  # noqa: E402
    STATIC_PROPS_PLATE,
    VISIBLE_PROPS_MASK,
)
from tools.visual_pipeline.eat_validate import write_static_prop_mask  # noqa: E402
from tools.visual_pipeline.png_rgba import source_rgba, write_rgba  # noqa: E402

WIDTH, HEIGHT = RUNTIME_SIZE
SOURCE_WIDTH, SOURCE_HEIGHT = SOURCE_SIZE
SPOON_PIVOT = (116.0, 462.0)
RUNTIME_TABLE_GUTTER_OFFSETS = tuple(
    (y * WIDTH + x) * 4
    for y in range(HEIGHT)
    for x in range(WIDTH)
    if runtime_inside_table_gutter(x, y)
)


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


def _inside_polygon(
    x: float,
    y: float,
    points: tuple[tuple[float, float], ...],
) -> bool:
    inside = False
    previous = points[-1]
    for current in points:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def _bell_2d(
    px: float,
    py: float,
    center_x: float,
    center_y: float,
    radius_x: float,
    radius_y: float,
) -> float:
    return math.exp(-(((px - center_x) / radius_x) ** 2 + ((py - center_y) / radius_y) ** 2))


def _body_offset(px: float, py: float, pose: EatPose) -> tuple[float, float]:
    """Translate the upper body as a rigid core and keep the seated base anchored."""

    lean = 0.38 * pose.approach + 0.58 * pose.lift
    upper_body = 1.0 - smoothstep(515.0, 590.0, py)
    dx = lean * -4.0 * upper_body
    dy = lean * 8.0 * upper_body
    dx += pose.breath * 0.3 * upper_body
    dy += pose.breath * -0.8 * upper_body
    return dx, dy


def _active_arm_offset(px: float, py: float, pose: EatPose) -> tuple[float, float]:
    """Move the billowing sleeve as one bounded surface below the arm band.

    A large articulated rotation folds the flattened source mesh over itself;
    unrelated per-joint translations stretch its organza texture. A common
    translation with a restrained rotation preserves internal proportions,
    while the long rigid spoon supplies the remaining reach to the mouth.
    """

    sleeve = _bell_2d(px, py, 132.0, 450.0, 74.0, 102.0)
    sleeve *= smoothstep(378.0, 402.0, py)
    sleeve *= 1.0 - smoothstep(190.0, 213.0, px)
    hand = _bell_2d(px, py, SPOON_PIVOT[0], SPOON_PIVOT[1], 44.0, 39.0)
    hand *= smoothstep(405.0, 425.0, py)
    hand *= 1.0 - smoothstep(184.0, 204.0, px)
    envelope = min(1.0, sleeve + hand)
    if envelope <= 1e-7:
        return 0.0, 0.0

    dx = 6.0 * pose.approach + 35.0 * pose.lift
    dy = 4.0 * pose.approach - 125.0 * pose.lift - 1.5 * pose.sip
    angle = math.radians(-3.0 * pose.approach - 8.0 * pose.lift)
    relative_x = px - SPOON_PIVOT[0]
    relative_y = py - SPOON_PIVOT[1]
    rotated_x = math.cos(angle) * relative_x - math.sin(angle) * relative_y
    rotated_y = math.sin(angle) * relative_x + math.cos(angle) * relative_y
    dx += rotated_x - relative_x
    dy += rotated_y - relative_y

    # The active transform starts below the metal arm band. Bare shoulder,
    # clavicle, neckline, and bust receive only the rigid body translation.
    root_gate = smoothstep(382.0, 448.0, py)
    chest_gate = 1.0 - smoothstep(184.0, 207.0, px)
    envelope *= root_gate * chest_gate
    return dx * envelope, dy * envelope


def _character_offset(px: float, py: float, pose: EatPose) -> tuple[float, float]:
    body_x, body_y = _body_offset(px, py, pose)
    arm_x, arm_y = _active_arm_offset(px, py, pose)
    dx = body_x + arm_x
    dy = body_y + arm_y

    # The support hand keeps contact with the fixed bowl. The broad local blend
    # cancels the torso lean at the fingertips while allowing a tiny living
    # adjustment rather than freezing an independently cut hand.
    support = _bell_2d(px, py, 292.0, 586.0, 82.0, 68.0)
    support *= smoothstep(515.0, 555.0, py)
    desired_x = -1.2 * pose.approach + 0.8 * pose.lift
    desired_y = 0.8 * pose.approach - 0.5 * pose.lift
    dx = dx * (1.0 - support) + desired_x * support
    dy = dy * (1.0 - support) + desired_y * support
    return dx, dy


def _deformed_vertex(
    base: tuple[float, float, float],
    pose: EatPose,
) -> tuple[float, float, float]:
    px, py = _pixels(base)
    dx, dy = _character_offset(px, py, pose)
    return (
        base[0] + dx * CANVAS_WIDTH / WIDTH,
        base[1] - dy * CANVAS_HEIGHT / HEIGHT,
        base[2],
    )


def _material(
    obj: bpy.types.Object,
    source: Path,
    *,
    name: str,
) -> bpy.types.ShaderNodeTexImage:
    texture = rgba_material(obj, name=name)
    texture.extension = "CLIP"
    image = set_texture_image(texture, source)
    if tuple(image.size) != SOURCE_SIZE:
        raise SystemExit(f"layer must be {SOURCE_WIDTH}x{SOURCE_HEIGHT}: {source}")
    return texture


def _render_png(scene: bpy.types.Scene, path: Path) -> None:
    scene.render.filepath = str(path.resolve())
    bpy.ops.render.render(write_still=True)
    pixels = bytearray(source_rgba(path, size=RUNTIME_SIZE))
    # Blender downsamples the 1024px source layers into the 512px runtime
    # frame. Clear the approved runtime gutter after that filter so a fringe
    # pixel cannot make the table appear wider than the status card.
    for offset in RUNTIME_TABLE_GUTTER_OFFSETS:
        pixels[offset : offset + 4] = b"\0\0\0\0"
    write_rgba(path, size=RUNTIME_SIZE, pixels=bytes(pixels))


def _clear_frames(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob(f"{FRAME_PREFIX}-*.png"):
        path.unlink()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extract_character_replays(source_root: Path) -> tuple[Path, Path]:
    character = source_rgba(source_root / CHARACTER_LAYER, size=SOURCE_SIZE)
    visible = source_rgba(source_root / CHARACTER_VISIBLE_MASK, size=SOURCE_SIZE)
    grip = bytearray(len(character))
    support = bytearray(len(character))
    for index in range(SOURCE_WIDTH * SOURCE_HEIGHT):
        x = index % SOURCE_WIDTH
        y = index // SOURCE_WIDTH
        offset = index * 4
        if character[offset + 3] <= 8:
            continue
        center_x = x + 0.5
        center_y = y + 0.5
        if _inside_polygon(center_x, center_y, GRIP_REGION):
            grip[offset : offset + 4] = character[offset : offset + 4]
        if visible[offset + 3] > 8 and _inside_polygon(center_x, center_y, SUPPORT_HAND_REGION):
            support[offset : offset + 4] = character[offset : offset + 4]

    generated_root = source_root / "layers/generated"
    generated_root.mkdir(parents=True, exist_ok=True)
    grip_path = generated_root / "eat-grip-replay-alpha-v1.png"
    support_path = generated_root / "eat-support-hand-replay-alpha-v1.png"
    write_rgba(grip_path, size=SOURCE_SIZE, pixels=bytes(grip))
    write_rgba(support_path, size=SOURCE_SIZE, pixels=bytes(support))
    return grip_path, support_path


def _layer(
    source: Path,
    *,
    role: str,
    z: float,
) -> tuple[bpy.types.Object, list[tuple[float, float, float]]]:
    title = role.replace("_", " ").title()
    obj, vertices = textured_grid(
        mesh_name=f"Eat V2 {title} Mesh",
        object_name=f"Eat V2 {title}",
        uv_name=f"Eat V2 {title} UV",
    )
    _material(obj, source, name=f"Eat V2 {title} Material")
    obj.location.z = z
    obj["layer_role"] = role
    obj["source_sha256"] = _digest(source)
    return obj, vertices


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(sys.argv if argv is None else argv)
    if args.fps <= 0 or args.frame_count < args.fps * 6:
        raise SystemExit("eat-v2 requires a positive FPS and at least six seconds")

    repository = args.repository_root.resolve()
    source_root = args.source_root.resolve() if args.source_root else repository / SOURCE_ROOT
    source_paths = {
        "rear": source_root / REAR_LAYER,
        "character": source_root / CHARACTER_LAYER,
        "spoon": source_root / SPOON_LAYER,
        "foreground": source_root / FOREGROUND_LAYER,
    }
    for source in source_paths.values():
        source_rgba(source, size=SOURCE_SIZE)
    grip_source, support_source = _extract_character_replays(source_root)

    frame_root = source_root / FRAME_DIRECTORY
    preview_root = source_root / "previews"
    if args.preview_frame is None:
        _clear_frames(frame_root)
    else:
        preview_root.mkdir(parents=True, exist_ok=True)

    scene = transparent_scene()
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    # Blender's intermediate PNG is immediately normalized by ``write_rgba``;
    # low intermediate compression avoids paying for the same compression twice.
    scene.render.image_settings.compression = 15
    orthographic_camera(scene, name="Eat V2 Camera")

    rear, _rear_vertices = _layer(source_paths["rear"], role="rear_static", z=0.00)
    character, character_vertices = _layer(
        source_paths["character"],
        role="continuous_character_surface",
        z=0.01,
    )
    spoon, spoon_vertices = _layer(source_paths["spoon"], role="rigid_spoon", z=0.02)
    foreground, _foreground_vertices = _layer(
        source_paths["foreground"],
        role="foreground_occluder",
        z=0.03,
    )
    support, support_vertices = _layer(
        support_source,
        role="continuous_character_support_replay",
        z=0.04,
    )
    grip, grip_vertices = _layer(
        grip_source,
        role="continuous_character_grip_replay",
        z=0.05,
    )
    spoon_origin = _set_pivot(spoon, spoon_vertices, SPOON_PIVOT)

    rear["motion"] = "byte_stable"
    foreground["motion"] = "byte_stable"
    character["surface"] = "continuous"
    support["surface_authority"] = "continuous_character_surface"
    grip["surface_authority"] = "continuous_character_surface"
    spoon["motion"] = "rigid_translation_and_rotation"

    if args.preview_frame is not None:
        if not 0 <= args.preview_frame < args.frame_count:
            raise SystemExit("preview frame must be inside the loop")
        frames = (args.preview_frame,)
    else:
        frames = tuple(range(args.frame_count))

    deformable = (
        (character, character_vertices),
        (support, support_vertices),
        (grip, grip_vertices),
    )
    for frame in frames:
        pose = timeline(frame, args.frame_count, args.fps)
        for obj, base_vertices in deformable:
            for vertex, base in zip(obj.data.vertices, base_vertices, strict=True):
                vertex.co = _deformed_vertex(base, pose)
            obj.data.update()

        spoon_dx, spoon_dy = _character_offset(*SPOON_PIVOT, pose)
        spoon.location.x = spoon_origin[0] + spoon_dx * CANVAS_WIDTH / WIDTH
        spoon.location.y = spoon_origin[1] - spoon_dy * CANVAS_HEIGHT / HEIGHT
        spoon.rotation_euler.z = math.radians(
            -4.0 * pose.approach + 55.0 * pose.lift + 1.5 * pose.sip
        )

        if args.preview_frame is None:
            destination = frame_root / f"{FRAME_PREFIX}-{frame:03d}.png"
        else:
            destination = preview_root / f"eat-v2-warp-v1-{frame:03d}.png"
        _render_png(scene, destination)

    if args.preview_frame is None:
        # Render the fixed rear/foreground composition independently from the
        # character and spoon. The derived full-loop mask records only prop
        # pixels that remain unobscured, so validation can reject even a
        # one-pixel chair/table drift without freezing character overlap.
        animated_objects = (character, spoon, support, grip)
        for obj in animated_objects:
            obj.hide_render = True
        static_props_path = source_root / STATIC_PROPS_PLATE
        _render_png(scene, static_props_path)
        for obj in animated_objects:
            obj.hide_render = False
        write_static_prop_mask(
            static_props_path,
            [frame_root / f"{FRAME_PREFIX}-{frame:03d}.png" for frame in frames],
            source_root / VISIBLE_PROPS_MASK,
        )

        rig_path = source_root / "eat-v2-rig.blend"
        # The source tree keeps only the current deterministic rig. Blender's
        # numbered save backups are local recovery artifacts, not authored
        # inputs, and would otherwise make repeated renders grow the asset set.
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(rig_path.resolve()))

    print(
        "EAT_V2_RENDERED "
        f"frames={len(frames)} fps={args.fps} "
        f"rear_sha256={_digest(source_paths['rear'])} "
        f"foreground_sha256={_digest(source_paths['foreground'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
