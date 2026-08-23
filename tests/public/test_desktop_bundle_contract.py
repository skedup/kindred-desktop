"""Public source contract for the macOS desktop-spirit bundle."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _load_validator() -> Any:
    script = ROOT / "scripts/validate_desktop_bundle.py"
    spec = importlib.util.spec_from_file_location("public_desktop_bundle_validator", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_desktop_bundle_is_macos_only_readonly_and_distribution_traced() -> None:
    validator = _load_validator()
    config = json.loads((ROOT / "app/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "app/package.json").read_text(encoding="utf-8"))
    capabilities = json.loads(
        (ROOT / "app/src-tauri/capabilities/desktop.json").read_text(encoding="utf-8")
    )

    assert config["identifier"] == validator.EXPECTED_IDENTIFIER
    assert config["bundle"]["active"] is True
    assert config["bundle"]["targets"] == ["app"]
    assert config["bundle"]["license"] == "Apache-2.0"
    assert config["bundle"]["macOS"]["minimumSystemVersion"] == "13.0"
    assert config["bundle"]["resources"] == {
        "../../LICENSE": "licenses/Apache-2.0.txt",
        "../../visual-packs/kindred-default/provenance.json": (
            "visual-packs/kindred-default/provenance.json"
        ),
        "icons/provenance.json": "icons/provenance.json",
    }
    assert "--bundles app --no-sign" in package["scripts"]["tauri:bundle:macos-arm64"]
    assert package["scripts"]["bundle:macos-arm64"].endswith("pnpm bundle:validate")

    width, height = validator._png_dimensions(ROOT / "app/src-tauri/icons/icon.png")
    assert width == height and width >= 512
    icon_provenance = json.loads(
        (ROOT / "app/src-tauri/icons/provenance.json").read_text(encoding="utf-8")
    )
    assert icon_provenance["public_license"] == "Apache-2.0"
    assert icon_provenance["rights_basis"]

    capability_text = json.dumps(capabilities).lower()
    assert "http" not in capability_text
    assert "shell" not in capability_text
    assert "process" not in capability_text
    assert "filesystem" not in capability_text


def test_desktop_release_source_contains_no_live2d_or_service_control() -> None:
    dependency_manifests = "\n".join(
        (ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in ("app/package.json", "app/pnpm-lock.yaml")
    ).lower()
    source_paths = [
        ROOT / "app/src-tauri",
        ROOT / "app/src",
    ]
    source = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for base in source_paths
        for path in base.rglob("*")
        if path.is_file()
        and "target" not in path.parts
        and (
            path.suffix in {".css", ".html", ".json", ".lock", ".rs", ".toml", ".ts", ".vue"}
            or path.name == ".gitignore"
        )
    ).lower()

    assert "live2d" not in source
    assert "cubism" not in source
    assert "live2d" not in dependency_manifests
    assert "cubism" not in dependency_manifests
    for forbidden_command in ("start_heart", "stop_heart", "start_web", "stop_web"):
        assert forbidden_command not in source
