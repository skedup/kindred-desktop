#!/usr/bin/env python3
"""Generate the FRAME2 ``draw`` loop from the FRAME2-B2a-R1 surface pilot.

Run this script through Blender, not the system Python::

    Blender --background --python tools/visual_pipeline/draw_generate.py -- \
      --repository-root /absolute/path/to/kindred

The runtime still receives only pre-rendered frames.  The torso, sleeves, arms,
and held palette are rendered through one continuous textured mesh; independent
layers remain only where a real visual overlap exists (head/hair, eyes, brush,
and fixed props).  No generated in-between frame is used.
"""

from __future__ import annotations

import argparse
import json
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
    bell,
    orthographic_camera,
    rgba_material,
    set_texture_image,
    smoothstep,
    textured_grid,
    transparent_scene,
)
from tools.visual_pipeline.draw_contract import (  # noqa: E402
    CONTRACT_VERSION,
    FPS,
    FRAME_COUNT,
    SOURCE_HEIGHT,
    SOURCE_WIDTH,
    prop_anchor_weight,
)
from tools.visual_pipeline.draw_layers_build import (  # noqa: E402
    LAYER_CONTRACT_VERSION,
)
from tools.visual_pipeline.draw_layers_validate import validate as validate_layers  # noqa: E402
from tools.visual_pipeline.png_rgba import source_rgba, write_rgba  # noqa: E402


def _arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--fps", type=int, default=FPS)
    if "--" not in argv:
        parser.error("arguments must follow Blender's -- separator")
    return parser.parse_args(argv[argv.index("--") + 1 :])


def _material(obj: bpy.types.Object, source: Path, *, name: str) -> None:
    texture = rgba_material(obj, name=name)
    image = set_texture_image(texture, source)
    if tuple(image.size) != (SOURCE_WIDTH, SOURCE_HEIGHT):
        raise SystemExit(
            f"FRAME2 draw layer must be {SOURCE_WIDTH}x{SOURCE_HEIGHT}, got "
            f"{image.size[0]}x{image.size[1]}"
        )


def _pixels(base: tuple[float, float, float]) -> tuple[float, float]:
    x, y, _ = base
    return (
        (x / CANVAS_WIDTH + 0.5) * SOURCE_WIDTH,
        (0.5 - y / CANVAS_HEIGHT) * SOURCE_HEIGHT,
    )


def _canvas_point(pixel: tuple[float, float]) -> tuple[float, float]:
    x, y = pixel
    return (
        (x / SOURCE_WIDTH - 0.5) * CANVAS_WIDTH,
        (0.5 - y / SOURCE_HEIGHT) * CANVAS_HEIGHT,
    )


def _set_pivot(
    obj: bpy.types.Object,
    base_vertices: Sequence[tuple[float, float, float]],
    pivot: tuple[float, float],
) -> list[tuple[float, float, float]]:
    pivot_x, pivot_y = _canvas_point(pivot)
    local = [(x - pivot_x, y - pivot_y, z) for x, y, z in base_vertices]
    for vertex, position in zip(obj.data.vertices, local, strict=True):
        vertex.co = position
    obj.location.x = pivot_x
    obj.location.y = pivot_y
    obj.data.update()
    return local


def _region_weights(px: float, py: float) -> dict[str, float]:
    # These named controls preserve the complete-master vocabulary in the
    # inspectable .blend.  Domains already promoted to independent cut-out
    # objects no longer consume their body-mesh weights.
    head = bell(px, 385.0, 165.0) * bell(py, 205.0, 180.0)
    hair = bell(px, 390.0, 205.0) * bell(py, 235.0, 235.0)
    torso = bell(px, 420.0, 235.0) * bell(py, 520.0, 285.0)
    draw_hand = bell(px, 620.0, 155.0) * bell(py, 485.0, 125.0)
    draw_sleeve = bell(px, 545.0, 145.0) * bell(py, 535.0, 205.0)
    support_hand = bell(px, 440.0, 165.0) * bell(py, 690.0, 130.0)
    support_sleeve = bell(px, 260.0, 145.0) * bell(py, 575.0, 235.0)
    skirt = bell(px, 340.0, 230.0) * bell(py, 930.0, 310.0)
    hair_back = hair * smoothstep(210.0, 520.0, py)
    # The canvas/easel and chair use the same explicit semantic mask as the
    # validator.  A brush corridor is excluded because it belongs to the hand.
    prop_anchor = prop_anchor_weight(px, py)
    movable = 1.0 - prop_anchor
    return {
        "face_eyes": head * movable,
        "hair_front": hair * movable,
        "hair_back": hair_back * movable,
        "torso": torso * movable,
        "draw_upper_arm": draw_sleeve * movable,
        "draw_forearm_hand_brush": draw_hand * movable,
        "support_arm_hand_palette": support_hand * movable,
        "translucent_sleeves": max(draw_sleeve, support_sleeve) * movable,
        "skirt_panels": skirt * movable,
        "legs_boots": 0.0,
        "easel_chair": prop_anchor,
    }


