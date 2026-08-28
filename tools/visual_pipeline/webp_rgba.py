"""Lossless WebP codec for reviewed runtime animation frames."""

from __future__ import annotations

from pathlib import Path

from tools.visual_pipeline.png_rgba import RUNTIME_SIZE, FrameValidationError


def _image_module():
    try:
        from PIL import Image, features
    except ImportError as error:
        raise RuntimeError(
            "Pillow with WebP support is required; install the visual-tool dev dependencies"
        ) from error
    if not features.check("webp"):
        raise RuntimeError("the installed Pillow build does not support WebP")
    return Image


def webp_rgba(path: Path, *, size: tuple[int, int] = RUNTIME_SIZE) -> bytes:
    """Decode one non-animated WebP frame under an explicit geometry contract."""

    image_module = _image_module()
    with image_module.open(path) as image:
        if image.format != "WEBP" or image.size != size or getattr(image, "is_animated", False):
            raise FrameValidationError(f"webp_format_invalid:{path.name}")
        return image.convert("RGBA").tobytes()


def write_lossless_webp(
    path: Path,
    *,
    size: tuple[int, int],
    pixels: bytes,
) -> None:
    """Encode RGBA pixels as a single-frame, exact lossless WebP image."""

    width, height = size
    if len(pixels) != width * height * 4:
        raise FrameValidationError(f"rgba_payload_invalid:{path.name}")
    image_module = _image_module()
    path.parent.mkdir(parents=True, exist_ok=True)
    image = image_module.frombytes("RGBA", size, pixels)
    try:
        image.save(
            path,
            format="WEBP",
            lossless=True,
            quality=100,
            method=6,
            exact=True,
        )
    finally:
        image.close()
