"""Dependency-free PNG RGBA codec shared by desktop visual tooling."""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
RUNTIME_SIZE = (512, 768)
ALPHA_VISIBLE = 8


class FrameValidationError(ValueError):
    """Raised when a runtime frame violates its reviewed asset contract."""


@dataclass(frozen=True)
class FrameInfo:
    width: int
    height: int
    bounds: tuple[int, int, int, int]
    digest: str


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def _reconstruct_alpha(encoded: bytes, previous: bytes, filter_type: int) -> bytes:
    # PNG filters predict each RGBA channel from the same channel in adjacent
    # pixels, so alpha can be reconstructed without spending time on RGB.
    encoded_alpha = encoded[3::4]
    decoded = bytearray(encoded_alpha)
    for index, value in enumerate(encoded_alpha):
        left = decoded[index - 1] if index >= 1 else 0
        above = previous[index] if previous else 0
        upper_left = previous[index - 1] if previous and index >= 1 else 0
        if filter_type == 0:
            predictor = 0
        elif filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = above
        elif filter_type == 3:
            predictor = (left + above) // 2
        elif filter_type == 4:
            predictor = _paeth(left, above, upper_left)
        else:
            raise FrameValidationError(f"unsupported_png_filter:{filter_type}")
        decoded[index] = (value + predictor) & 0xFF
    return bytes(decoded)


def _chunks(
    payload: bytes,
    name: str,
    *,
    expected_size: tuple[int, int] | None,
) -> tuple[int, int, bytes]:
    if not payload.startswith(PNG_SIGNATURE):
        raise FrameValidationError(f"png_signature_invalid:{name}")

    offset = len(PNG_SIGNATURE)
    width = height = 0
    compressed = bytearray()
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise FrameValidationError(f"png_chunks_invalid:{name}")
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        end = offset + 12 + length
        if end > len(payload):
            raise FrameValidationError(f"png_chunks_invalid:{name}")
        chunk_type = payload[offset + 4 : offset + 8]
        chunk = payload[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", payload[offset + 8 + length : end])[0]
        if zlib.crc32(chunk_type + chunk) & 0xFFFFFFFF != expected_crc:
            raise FrameValidationError(f"png_crc_invalid:{name}")
        offset = end
        if chunk_type == b"IHDR":
            width, height, depth, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
            if (
                (expected_size is not None and (width, height) != expected_size)
                or depth != 8
                or color != 6
                or compression != 0
                or filtering != 0
                or interlace != 0
            ):
                raise FrameValidationError(f"png_format_invalid:{name}")
        elif chunk_type == b"IDAT":
            compressed.extend(chunk)
        elif chunk_type == b"IEND":
            break

    if width == 0 or height == 0 or not compressed:
        raise FrameValidationError(f"png_chunks_missing:{name}")
    return width, height, bytes(compressed)


def frame_info(path: Path) -> FrameInfo:
    """Read validated runtime geometry and content identity from an RGBA PNG."""

    payload = path.read_bytes()
    width, height, compressed = _chunks(
        payload,
        path.name,
        expected_size=RUNTIME_SIZE,
    )
    raw = zlib.decompress(compressed)
    stride = width * 4
    expected_bytes = height * (stride + 1)
    if len(raw) != expected_bytes:
        raise FrameValidationError(f"png_payload_invalid:{path.name}")

    previous = b""
    first_row = b""
    min_x, min_y = width, height
    max_x = max_y = -1
    cursor = 0
    for y in range(height):
        filter_type = raw[cursor]
        encoded = raw[cursor + 1 : cursor + stride + 1]
        alpha = _reconstruct_alpha(encoded, previous, filter_type)
        cursor += stride + 1
        previous = alpha
        if y == 0:
            first_row = alpha
        for x, value in enumerate(alpha):
            if value > ALPHA_VISIBLE:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if max_x < 0:
        raise FrameValidationError(f"frame_empty:{path.name}")
    if first_row[0] != 0 or first_row[-1] != 0:
        raise FrameValidationError(f"top_corner_not_transparent:{path.name}")
    if previous[0] != 0 or previous[-1] != 0:
        raise FrameValidationError(f"bottom_corner_not_transparent:{path.name}")

    return FrameInfo(
        width=width,
        height=height,
        bounds=(min_x, min_y, max_x, max_y),
        digest=hashlib.sha256(payload).hexdigest(),
    )


def rgba_pixels(path: Path) -> bytes:
    """Decode a validated runtime PNG into row-major RGBA bytes."""

    payload = path.read_bytes()
    width, height, compressed = _chunks(
        payload,
        path.name,
        expected_size=RUNTIME_SIZE,
    )
    return _decode_rgba(width, height, compressed, path.name)


def source_rgba(path: Path, *, size: tuple[int, int]) -> bytes:
    """Decode a reviewed source PNG with an explicit geometry contract."""

    payload = path.read_bytes()
    width, height, compressed = _chunks(
        payload,
        path.name,
        expected_size=size,
    )
    return _decode_rgba(width, height, compressed, path.name)


def _decode_rgba(width: int, height: int, compressed: bytes, name: str) -> bytes:
    raw = zlib.decompress(compressed)
    stride = width * 4
    expected_bytes = height * (stride + 1)
    if len(raw) != expected_bytes:
        raise FrameValidationError(f"png_payload_invalid:{name}")

    decoded_image = bytearray(width * height * 4)
    previous = bytearray()
    cursor = 0
    for y in range(height):
        filter_type = raw[cursor]
        encoded = raw[cursor + 1 : cursor + stride + 1]
        decoded = bytearray(encoded)
        cursor += stride + 1
        for index, value in enumerate(encoded):
            left = decoded[index - 4] if index >= 4 else 0
            above = previous[index] if previous else 0
            upper_left = previous[index - 4] if previous and index >= 4 else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = _paeth(left, above, upper_left)
            else:
                raise FrameValidationError(f"unsupported_png_filter:{filter_type}")
            decoded[index] = (value + predictor) & 0xFF
        row_start = y * stride
        decoded_image[row_start : row_start + stride] = decoded
        previous = decoded
    return bytes(decoded_image)


def write_rgba(path: Path, *, size: tuple[int, int], pixels: bytes) -> None:
    """Write deterministic 8-bit, non-interlaced RGBA pixels as a PNG."""

    width, height = size
    stride = width * 4
    if len(pixels) != stride * height:
        raise FrameValidationError(f"rgba_payload_invalid:{path.name}")

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    scanlines = bytearray()
    for y in range(height):
        scanlines.append(0)
        start = y * stride
        scanlines.extend(pixels[start : start + stride])
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    payload = (
        PNG_SIGNATURE
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(scanlines), level=9))
        + chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
