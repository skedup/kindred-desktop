# FRAME1 source assets

This directory is the non-runtime source of the `settle`, `sleep`, and `eat` frame animations in
`visual-packs/kindred-default`.

## Source contract

- `keys/blink.png` is the generated closed-eye source. The generator composites only two feathered
  eye ellipses from it onto the first-party `assets/body/neutral.png` and writes
  `keys/blink-local.png`; every pixel outside that eye mask remains neutral-derived.
- `keys/sleep.png` is the dedicated sleep pose.
- `keys/eat-rest.png`, `keys/eat-mid.png`, and `keys/eat-bite.png` are controlled action key poses
  derived from the same first-party identity and costume.
- Key poses were generated with OpenAI built-in image generation on 2026-08-20, using no
  third-party image input. The green background was converted to alpha with FFmpeg chroma-key and
  despill filters.
- `keys/blink-local.png`, `frame1-rig.blend`, and the runtime PNG sequences are deterministic
  outputs of `tools/visual_pipeline/standing_generate.py` under FFmpeg and Blender 5.2 LTS.
- Krita 5.3.3 is the manual cleanup fallback for face, hands, occlusion, and alpha-edge defects;
  the current reviewed keys did not require a destructive manual repaint.

The reproducible animation workflow is documented in the
[visual-pipeline README](../../../tools/visual_pipeline/README.md); production decisions remain available in this
repository's history.

## Rebuild

The rebuild requires `ffmpeg` on `PATH`. On the current macOS workstation, Blender is installed
through Steam:

```bash
"$HOME/Library/Application Support/Steam/steamapps/common/Blender/Blender.app/Contents/MacOS/Blender" \
  --background \
  --python tools/visual_pipeline/standing_generate.py \
  -- \
  --repository-root "$PWD"
```

The generator intentionally produces 512×768 RGBA runtime frames at 6 FPS. The 1024×1536 source
keys remain available for future re-rigging, while the shipped default pack stays below its 64 MiB
soft budget.
