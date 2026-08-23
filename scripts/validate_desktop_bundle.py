#!/usr/bin/env python3
"""Validate the unsigned macOS desktop-spirit bundle and emit release provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import stat
import struct
import subprocess
from pathlib import Path
from typing import Any


class DesktopBundleError(RuntimeError):
    pass


EXPECTED_IDENTIFIER = "dev.kindred.desktop-spirit"
EXPECTED_MINIMUM_MACOS = "13.0"
EXPECTED_LICENSE = "Apache-2.0"
EXPECTED_PACK_ID = "kindred-default"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DesktopBundleError(f"unreadable JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise DesktopBundleError(f"invalid JSON object: {path.name}")
    return value


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            payload = os.readlink(path).encode()
            kind = b"link"
        elif path.is_file():
            payload = bytes.fromhex(_sha256(path))
            kind = b"file"
        else:
            continue
        digest.update(kind + b"\0" + relative + b"\0" + payload + b"\0")
    return digest.hexdigest()


def _png_dimensions(path: Path) -> tuple[int, int]:
    try:
        with path.open("rb") as stream:
            header = stream.read(24)
    except OSError as exc:
        raise DesktopBundleError("application icon is unreadable") from exc
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise DesktopBundleError("application icon is not a PNG")
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def _mach_o_architecture(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            header = stream.read(12)
    except OSError as exc:
        raise DesktopBundleError("bundle executable is unreadable") from exc
    if len(header) != 12:
        raise DesktopBundleError("bundle executable is not a 64-bit Mach-O")
    magic, cpu_type, _cpu_subtype = struct.unpack("<III", header)
    if magic != 0xFEEDFACF:
        raise DesktopBundleError("bundle executable is not a 64-bit Mach-O")
    if cpu_type != 0x0100000C:
        raise DesktopBundleError("bundle executable is not Apple Silicon arm64")
    return "aarch64"


def _referenced_files(value: object, suffixes: frozenset[str]) -> set[str]:
    if isinstance(value, str):
        return {value} if Path(value).suffix.lower() in suffixes else set()
    if isinstance(value, list):
        return set().union(*(_referenced_files(item, suffixes) for item in value), set())
    if isinstance(value, dict):
        return set().union(*(_referenced_files(item, suffixes) for item in value.values()), set())
    return set()


def _validate_built_visual_assets(root: Path, manifest: dict[str, Any]) -> None:
    pack = (root / "visual-packs/kindred-default").resolve()
    raster_suffixes = frozenset({".png", ".svg", ".webp"})
    references = _referenced_files(manifest, raster_suffixes)
    for descriptor in _referenced_files(manifest, frozenset({".json"})):
        descriptor_path = (pack / descriptor).resolve()
        if not descriptor_path.is_relative_to(pack):
            raise DesktopBundleError("visual descriptor escapes the default pack")
        references.update(_referenced_files(_load_json(descriptor_path), raster_suffixes))
    if not references:
        raise DesktopBundleError("default visual pack declares no raster assets")

    source_hashes: set[str] = set()
    for reference in references:
        source = (pack / reference).resolve()
        if not source.is_relative_to(pack) or not source.is_file():
            raise DesktopBundleError("default visual asset is missing or escapes its pack")
        source_hashes.add(_sha256(source))

    dist_assets = root / "app/dist/assets"
    built_hashes = {
        _sha256(path)
        for path in dist_assets.glob("*")
        if path.is_file() and path.suffix.lower() in raster_suffixes
    }
    if not source_hashes <= built_hashes:
        raise DesktopBundleError("desktop build is missing a default visual asset")


def _git_value(root: Path, *arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _tracked_tree_dirty(root: Path) -> bool | None:
    try:
        result = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", "."],
            cwd=root,
            check=False,
            capture_output=True,
        )
    except OSError:
        return None
    return result.returncode != 0


def validate_desktop_bundle(app: Path, root: Path) -> dict[str, Any]:
    app = app.resolve()
    root = root.resolve()
    if app.suffix != ".app" or not app.is_dir():
        raise DesktopBundleError("macOS .app bundle is missing")

    config = _load_json(root / "app/src-tauri/tauri.conf.json")
    bundle = config.get("bundle")
    if not isinstance(bundle, dict) or bundle.get("active") is not True:
        raise DesktopBundleError("Tauri bundling is not enabled")
    if bundle.get("targets") != ["app"]:
        raise DesktopBundleError("desktop target must be macOS app only")
    if bundle.get("license") != EXPECTED_LICENSE:
        raise DesktopBundleError("desktop SPDX license is missing")
    if config.get("identifier") != EXPECTED_IDENTIFIER:
        raise DesktopBundleError("unexpected desktop bundle identifier")

    info_path = app / "Contents/Info.plist"
    try:
        with info_path.open("rb") as stream:
            info = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException) as exc:
        raise DesktopBundleError("bundle Info.plist is unreadable") from exc
    expected_info = {
        "CFBundleIdentifier": EXPECTED_IDENTIFIER,
        "CFBundleShortVersionString": config.get("version"),
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": EXPECTED_MINIMUM_MACOS,
    }
    for key, expected in expected_info.items():
        if info.get(key) != expected:
            raise DesktopBundleError(f"unexpected Info.plist value: {key}")

    executable_name = info.get("CFBundleExecutable")
    executable = app / "Contents/MacOS" / str(executable_name)
    if not executable.is_file() or not executable.stat().st_mode & stat.S_IXUSR:
        raise DesktopBundleError("bundle executable is missing or not executable")
    architecture = _mach_o_architecture(executable)
    icon_name = str(info.get("CFBundleIconFile", ""))
    if not icon_name:
        raise DesktopBundleError("bundle icon declaration is missing")
    icon_path = app / "Contents/Resources" / icon_name
    if not icon_path.suffix:
        icon_path = icon_path.with_suffix(".icns")
    if not icon_path.is_file() or icon_path.stat().st_size == 0:
        raise DesktopBundleError("compiled macOS icon is missing")

    source_icon = root / "app/src-tauri/icons/icon.png"
    width, height = _png_dimensions(source_icon)
    if width != height or width < 512:
        raise DesktopBundleError("application icon source must be square and at least 512 px")

    resources = app / "Contents/Resources"
    expected_copies = {
        root / "LICENSE": resources / "licenses/Apache-2.0.txt",
        root / "visual-packs/kindred-default/provenance.json": (
            resources / "visual-packs/kindred-default/provenance.json"
        ),
        root / "app/src-tauri/icons/provenance.json": resources / "icons/provenance.json",
    }
    for source, bundled in expected_copies.items():
        if not bundled.is_file() or source.read_bytes() != bundled.read_bytes():
            raise DesktopBundleError(f"bundled resource mismatch: {bundled.name}")

    pack_manifest = _load_json(root / "visual-packs/kindred-default/manifest.json")
    pack_provenance = _load_json(root / "visual-packs/kindred-default/provenance.json")
    icon_provenance = _load_json(root / "app/src-tauri/icons/provenance.json")
    if pack_manifest.get("id") != EXPECTED_PACK_ID:
        raise DesktopBundleError("unexpected default visual pack")
    _validate_built_visual_assets(root, pack_manifest)
    for provenance in (pack_provenance, icon_provenance):
        if (
            provenance.get("schema_version") != 1
            or provenance.get("public_license") != EXPECTED_LICENSE
        ):
            raise DesktopBundleError("asset provenance is incomplete")
    pack_assets = pack_provenance.get("assets")
    if (
        not isinstance(pack_assets, list)
        or not pack_assets
        or any(not isinstance(item, dict) or not item.get("rights_basis") for item in pack_assets)
        or not icon_provenance.get("rights_basis")
    ):
        raise DesktopBundleError("asset rights basis is missing")

    forbidden_suffixes = (".moc3", ".model3.json")
    forbidden_names = ("live2d", "cubism")
    for path in app.rglob("*"):
        lowered = path.name.lower()
        if lowered == "desktop-spirit.json":
            raise DesktopBundleError("shell preferences must remain outside the app bundle")
        if lowered.endswith(forbidden_suffixes) or any(name in lowered for name in forbidden_names):
            raise DesktopBundleError("deferred Live2D runtime or model found in V1 bundle")

    return {
        "schema_version": 1,
        "artifact": {
            "kind": "macos-app",
            "architecture": architecture,
            "bundle_identifier": EXPECTED_IDENTIFIER,
            "version": config["version"],
            "minimum_macos": EXPECTED_MINIMUM_MACOS,
            "tree_sha256": _tree_sha256(app),
            "signing": "no-developer-id",
            "notarized": False,
        },
        "source": {
            "revision": _git_value(root, "rev-parse", "HEAD"),
            "tracked_tree_dirty": _tracked_tree_dirty(root),
        },
        "default_visual_pack": {
            "id": EXPECTED_PACK_ID,
            "source_tree_sha256": _tree_sha256(root / "visual-packs/kindred-default"),
            "license": EXPECTED_LICENSE,
        },
        "application_icon": {
            "source_sha256": _sha256(source_icon),
            "license": EXPECTED_LICENSE,
        },
    }


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--provenance-output", type=Path)
    arguments = parser.parse_args()

    try:
        result = validate_desktop_bundle(arguments.app, arguments.root)
        output = arguments.provenance_output or arguments.app.with_suffix(".provenance.json")
        _write_json_atomic(output, result)
    except DesktopBundleError as exc:
        print(f"desktop bundle validation failed: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"provenance: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