def _add_vertex_groups(
    obj: bpy.types.Object, base_vertices: Sequence[tuple[float, float, float]]
) -> list[dict[str, float]]:
    weights: list[dict[str, float]] = []
    names = tuple(_region_weights(0.0, 0.0))
    groups = {name: obj.vertex_groups.new(name=name) for name in names}
    for index, base in enumerate(base_vertices):
        px, py = _pixels(base)
        vertex_weights = _region_weights(px, py)
        weights.append(vertex_weights)
        for name, weight in vertex_weights.items():
            if weight > 0.001:
                groups[name].add([index], weight, "REPLACE")
    return weights


def _ease_between(frame: int, start: int, peak: int, end: int) -> float:
    if frame <= start or frame >= end:
        return 0.0
    if frame <= peak:
        return smoothstep(start, peak, frame)
    return 1.0 - smoothstep(peak, end, frame)


SUPPORT_ARM_PATH = ((260.0, 425.0), (205.0, 570.0), (395.0, 625.0))
DRAW_ARM_PATH = ((515.0, 420.0), (650.0, 565.0), (625.0, 475.0))


def _pixel_delta_to_canvas(dx: float, dy: float) -> tuple[float, float]:
    return (
        dx * CANVAS_WIDTH / SOURCE_WIDTH,
        -dy * CANVAS_HEIGHT / SOURCE_HEIGHT,
    )


