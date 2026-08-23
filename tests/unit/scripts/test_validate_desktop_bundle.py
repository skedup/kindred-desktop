"""Tests for the macOS desktop bundle release gate."""

from __future__ import annotations

import importlib.util
import json
import plistlib
import shutil
import stat
import struct
import sys
from pathlib import Path
from typing import Any

import pytest


def _load_module() -> Any:
    script = Path(__file__).resolve().parents[3] / "scripts/validate_desktop_bundle.py"
    spec = importlib.util.spec_from_file_location("validate_desktop_bundle", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _png_header(width: int = 1024, height: int = 1024) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I4sII", 13, b"IHDR", width, height)


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    app = tmp_path / "Kindred Desktop Spirit.app"
    resources = app / "Contents/Resources"
    executable = app / "Contents/MacOS/kindred-desktop-spirit"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(struct.pack("<III", 0xFEEDFACF, 0x0100000C, 0))
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    resources.mkdir(parents=True)
    (resources / "icon.icns").write_bytes(b"icon")
    with (app / "Contents/Info.plist").open("wb") as stream:
        plistlib.dump(
            {
                "CFBundleExecutable": "kindred-desktop-spirit",
                "CFBundleIconFile": "icon.icns",
                "CFBundleIdentifier": "dev.kindred.desktop-spirit",
                "CFBundlePackageType": "APPL",
                "CFBundleShortVersionString": "0.1.0",
                "LSMinimumSystemVersion": "13.0",
            },
            stream,
        )

    config = root / "app/src-tauri/tauri.conf.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "identifier": "dev.kindred.desktop-spirit",
                "bundle": {
                    "active": True,
                    "targets": ["app"],
                    "license": "Apache-2.0",
                },
            }
        )
    )
    icon = root / "app/src-tauri/icons/icon.png"
    icon.parent.mkdir()
    icon.write_bytes(_png_header())
    icon_provenance = icon.with_name("provenance.json")
    icon_provenance.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "public_license": "Apache-2.0",
                "rights_basis": "first-party fixture",
            }
        )
    )

    license_path = root / "LICENSE"
    license_path.write_text("Apache fixture\n")
    pack = root / "visual-packs/kindred-default"
    pack.mkdir(parents=True)
    visual = pack / "assets/neutral.png"
    visual.parent.mkdir()
    visual.write_bytes(_png_header())
    (pack / "manifest.json").write_text(
        json.dumps(
            {
                "id": "kindred-default",
                "motions": {"neutral": {"renderer": "static", "source": "assets/neutral.png"}},
            }
        )
    )
    dist_asset = root / "app/dist/assets/neutral-fixture.png"
    dist_asset.parent.mkdir(parents=True)
    shutil.copyfile(visual, dist_asset)
    pack_provenance = pack / "provenance.json"
    pack_provenance.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "public_license": "Apache-2.0",
                "assets": [{"rights_basis": "first-party fixture"}],
            }
        )
    )
    copies = {
        license_path: resources / "licenses/Apache-2.0.txt",
        pack_provenance: resources / "visual-packs/kindred-default/provenance.json",
        icon_provenance: resources / "icons/provenance.json",
    }
    for source, target in copies.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return root, app


def test_accepts_unsigned_mac_app_and_records_provenance(tmp_path: Path) -> None:
    module = _load_module()
    root, app = _fixture(tmp_path)

    result = module.validate_desktop_bundle(app, root)

    assert result["artifact"]["signing"] == "no-developer-id"
    assert result["artifact"]["notarized"] is False
    assert result["artifact"]["bundle_identifier"] == "dev.kindred.desktop-spirit"
    assert result["default_visual_pack"]["id"] == "kindred-default"
    assert len(result["artifact"]["tree_sha256"]) == 64


def test_rejects_resource_drift_and_deferred_live2d(tmp_path: Path) -> None:
    module = _load_module()
    root, app = _fixture(tmp_path)
    bundled_license = app / "Contents/Resources/licenses/Apache-2.0.txt"
    bundled_license.write_text("changed\n")
    with pytest.raises(module.DesktopBundleError, match="resource mismatch"):
        module.validate_desktop_bundle(app, root)

    shutil.copyfile(root / "LICENSE", bundled_license)
    (app / "Contents/Resources/avatar.model3.json").write_text("{}")
    with pytest.raises(module.DesktopBundleError, match="Live2D"):
        module.validate_desktop_bundle(app, root)


def test_rejects_non_square_icon_and_wrong_platform_target(tmp_path: Path) -> None:
    module = _load_module()
    root, app = _fixture(tmp_path)
    (root / "app/src-tauri/icons/icon.png").write_bytes(_png_header(height=768))
    with pytest.raises(module.DesktopBundleError, match="square"):
        module.validate_desktop_bundle(app, root)

    (root / "app/src-tauri/icons/icon.png").write_bytes(_png_header())
    config = root / "app/src-tauri/tauri.conf.json"
    value = json.loads(config.read_text())
    value["bundle"]["targets"] = ["app", "dmg"]
    config.write_text(json.dumps(value))
    with pytest.raises(module.DesktopBundleError, match="macOS app only"):
        module.validate_desktop_bundle(app, root)


def test_rejects_preferences_inside_replaceable_app(tmp_path: Path) -> None:
    module = _load_module()
    root, app = _fixture(tmp_path)
    (app / "Contents/Resources/desktop-spirit.json").write_text("{}")

    with pytest.raises(module.DesktopBundleError, match="preferences"):
        module.validate_desktop_bundle(app, root)


def test_rejects_non_mach_o_executable(tmp_path: Path) -> None:
    module = _load_module()
    root, app = _fixture(tmp_path)
    executable = app / "Contents/MacOS/kindred-desktop-spirit"
    executable.write_bytes(b"not mach-o")

    with pytest.raises(module.DesktopBundleError, match="Mach-O"):
        module.validate_desktop_bundle(app, root)


def test_rejects_missing_built_visual_asset(tmp_path: Path) -> None:
    module = _load_module()
    root, app = _fixture(tmp_path)
    (root / "app/dist/assets/neutral-fixture.png").unlink()

    with pytest.raises(module.DesktopBundleError, match="missing a default visual asset"):
        module.validate_desktop_bundle(app, root)
