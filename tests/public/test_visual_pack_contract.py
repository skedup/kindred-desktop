"""Public release contract for the bundled desktop visual pack."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "visual-packs/kindred-default"
EXPECTED_ACTIONS = {
    "change_outfit",
    "compose",
    "draw",
    "eat",
    "explore_place",
    "makeup",
    "pack_bag",
    "prepare_food",
    "remove_makeup",
    "ride",
    "send",
    "settle",
    "sleep",
    "walk",
}


def _load_validator() -> Any:
    script = ROOT / "scripts/validate_visual_pack.py"
    spec = importlib.util.spec_from_file_location("public_visual_pack_validator", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_visual_pack_is_complete_local_silent_and_static_safe() -> None:
    module = _load_validator()
    expected = EXPECTED_ACTIONS

    result = module.validate_visual_pack(PACK, expected_actions=expected)
    manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))

    assert result["actions"] == len(expected)
    assert manifest["fallback_motion"] == "neutral"
    assert manifest["motions"]["neutral"]["renderer"] == "static"
    action_motions = [
        manifest["motions"][manifest["action_motions"][action]] for action in expected
    ]
    decorations = {motion["decoration"]["source"] for motion in action_motions}
    reduced_decorations = {
        motion["reduced_motion"]["decoration"]["source"] for motion in action_motions
    }
    assert len(decorations) == len(expected)
    assert reduced_decorations == decorations
    assert all(motion["fallback_motion"] == "neutral" for motion in action_motions)
    assert all(motion["reduced_motion"]["renderer"] == "static" for motion in action_motions)

    body_sources = ("assets/body/neutral.png", "assets/body/breathe.png")
    decoded_hashes: dict[str, bytes] = {}
    for source in (*body_sources, *sorted(decorations)):
        width, height, pixels = module._decode_png_rgba8(PACK / source)
        alpha = pixels[3::4]
        assert (width, height) == (1024, 1536)
        assert min(alpha) == 0
        assert max(alpha) > 0
        decoded_hashes[source] = hashlib.sha256(pixels).digest()

    assert len({decoded_hashes[source] for source in decorations}) == len(decorations)
    assert decoded_hashes[body_sources[0]] != decoded_hashes[body_sources[1]]
    assert "audio" not in json.dumps(manifest).lower()
    assert "identity_from_state" not in json.dumps(manifest)
