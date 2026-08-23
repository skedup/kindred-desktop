"""Shared Blender canvas primitives for desktop frame production."""

from __future__ import annotations

import math
from pathlib import Path

import bpy

SOURCE_WIDTH = 1024
SOURCE_HEIGHT = 1536
CANVAS_WIDTH = 2.0
CANVAS_HEIGHT = 3.0
GRID_COLUMNS = 64
GRID_ROWS = 96


def transparent_scene() -> bpy.types.Scene:
    """Create the deterministic transparent scene used by frame generators."""

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 100
    scene.render.resolution_percentage = 100
    scene.render.use_file_extension = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    return scene


def orthographic_camera(scene: bpy.types.Scene, *, name: str) -> None:
    """Attach a fixed orthographic camera covering the vertical source canvas."""

    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    data.ortho_scale = CANVAS_HEIGHT
    camera = bpy.data.objects.new(name, data)
    camera.location = (0.0, 0.0, 10.0)
    scene.collection.objects.link(camera)
    scene.camera = camera


def textured_grid(
    *,
    mesh_name: str,
    object_name: str,
    uv_name: str,
) -> tuple[bpy.types.Object, list[tuple[float, float, float]]]:
    """Create the common deformable grid and source-aligned UV coordinates."""

    vertices: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    for row in range(GRID_ROWS + 1):
        v = row / GRID_ROWS
        for column in range(GRID_COLUMNS + 1):
            u = column / GRID_COLUMNS
            vertices.append(((u - 0.5) * CANVAS_WIDTH, (0.5 - v) * CANVAS_HEIGHT, 0.0))
            uvs.append((u, 1.0 - v))

    stride = GRID_COLUMNS + 1
    for row in range(GRID_ROWS):
        for column in range(GRID_COLUMNS):
            top_left = row * stride + column
            faces.append((top_left, top_left + 1, top_left + stride + 1, top_left + stride))

    mesh = bpy.data.meshes.new(mesh_name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv_layer = mesh.uv_layers.new(name=uv_name)
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            uv_layer.data[loop_index].uv = uvs[vertex_index]

    obj = bpy.data.objects.new(object_name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj, vertices


def rgba_material(obj: bpy.types.Object, *, name: str) -> bpy.types.ShaderNodeTexImage:
    """Attach an unlit alpha-aware image material and return its texture node."""

    material = bpy.data.materials.new(name)
    material.use_nodes = True
    try:
        material.surface_render_method = "DITHERED"
    except AttributeError:
        pass

    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    emission = nodes.new("ShaderNodeEmission")
    texture = nodes.new("ShaderNodeTexImage")
    texture.interpolation = "Linear"
    mix = nodes.new("ShaderNodeMixShader")
    material.node_tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
    material.node_tree.links.new(texture.outputs["Alpha"], mix.inputs[0])
    material.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
    material.node_tree.links.new(emission.outputs[0], mix.inputs[2])
    material.node_tree.links.new(mix.outputs[0], output.inputs["Surface"])
    obj.data.materials.append(material)
    return texture


def set_texture_image(
    texture: bpy.types.ShaderNodeTexImage,
    path: Path,
) -> bpy.types.Image:
    """Load an sRGB straight-alpha image and assign it to a texture node."""

    absolute = str(path.resolve())
    image = bpy.data.images.get(absolute)
    if image is None:
        image = bpy.data.images.load(absolute, check_existing=True)
    image.alpha_mode = "STRAIGHT"
    image.colorspace_settings.name = "sRGB"
    texture.image = image
    return image


def bell(value: float, center: float, radius: float) -> float:
    """Return a Gaussian-like regional influence weight."""

    return math.exp(-(((value - center) / radius) ** 2))


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    """Return a clamped cubic transition between two scalar edges."""

    if edge0 == edge1:
        return float(value >= edge1)
    amount = min(1.0, max(0.0, (value - edge0) / (edge1 - edge0)))
    return amount * amount * (3.0 - 2.0 * amount)