def _segment_coordinate(
    px: float,
    py: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[float, float]:
    start_x, start_y = start
    delta_x = end[0] - start_x
    delta_y = end[1] - start_y
    length_squared = delta_x * delta_x + delta_y * delta_y
    projection = ((px - start_x) * delta_x + (py - start_y) * delta_y) / length_squared
    parameter = min(1.0, max(0.0, projection))
    closest_x = start_x + parameter * delta_x
    closest_y = start_y + parameter * delta_y
    return parameter, math.hypot(px - closest_x, py - closest_y)


def _joint_pixel_offsets(frame: int) -> dict[str, tuple[float, float]]:
    cycle = 2.0 * math.pi * frame / FRAME_COUNT
    sway = math.sin(cycle)
    stroke = _ease_between(frame, 4, 8, 12)
    return {
        "support_shoulder": (-6.0 * sway, -3.0 * sway),
        "support_elbow": (-10.0 * sway, 3.0 * sway),
        "support_wrist": (-4.0 * sway, 1.5 * sway),
        "draw_shoulder": (7.0 * stroke + 1.2 * sway, -3.0 * stroke - 0.6 * sway),
        "draw_elbow": (11.0 * stroke + 1.8 * sway, -4.1 * stroke - 0.7 * sway),
        "draw_wrist": (13.0 * stroke, -4.8 * stroke),
    }


def _arm_path_offset(
    px: float,
    py: float,
    *,
    path: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
    offsets: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
) -> tuple[float, float, tuple[float, float, float]]:
    """Interpolate a shoulder-elbow-wrist displacement along the nearest bone."""

    first_t, first_distance = _segment_coordinate(px, py, path[0], path[1])
    second_t, second_distance = _segment_coordinate(px, py, path[1], path[2])
    if first_distance <= second_distance:
        weights = (1.0 - first_t, first_t, 0.0)
    else:
        weights = (0.0, 1.0 - second_t, second_t)
    dx = sum(weight * offset[0] for weight, offset in zip(weights, offsets, strict=True))
    dy = sum(weight * offset[1] for weight, offset in zip(weights, offsets, strict=True))
    return dx, dy, weights


def _body_canvas_offset(
    base: tuple[float, float, float], weights: dict[str, float], frame: int
) -> tuple[float, float]:
    """Return the shared continuous-surface displacement in canvas units."""

    px, py = _pixels(base)
    cycle = 2.0 * math.pi * frame / FRAME_COUNT
    breath = 0.5 - 0.5 * math.cos(cycle)
    delayed = math.sin(cycle - 0.42)
    dx = 0.0
    dy = 0.0

    torso = weights["torso"]
    dx += (1.7 if px >= 420.0 else -1.7) * breath * torso
    dy += -3.4 * breath * torso

    skirt = weights["skirt_panels"]
    dx += delayed * 1.0 * skirt
    dy += delayed * 0.7 * skirt

    joint_offsets = _joint_pixel_offsets(frame)
    support_x, support_y, support_weights = _arm_path_offset(
        px,
        py,
        path=SUPPORT_ARM_PATH,
        offsets=(
            joint_offsets["support_shoulder"],
            joint_offsets["support_elbow"],
            joint_offsets["support_wrist"],
        ),
    )
    support_distance = min(
        _segment_coordinate(px, py, SUPPORT_ARM_PATH[0], SUPPORT_ARM_PATH[1])[1],
        _segment_coordinate(px, py, SUPPORT_ARM_PATH[1], SUPPORT_ARM_PATH[2])[1],
    )
    support_radius = 76.0 + 42.0 * support_weights[1]
    support_influence = 1.0 - smoothstep(support_radius * 0.68, support_radius, support_distance)

    draw_x, draw_y, draw_weights = _arm_path_offset(
        px,
        py,
        path=DRAW_ARM_PATH,
        offsets=(
            joint_offsets["draw_shoulder"],
            joint_offsets["draw_elbow"],
            joint_offsets["draw_wrist"],
        ),
    )
    draw_distance = min(
        _segment_coordinate(px, py, DRAW_ARM_PATH[0], DRAW_ARM_PATH[1])[1],
        _segment_coordinate(px, py, DRAW_ARM_PATH[1], DRAW_ARM_PATH[2])[1],
    )
    draw_radius = 66.0 + 34.0 * draw_weights[1]
    draw_influence = 1.0 - smoothstep(draw_radius * 0.68, draw_radius, draw_distance)

    # The palette is part of the continuous surface.  Carry its broad, rigid
    # silhouette with the support wrist instead of leaving a new cut boundary.
    palette = bell(px, 605.0, 255.0) * bell(py, 640.0, 72.0) * smoothstep(360.0, 455.0, px)
    support_wrist_x, support_wrist_y = joint_offsets["support_wrist"]
    dx += support_x * support_influence + support_wrist_x * palette
    dy += support_y * support_influence + support_wrist_y * palette
    dx += draw_x * draw_influence
    dy += draw_y * draw_influence

    support_billow = (
        bell(px, 270.0, 160.0)
        * bell(py, 555.0, 185.0)
        * support_influence
        * (1.0 - support_weights[0])
        * (1.0 - support_weights[2])
    )
    draw_billow = (
        bell(px, 555.0, 145.0)
        * bell(py, 555.0, 155.0)
        * draw_influence
        * (1.0 - draw_weights[0])
        * (1.0 - draw_weights[2])
    )
    dx += delayed * (1.7 * support_billow + 0.9 * draw_billow)
    dy += delayed * (0.8 * support_billow + 0.4 * draw_billow)

    return (
        dx * CANVAS_WIDTH / SOURCE_WIDTH,
        -dy * CANVAS_HEIGHT / SOURCE_HEIGHT,
    )


def _deformed_character_vertex(
    base: tuple[float, float, float], weights: dict[str, float], frame: int
) -> tuple[float, float, float]:
    x, y, z = base
    dx, dy = _body_canvas_offset(base, weights, frame)
    return (x + dx, y + dy, z)


def _render(
    scene: bpy.types.Scene,
    objects: dict[str, bpy.types.Object],
    character_vertices: Sequence[tuple[float, float, float]],
    character_weights: Sequence[dict[str, float]],
    output: Path,
) -> list[str]:
    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("draw-*.png"):
        stale.unlink()

    names: list[str] = []
    for frame in range(FRAME_COUNT):
        cycle = 2.0 * math.pi * frame / FRAME_COUNT
        delayed = math.sin(cycle - 0.42)
        stroke = _ease_between(frame, 4, 8, 12)
        head_tilt = _ease_between(frame, 12, 16, 21)

        for vertex, base, vertex_weights in zip(
            objects["character_surface"].data.vertices,
            character_vertices,
            character_weights,
            strict=True,
        ):
            vertex.co = _deformed_character_vertex(base, vertex_weights, frame)
        objects["character_surface"].data.update()

        head_angle = math.radians(2.0 * head_tilt)
        for name in ("head_underlay", "head_face", "eyes_open", "eyes_closed"):
            objects[name].rotation_euler[2] = head_angle
        for name in ("hair_back", "hair_front"):
            objects[name].rotation_euler[2] = head_angle + math.radians(0.24 * delayed)
            objects[name].location.x += delayed * 0.42 * CANVAS_WIDTH / SOURCE_WIDTH

        arm_x = 13.0 * stroke * CANVAS_WIDTH / SOURCE_WIDTH
        arm_y = 4.8 * stroke * CANVAS_HEIGHT / SOURCE_HEIGHT
        objects["brush"].location.x += arm_x
        objects["brush"].location.y += arm_y

        blink = frame == 18
        objects["eyes_open"].hide_render = blink
        objects["eyes_closed"].hide_render = not blink

        name = f"draw-{frame:03d}.png"
        frame_path = output / name
        scene.render.filepath = str(frame_path.resolve())
        bpy.ops.render.render(write_still=True)
        # Blender's PNG compressor may choose different byte streams for the
        # same pixels across runs.  Re-encode through the project codec so the
        # committed runtime asset is both pixel- and byte-deterministic.
        rendered = source_rgba(
            frame_path, size=(scene.render.resolution_x, scene.render.resolution_y)
        )
        write_rgba(
            frame_path,
            size=(scene.render.resolution_x, scene.render.resolution_y),
            pixels=rendered,
        )
        names.append(name)

        for name in ("hair_back", "hair_front"):
            objects[name].location.x -= delayed * 0.42 * CANVAS_WIDTH / SOURCE_WIDTH
        objects["brush"].location.x -= arm_x
        objects["brush"].location.y -= arm_y
    return names


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(sys.argv if argv is None else argv)
    if (args.width, args.height) != (512, 768):
        raise SystemExit("FRAME2 draw currently requires a 512x768 runtime canvas")
    if args.fps != FPS:
        raise SystemExit(f"FRAME2 draw currently requires {FPS} FPS")

    repository = args.repository_root.resolve()
    source_root = repository / "visual-sources/kindred-default/frame2"
    validate_layers(repository)
    manifest_path = source_root / "layers/draw/layers.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contract") != LAYER_CONTRACT_VERSION:
        raise SystemExit("FRAME2 draw layer contract mismatch")

    scene = transparent_scene()
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    orthographic_camera(scene, name="FRAME2 Camera")
    objects: dict[str, bpy.types.Object] = {}
    character_vertices: list[tuple[float, float, float]] = []
    character_weights: list[dict[str, float]] = []
    for entry in manifest["layers"]:
        if not entry["render_in_rig"]:
            continue
        name = str(entry["name"])
        obj, base_vertices = textured_grid(
            mesh_name=f"FRAME2 {name} Mesh",
            object_name=f"FRAME2 {name}",
            uv_name=f"FRAME2 {name} UV",
        )
        source = source_root / "layers/draw" / str(entry["file"])
        _material(obj, source, name=f"FRAME2 {name} Material")
        obj.location.z = float(entry["order"]) * 0.001
        if "pivot" in entry:
            _set_pivot(obj, base_vertices, tuple(entry["pivot"]))
        if name == "character_surface":
            character_vertices = base_vertices
            character_weights = _add_vertex_groups(obj, base_vertices)
        obj["source_contract"] = CONTRACT_VERSION
        obj["layer_contract"] = LAYER_CONTRACT_VERSION
        obj["layer_role"] = str(entry["role"])
        obj["runtime_renderer"] = "frames"
        objects[name] = obj

    output = repository / "visual-packs/kindred-default/assets/body/frame2/draw"
    names = _render(
        scene,
        objects,
        character_vertices,
        character_weights,
        output,
    )

    # Save the inspectable rig in its neutral loop pose rather than at the final
    # deformed frame.
    for vertex, base in zip(
        objects["character_surface"].data.vertices,
        character_vertices,
        strict=True,
    ):
        vertex.co = base
    objects["character_surface"].data.update()
    objects["eyes_open"].hide_render = False
    objects["eyes_closed"].hide_render = True
    for name in (
        "head_underlay",
        "head_face",
        "eyes_open",
        "eyes_closed",
        "hair_back",
        "hair_front",
    ):
        objects[name].rotation_euler[2] = 0.0
    bpy.ops.wm.save_as_mainfile(filepath=str((source_root / "frame2-draw-rig.blend").resolve()))
    (source_root / "RENDERED.txt").write_text(
        (
            f"contract={CONTRACT_VERSION}\n"
            f"layer_contract={LAYER_CONTRACT_VERSION}\n"
            f"fps={FPS}\nsize={args.width}x{args.height}\ndraw={len(names)}\n"
        ),
        encoding="utf-8",
    )
    print(f"FRAME2_DRAW_RENDERED draw={len(names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
